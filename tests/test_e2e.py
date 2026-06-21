"""Test end-to-end: integra las cuatro piezas con un stream simulado.

Simula el flujo completo de uso:

1. Crear builder, generar system prompt, crear tool y parser.
2. Simular un stream de Anthropic con tool use (JSON A2UI en ``InputJSONDelta``).
3. Procesar eventos y recolectar ``ResponsePart``.
4. Convertir el ``a2ui_json`` a ``A2uiPart`` para transporte.
5. Verificar que todo encaja.

No llama a la API de Anthropic: usa los fakes de ``test_stream_parser``.
"""

import json
from dataclasses import dataclass
from typing import Any

import pytest

from anthropic_a2ui import (
    A2uiPart,
    ClaudeA2uiPromptBuilder,
    ClaudeStreamParser,
    MIME_A2UI,
    create_a2ui_tool,
    to_a2ui_part,
)


@dataclass
class _FakeTextDelta:
  text: str
  type: str = "text_delta"


@dataclass
class _FakeInputJSONDelta:
  partial_json: str
  type: str = "input_json_delta"


@dataclass
class _FakeDeltaEvent:
  type: str
  delta: Any
  index: int = 0


@dataclass
class _FakeBlock:
  type: str
  name: str = ""


@dataclass
class _FakeBlockStart:
  type: str
  index: int
  content_block: Any


@dataclass
class _FakeBlockStop:
  type: str
  index: int


class TestEndToEndModoTool:
  """Flujo completo en modo tool use."""

  def test_flujo_completo_tool_use(self, sample_a2ui_json):
    # 1. Builder + prompt + tool + parser
    builder = ClaudeA2uiPromptBuilder(version="0.9")
    system_prompt = builder.build(
        role_description="Construye formularios de contacto.",
        include_schema=True,
        include_examples=True,
    )
    catalog = builder.get_catalog()
    tool = create_a2ui_tool(catalog)
    parser = ClaudeStreamParser(catalog=catalog, strict_tool_validation=True)

    # 2. Simular stream de Anthropic: texto + tool_use
    raw = json.dumps(sample_a2ui_json)
    events = [
        _FakeBlockStart(
            type="content_block_start",
            index=0,
            content_block=_FakeBlock(type="text", name=""),
        ),
        _FakeDeltaEvent(
            type="content_block_delta",
            delta=_FakeTextDelta("Aquí tienes el formulario:"),
            index=0,
        ),
        _FakeBlockStop(type="content_block_stop", index=0),
        _FakeBlockStart(
            type="content_block_start",
            index=1,
            content_block=_FakeBlock(type="tool_use", name="send_a2ui_json_to_client"),
        ),
        _FakeDeltaEvent(
            type="content_block_delta", delta=_FakeInputJSONDelta(raw), index=1
        ),
        _FakeBlockStop(type="content_block_stop", index=1),
    ]

    # 3. Procesar
    text_parts: list[str] = []
    a2ui_payloads: list = []
    for event in events:
      for part in parser.process_event(event):
        if part.text:
          text_parts.append(part.text)
        if part.a2ui_json is not None:
          a2ui_payloads.append(part.a2ui_json)

    # 4. Verificaciones
    assert system_prompt  # prompt no vacío
    assert tool["name"] == "send_a2ui_json_to_client"
    assert any("Aquí tienes" in t for t in text_parts)
    assert len(a2ui_payloads) == 1
    assert a2ui_payloads[0] == sample_a2ui_json

    # 5. Convertir a A2uiPart para transporte
    part = to_a2ui_part(a2ui_payloads[0])
    assert isinstance(part, A2uiPart)
    assert part.mime == MIME_A2UI
    assert part.data == sample_a2ui_json
    # Serializa a JSON sin error
    s = part.to_json_string()
    assert json.loads(s) == sample_a2ui_json

  def test_flujo_completo_tags(self, sample_a2ui_json):
    """Flujo completo en modo system prompt + tags (sin tool)."""
    builder = ClaudeA2uiPromptBuilder(version="0.9")
    system_prompt = builder.build(role_description="Agente de UI.")
    catalog = builder.get_catalog()
    parser = ClaudeStreamParser(catalog=catalog)

    # Simular stream con texto + bloque <a2ui-json>
    payload = json.dumps(sample_a2ui_json)
    chunks = [
        "Aquí tienes:\n",
        "<a2ui-json>",
        payload,
        "</a2ui-json>",
        "\n¿Quieres más?",
    ]
    events = [
        _FakeDeltaEvent(type="content_block_delta", delta=_FakeTextDelta(ch), index=0)
        for ch in chunks
    ]

    text_parts: list[str] = []
    a2ui_payloads: list = []
    for event in events:
      for part in parser.process_event(event):
        if part.text:
          text_parts.append(part.text)
        if part.a2ui_json is not None:
          a2ui_payloads.append(part.a2ui_json)

    assert system_prompt
    assert a2ui_payloads, "Debe emitir al menos un payload A2UI"
    # El payload emitido debe ser igual al inyectado
    assert a2ui_payloads[0] == sample_a2ui_json


class TestEndToEndEstructura:
  """Verifica que la API pública expone todo lo necesario."""

  def test_imports_publicos_disponibles(self):
    import anthropic_a2ui as aa

    for name in [
        "ClaudeA2uiPromptBuilder",
        "ClaudeStreamParser",
        "create_a2ui_tool",
        "validate_tool_input",
        "make_parser_for_tool",
        "to_a2ui_part",
        "to_a2a_datapart",
        "parse_a2ui_part_json",
        "A2uiPart",
        "MIME_A2UI",
        "TOOL_NAME",
        "TOOL_DESCRIPTION",
        "SUPPORTED_VERSIONS",
        "DEFAULT_VERSION",
        "__version__",
    ]:
      assert hasattr(aa, name), f"Falta {name} en la API pública"

  def test_version_es_string(self):
    import anthropic_a2ui as aa

    assert isinstance(aa.__version__, str)
    assert aa.__version__.count(".") >= 2
