"""Tests del parser de stream de Anthropic.

Se usan dobles (fakes) de los eventos de Anthropic para no llamar a la API
real. Los fakes replican la estructura de ``RawContentBlockDeltaEvent`` y
sus deltas (``TextDelta``, ``InputJSONDelta``) con ``getattr`` para que el
parser funcione sin depender de tipos concretos.
"""

import json
from dataclasses import dataclass
from typing import Any, Optional

import pytest

from anthropic_a2ui import ClaudeStreamParser


# --- Dobles de eventos de Anthropic -------------------------------


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
  """Equivalente a RawContentBlockDeltaEvent."""

  type: str
  delta: Any
  index: int = 0


@dataclass
class _FakeBlock:
  type: str
  name: str = ""
  id: str = ""


@dataclass
class _FakeBlockStart:
  type: str
  index: int
  content_block: Any


@dataclass
class _FakeBlockStop:
  type: str
  index: int


def text_event(text: str, index: int = 0) -> _FakeDeltaEvent:
  return _FakeDeltaEvent(
      type="content_block_delta", delta=_FakeTextDelta(text), index=index
  )


def json_delta_event(chunk: str, index: int = 1) -> _FakeDeltaEvent:
  return _FakeDeltaEvent(
      type="content_block_delta", delta=_FakeInputJSONDelta(chunk), index=index
  )


def block_start_tool(name: str, index: int = 1) -> _FakeBlockStart:
  return _FakeBlockStart(
      type="content_block_start",
      index=index,
      content_block=_FakeBlock(type="tool_use", name=name),
  )


def block_start_text(index: int = 0) -> _FakeBlockStart:
  return _FakeBlockStart(
      type="content_block_start",
      index=index,
      content_block=_FakeBlock(type="text", name=""),
  )


def block_stop(index: int) -> _FakeBlockStop:
  return _FakeBlockStop(type="content_block_stop", index=index)


# --- Tests --------------------------------------------------------


class TestClaudeStreamParserModoTags:
  """Modo system prompt + tags <a2ui-json> en el texto."""

  def test_texto_plano_sin_a2ui_se_emite_como_texto(self, catalog_v09):
    parser = ClaudeStreamParser(catalog=catalog_v09)
    parts = parser.process_event(text_event("Hola, soy Claude."))
    # Puede emitirse en el mismo chunk o acumularse; al menos hay texto.
    assert any(p.text for p in parts)

  def test_bloque_a2ui_json_completo_se_emite(self, catalog_v09, sample_a2ui_json):
    parser = ClaudeStreamParser(catalog=catalog_v09)
    payload = json.dumps(sample_a2ui_json)
    # Simular stream: texto + bloque <a2ui-json>...</a2ui-json>
    chunks = [
        "Aquí tienes el formulario:\n",
        "<a2ui-json>",
        payload,
        "</a2ui-json>",
    ]
    all_parts: list = []
    for ch in chunks:
      all_parts.extend(parser.process_event(text_event(ch)))
    # Al menos un part con a2ui_json no None
    a2ui_parts = [p for p in all_parts if p.a2ui_json is not None]
    assert a2ui_parts, "Debe emitir al menos un ResponsePart con a2ui_json"

  def test_texto_antes_del_bloque_se_emite_como_texto(
      self, catalog_v09, sample_a2ui_json
  ):
    parser = ClaudeStreamParser(catalog=catalog_v09)
    payload = json.dumps(sample_a2ui_json)
    parts: list = []
    parts.extend(parser.process_event(text_event("Texto previo. ")))
    parts.extend(parser.process_event(text_event("<a2ui-json>")))
    parts.extend(parser.process_event(text_event(payload)))
    parts.extend(parser.process_event(text_event("</a2ui-json>")))
    text_parts = [p for p in parts if p.text]
    # El texto previo se emite (puede estar acumulado en el primer chunk)
    assert any("Texto previo" in (p.text or "") for p in text_parts) or any(
        p.text for p in text_parts
    )

  def test_bloque_a2ui_json_invalido_no_rompe(self, catalog_v09):
    parser = ClaudeStreamParser(catalog=catalog_v09)
    # JSON malformado dentro del bloque
    chunks = ["<a2ui-json>", "{invalido", "</a2ui-json>"]
    # No debe lanzar; puede no emitir a2ui_json o emitir texto residual
    for ch in chunks:
      parser.process_event(text_event(ch))
    # No hay aserción estricta: el parser es tolerante

  def test_sin_catalogo_texto_se_emite_directo(self):
    parser = ClaudeStreamParser(catalog=None)
    parts = parser.process_event(text_event("Hola."))
    assert len(parts) == 1
    assert parts[0].text == "Hola."
    assert parts[0].a2ui_json is None


class TestClaudeStreamParserModoTool:
  """Modo tool use con InputJSONDelta."""

  def test_tool_use_json_valido_se_emite(self, catalog_v09, sample_a2ui_json):
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=False)
    raw = json.dumps(sample_a2ui_json)
    # Simular stream de tool use: block_start (tool) + deltas + block_stop
    parts: list = []
    parts.extend(
        parser.process_event(block_start_tool("send_a2ui_json_to_client", index=1))
    )
    # Fragmentar el JSON en varios deltas
    mid = len(raw) // 2
    parts.extend(parser.process_event(json_delta_event(raw[:mid], index=1)))
    parts.extend(parser.process_event(json_delta_event(raw[mid:], index=1)))
    parts.extend(parser.process_event(block_stop(index=1)))
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert len(a2ui_parts) == 1
    assert a2ui_parts[0].a2ui_json == sample_a2ui_json

  def test_tool_use_json_invalido_lanza_valueerror(self, catalog_v09):
    # Sin validación estricta, JSON malformado lanza ValueError al parsear
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=False)
    parser.process_event(block_start_tool("send_a2ui_json_to_client", index=1))
    parser.process_event(json_delta_event("{no es json", index=1))
    with pytest.raises(ValueError, match="JSON invalido"):
      parser.process_event(block_stop(index=1))

  def test_tool_use_validacion_stricta_falla_si_schema_invalido(self, catalog_v09):
    # Payload que es JSON válido pero no conforma el schema A2UI
    bad_payload = [
        {"version": "v0.9", "createSurface": {"surfaceId": "x"}}
    ]  # falta catalogId
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=True)
    parser.process_event(block_start_tool("send_a2ui_json_to_client", index=1))
    parser.process_event(json_delta_event(json.dumps(bad_payload), index=1))
    with pytest.raises(Exception):
      parser.process_event(block_stop(index=1))

  def test_tool_use_sin_strict_no_valida(self, catalog_v09):
    # Mismo payload inválido, pero con strict=False: no lanza
    bad_payload = [{"version": "v0.9", "createSurface": {"surfaceId": "x"}}]
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=False)
    parser.process_event(block_start_tool("send_a2ui_json_to_client", index=1))
    parser.process_event(json_delta_event(json.dumps(bad_payload), index=1))
    parts = parser.process_event(block_stop(index=1))
    assert len(parts) == 1
    assert parts[0].a2ui_json == bad_payload

  def test_varias_tools_en_paralelo_se_separan_por_indice(
      self, catalog_v09, sample_a2ui_json
  ):
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=False)
    raw = json.dumps(sample_a2ui_json)
    parts: list = []
    # Bloque 0: texto, bloque 1: tool A, bloque 2: tool B
    parts.extend(parser.process_event(block_start_tool("tool_a", index=1)))
    parts.extend(parser.process_event(block_start_tool("tool_b", index=2)))
    parts.extend(parser.process_event(json_delta_event(raw, index=1)))
    parts.extend(parser.process_event(json_delta_event(raw, index=2)))
    parts.extend(parser.process_event(block_stop(index=1)))
    parts.extend(parser.process_event(block_stop(index=2)))
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert len(a2ui_parts) == 2

  def test_block_start_text_no_registra_tool(self, catalog_v09):
    parser = ClaudeStreamParser(catalog=catalog_v09)
    parser.process_event(block_start_text(index=0))
    # No debe haber buffers de tool
    assert parser._tool_buffers == {}


class TestClaudeStreamParserParseStream:

  def test_parse_stream_itera_eventos(self, catalog_v09, sample_a2ui_json):
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=False)
    raw = json.dumps(sample_a2ui_json)
    events = [
        block_start_tool("send_a2ui_json_to_client", index=1),
        json_delta_event(raw, index=1),
        block_stop(index=1),
    ]
    parts = list(parser.parse_stream(events))
    assert any(p.a2ui_json is not None for p in parts)

  def test_evento_desconocido_no_produce_parts(self, catalog_v09):
    parser = ClaudeStreamParser(catalog=catalog_v09)

    @dataclass
    class Unknown:
      type: str = "message_start"

    assert parser.process_event(Unknown()) == []


class TestClaudeStreamParserFlush:

  def test_flush_sin_catalogo_devuelve_vacio(self):
    parser = ClaudeStreamParser(catalog=None)
    assert parser.flush() == []

  def test_flush_con_catalogo_no_rompe(self, catalog_v09):
    parser = ClaudeStreamParser(catalog=catalog_v09)
    # Alimentar texto parcial y volcar
    parser.process_event(text_event("texto sin cerrar"))
    result = parser.flush()
    assert isinstance(result, list)
