"""Adapta el stream de Anthropic al ``A2uiStreamParser`` de A2UI.

El ``A2uiStreamParser`` espera chunks de texto plano y emite ``ResponsePart``
(texto conversacional + bloques ``<a2ui-json>``). El stream de Anthropic
entrega eventos tipados (``RawContentBlockDeltaEvent``) con deltas de texto o
de JSON de tool use. Este módulo hace la traducción mecánica:

- Los ``TextDelta`` se concatenan y se alimentan al parser, que detecta los
  bloques ``<a2ui-json>`` y emite partes A2UI + texto.
- Los ``InputJSONDelta`` (tool use) se acumulan por índice de bloque y se
  validan al cerrar el bloque. No pasan por el parser de tags porque la tool
  ya entrega JSON estructurado.

Esto cubre los dos modos soportados por la v0.1: system prompt + tags, y
tool use con ``send_a2ui_json_to_client``.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from a2ui.parser.response_part import ResponsePart
from a2ui.parser.streaming import A2uiStreamParser


class ClaudeStreamParser:
  """Parsea el stream de ``anthropic`` y emite ``ResponsePart`` de A2UI.

  Cubre dos modos:

  1. **Modo tags**: Claude emite texto con bloques ``<a2ui-json>`` (cuando se
     usa system prompt sin tool). El ``A2uiStreamParser`` detecta los bloques.
  2. **Modo tool**: Claude invoca la tool ``send_a2ui_json_to_client``. Los
     ``InputJSONDelta`` se acumulan y, al cerrar el bloque, se validan y se
     emiten como ``ResponsePart`` con ``a2ui_json`` ya parseado.

  El parser es stateful y se consume con ``process_event`` (síncrono) o
  ``parse_stream`` (iterator sobre el stream de Anthropic).

  Attributes:
    catalog: Catálogo A2UI para construir el ``A2uiStreamParser`` y validar
      los JSON de tool use. Si es ``None``, el parser de tags no valida.
    validator: Validador opcional. Si es ``None`` se usa
      ``catalog.validator`` (si hay catálogo).
    strict_tool_validation: Si validar el JSON de tool use contra el
      esquema. Por defecto ``True``.

  Example:
    ```python
    parser = ClaudeStreamParser(catalog=builder.get_catalog())
    with client.messages.stream(..., tools=[tool]) as stream:
        for event in stream:
            for part in parser.process_event(event):
                if part.a2ui_json:
                    send_to_client(part.a2ui_json)
                if part.text:
                    print(part.text, end="")
    ```
  """

  def __init__(
      self,
      catalog: Any = None,
      validator: Any = None,
      strict_tool_validation: bool = True,
      repair: bool = True,
      tool_name: str = "send_a2ui_json_to_client",
      max_tool_input_chars: int = 2_000_000,
  ) -> None:
    """Inicializa el parser.

    Args:
      catalog: ``A2uiCatalog`` para el parser de tags. Puede ser ``None``
        si solo se usa el modo tool (no hay tags que parsear).
      validator: ``A2uiValidator`` para validar JSON de tool use. Si es
        ``None`` y ``catalog`` no lo es, se usa ``catalog.validator``.
      strict_tool_validation: Si validar el JSON de cada tool use contra el
        esquema antes de emitirlo como ``ResponsePart``.
      repair: Si reparar problemas conocidos antes de validar. Aplica
        ``repair_orphans`` (reconecta componentes huerfanos) y parchea el
        schema para ``DateTimeInput.min/max``. Por defecto ``True``.
      tool_name: Nombre de la tool A2UI que debe procesar. Las demas tools se
        ignoran para poder compartir el stream con otras herramientas.
      max_tool_input_chars: Limite defensivo del JSON acumulado por tool use.
    """
    if max_tool_input_chars <= 0:
      raise ValueError("max_tool_input_chars debe ser mayor que cero")
    self._a2ui_parser = A2uiStreamParser(catalog=catalog) if catalog else None
    self._validator = validator or (catalog.validator if catalog else None)
    self.strict_tool_validation = strict_tool_validation
    self.repair = repair
    self._catalog = catalog
    self.tool_name = tool_name
    self.max_tool_input_chars = max_tool_input_chars
    # Buffers por indice: index -> {"name": str, "id": str, "json": str}
    self._tool_buffers: dict[int, dict[str, str]] = {}
    self.last_tool_use_id: str = ""
    self.last_tool_used: bool = False
    self.last_tool_input: Any = None
    self.last_a2ui_json: Any = None
    self.last_repairs: list[str] = []

  def process_event(self, event: Any) -> list[ResponsePart]:
    """Procesa un evento del stream de Anthropic y devuelve partes completas.

    Args:
      event: Un ``RawMessageStreamEvent`` (o cualquier objeto con ``type`` y
        ``delta`` compatibles). Se aceptan:

        - ``content_block_start``: registra el nombre de la tool si es tool
          use.
        - ``content_block_delta``: si ``delta`` es ``TextDelta``, alimenta el
          parser de tags; si es ``InputJSONDelta``, acumula JSON.
        - ``content_block_stop``: si era tool use, valida y emite el
          ``ResponsePart`` con el JSON parseado.

    Returns:
      Lista de ``ResponsePart`` (puede ser vacía si el evento no produce
      nada completo todavía).

    Raises:
      ValueError: Si el JSON de tool use no es válido o no pasa la
        validación del esquema (solo si ``strict_tool_validation`` es
        ``True``).
    """
    etype = getattr(event, "type", None)
    if etype == "content_block_start":
      return self._on_block_start(event)
    if etype == "content_block_delta":
      return self._on_block_delta(event)
    if etype == "content_block_stop":
      return self._on_block_stop(event)
    return []

  def parse_stream(self, stream: Any) -> Iterator[ResponsePart]:
    """Itera sobre un stream de Anthropic y cede ``ResponsePart``.

    Atajo para ``for event in stream: for part in parser.process_event(event):
    yield part``. Acepta tanto el ``MessageStream`` (gestor de contexto) como
    cualquier iterable de eventos.

    Args:
      stream: Objeto iterable de eventos (por ejemplo,
        ``client.messages.stream(...)``).

    Yields:
      ``ResponsePart`` con texto o ``a2ui_json``.
    """
    for event in stream:
      yield from self.process_event(event)

  def _on_block_start(self, event: Any) -> list[ResponsePart]:
    block = getattr(event, "content_block", None)
    if block is None:
      return []
    # Si es tool_use, registrar el nombre para emitirlo al cerrar el bloque.
    if getattr(block, "type", None) == "tool_use":
      idx = getattr(event, "index", 0)
      name = getattr(block, "name", "")
      if name != self.tool_name:
        return []
      self._tool_buffers[idx] = {
          "name": name,
          "id": getattr(block, "id", ""),
          "json": "",
      }
      self.last_tool_use_id = self._tool_buffers[idx]["id"]
      self.last_tool_used = True
      self.last_tool_input = None
      self.last_a2ui_json = None
      self.last_repairs = []
    return []

  def _on_block_delta(self, event: Any) -> list[ResponsePart]:
    delta = getattr(event, "delta", None)
    if delta is None:
      return []
    dtype = getattr(delta, "type", None)
    if dtype == "text_delta":
      text = getattr(delta, "text", "")
      if not text:
        return []
      if self._a2ui_parser is None:
        return [ResponsePart(text=text)]
      return self._a2ui_parser.process_chunk(text)
    if dtype == "input_json_delta":
      idx = getattr(event, "index", 0)
      buf = self._tool_buffers.get(idx)
      if buf is None:
        return []
      buf["json"] += getattr(delta, "partial_json", "")
      if len(buf["json"]) > self.max_tool_input_chars:
        self._tool_buffers.pop(idx, None)
        raise ValueError(
            f"El JSON de tool use supera {self.max_tool_input_chars} caracteres"
        )
    return []

  def _on_block_stop(self, event: Any) -> list[ResponsePart]:
    idx = getattr(event, "index", 0)
    buf = self._tool_buffers.pop(idx, None)
    if buf is None:
      return []
    raw = buf["json"].strip()
    if not raw:
      return []
    try:
      parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
      raise ValueError(f"JSON invalido en tool use {buf['name']!r}: {exc}") from exc
    self.last_tool_input = parsed
    # Desenvolver a2ui_json si la tool lo envolvio (create_a2ui_tool envuelve
    # el esquema s2c en {"a2ui_json": [...]} para evitar oneOf en la raiz,
    # que Anthropic no soporta).
    if isinstance(parsed, dict) and "a2ui_json" in parsed and len(parsed) == 1:
      parsed = parsed["a2ui_json"]
    self.last_a2ui_json = parsed
    if not isinstance(parsed, list):
      raise ValueError("a2ui_json debe ser una lista de mensajes A2UI")
    if not parsed:
      raise ValueError("a2ui_json debe contener al menos un mensaje A2UI")
    # Reparar antes de validar si repair esta activado.
    if self.repair:
      from .repair import repair_payload

      if isinstance(parsed, list):
        parsed = repair_payload(
            parsed,
            catalog=self._catalog,
            repair_log=self.last_repairs,
        )
        self.last_a2ui_json = parsed
    if self.strict_tool_validation and self._validator is not None:
      if self.repair and self._catalog is not None:
        # Validar con schema parcheado (DateTimeInput oneOf -> anyOf)
        from .tool import _validate_with_patched_schema
        from .repair import patch_catalog_schema

        patched = patch_catalog_schema(self._catalog.catalog_schema)
        _validate_with_patched_schema(
            self._catalog, patched, parsed, strict_integrity=True
        )
      else:
        self._validator.validate(parsed)
    return [ResponsePart(a2ui_json=parsed)]

  def flush(self) -> list[ResponsePart]:
    """Vuelca el buffer interno del parser de tags.

    Útil al final del stream por si quedó texto sin emitir. No afecta a los
    buffers de tool use (esos se cierran con ``content_block_stop``).
    """
    if self._a2ui_parser is None:
      return []
    # El parser de A2UI no expone un flush público; se puede llamar con un
    # chunk vacío para forzar el cierre de un bloque pendiente.
    return self._a2ui_parser.process_chunk("")
