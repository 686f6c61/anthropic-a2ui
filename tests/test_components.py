"""Tests parametrizados por cada componente del Basic Catalog de A2UI.

Cubre los 18 componentes: Text, Image, Icon, Video, AudioPlayer, Row, Column,
List, Card, Tabs, Modal, Divider, Button, TextField, CheckBox, ChoicePicker,
Slider y DateTimeInput.

Para cada componente se verifica:

1. **Validación**: el payload pasa ``A2uiValidator.validate``.
2. **Round-trip tool use**: el payload viaja por un stream simulado de
   Anthropic (``InputJSONDelta``) y el ``ClaudeStreamParser`` lo emite
   íntegro.
3. **Transporte**: el ``ResponsePart`` se convierte a ``A2uiPart`` con el
   MIME estándar.
4. **Tags**: el payload viaja como bloque ``<a2ui-json>`` en texto y el
   parser de tags lo reconoce.

Estos tests garantizan que cualquier componente del catálogo básico puede
generarse con Claude, validarse y entregarse al renderer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from anthropic_a2ui import (
    A2uiPart,
    ClaudeStreamParser,
    MIME_A2UI,
    create_a2ui_tool,
    to_a2ui_part,
    validate_tool_input,
)

from ._a2ui_specs import COMPONENT_SPECS, all_payloads, build_payload


# --- Dobles de eventos de Anthropic (mismos que test_stream_parser) ---


@dataclass
class _TextDelta:
  text: str
  type: str = "text_delta"


@dataclass
class _InputJSONDelta:
  partial_json: str
  type: str = "input_json_delta"


@dataclass
class _DeltaEvent:
  type: str
  delta: Any
  index: int = 0


@dataclass
class _Block:
  type: str
  name: str = ""


@dataclass
class _BlockStart:
  type: str
  index: int
  content_block: Any


@dataclass
class _BlockStop:
  type: str
  index: int


# --- Tests de validación por componente ----------------------------


@pytest.mark.parametrize("name, payload", all_payloads())
class TestValidacionPorComponente:
  """Cada componente del catálogo debe validar contra el esquema A2UI."""

  def test_valida_con_strict_integrity(self, catalog_v09, name, payload):
    """El payload pasa el validador con comprobaciones de integridad."""
    validate_tool_input(catalog_v09, payload, strict_integrity=True)

  def test_valida_sin_strict_integrity(self, catalog_v09, name, payload):
    """El payload pasa sin comprobaciones de integridad (más laxo)."""
    validate_tool_input(catalog_v09, payload, strict_integrity=False)

  def test_tiene_create_surface(self, name, payload):
    """El payload incluye un mensaje createSurface."""
    assert any("createSurface" in m for m in payload)

  def test_tiene_update_components(self, name, payload):
    """El payload incluye un mensaje updateComponents."""
    assert any("updateComponents" in m for m in payload)

  def test_tiene_component_root(self, name, payload):
    """El payload tiene un componente con id='root'."""
    for m in payload:
      if "updateComponents" in m:
        ids = [c["id"] for c in m["updateComponents"]["components"]]
        assert "root" in ids

  def test_catalog_id_es_el_basico(self, name, payload):
    """El createSurface usa el catalogId del Basic Catalog."""
    for m in payload:
      if "createSurface" in m:
        assert m["createSurface"]["catalogId"] == (
            "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
        )


# --- Tests de round-trip tool use por componente -------------------


@pytest.mark.parametrize("name, payload", all_payloads())
class TestRoundTripToolUsePorComponente:
  """Cada componente viaja por el stream de Anthropic (modo tool) y se
  reconstruye íntegro vía ``ClaudeStreamParser``."""

  def test_tool_use_emite_payload_completo(self, catalog_v09, name, payload):
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=True)
    raw = json.dumps(payload)
    parts: list = []
    parts.extend(
        parser.process_event(
            _BlockStart(
                "content_block_start", 1, _Block("tool_use", "send_a2ui_json_to_client")
            )
        )
    )
    parts.extend(
        parser.process_event(
            _DeltaEvent("content_block_delta", _InputJSONDelta(raw), 1)
        )
    )
    parts.extend(parser.process_event(_BlockStop("content_block_stop", 1)))
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert len(a2ui_parts) == 1
    assert a2ui_parts[0].a2ui_json == payload

  def test_tool_use_fragmentado_en_dos_deltas(self, catalog_v09, name, payload):
    """El JSON fragmentado en varios deltas se reconstruye correctamente."""
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=False)
    raw = json.dumps(payload)
    mid = len(raw) // 2
    parts: list = []
    parts.extend(
        parser.process_event(
            _BlockStart(
                "content_block_start", 1, _Block("tool_use", "send_a2ui_json_to_client")
            )
        )
    )
    parts.extend(
        parser.process_event(
            _DeltaEvent("content_block_delta", _InputJSONDelta(raw[:mid]), 1)
        )
    )
    parts.extend(
        parser.process_event(
            _DeltaEvent("content_block_delta", _InputJSONDelta(raw[mid:]), 1)
        )
    )
    parts.extend(parser.process_event(_BlockStop("content_block_stop", 1)))
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert len(a2ui_parts) == 1
    assert a2ui_parts[0].a2ui_json == payload

  def test_payload_se_convierte_a_a2uipart(self, catalog_v09, name, payload):
    """El payload emitido por el parser se envuelve en A2uiPart con MIME."""
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=True)
    raw = json.dumps(payload)
    parts: list = []
    parts.extend(
        parser.process_event(
            _BlockStart(
                "content_block_start", 1, _Block("tool_use", "send_a2ui_json_to_client")
            )
        )
    )
    parts.extend(
        parser.process_event(
            _DeltaEvent("content_block_delta", _InputJSONDelta(raw), 1)
        )
    )
    parts.extend(parser.process_event(_BlockStop("content_block_stop", 1)))
    a2ui_json = [p for p in parts if p.a2ui_json is not None][0].a2ui_json
    part = to_a2ui_part(a2ui_json)
    assert isinstance(part, A2uiPart)
    assert part.mime == MIME_A2UI
    assert part.data == payload
    # Serializa y re-parsea sin error
    assert json.loads(part.to_json_string()) == payload


# --- Tests de modo tags por componente -----------------------------


# --- Tests de modo tags por componente -----------------------------
#
# Nota: el ``A2uiStreamParser`` reordena los componentes para renderizado
# incremental (top-down: padre antes que hijo, o viceversa según el flujo
# de streaming). Por eso los tests de modo tags comparan de forma
# semántica (mismo conjunto de componentes y mismos mensajes), no por
# orden exacto de la lista.


def _normalizar(payload):
  """Normaliza un payload para comparación semántica.

  Ordena los componentes por ``id`` dentro de cada ``updateComponents`` y
  ordena los mensajes por tipo (createSurface antes que updateComponents).
  """
  norm = []
  for m in payload:
    m_copy = dict(m)
    if "updateComponents" in m_copy:
      uc = dict(m_copy["updateComponents"])
      uc["components"] = sorted(uc["components"], key=lambda c: c["id"])
      m_copy["updateComponents"] = uc
    norm.append(m_copy)
  # Ordenar por tipo de mensaje
  norm.sort(key=lambda m: list(m.keys())[1] if len(m) > 1 else list(m.keys())[0])
  return norm


@pytest.mark.parametrize("name, payload", all_payloads())
class TestModoTagsPorComponente:
  """Cada componente viaja como bloque ``<a2ui-json>`` en texto y el parser
  de tags lo reconoce."""

  def test_bloque_tags_emite_payload(self, catalog_v09, name, payload):
    parser = ClaudeStreamParser(catalog=catalog_v09)
    raw = json.dumps(payload)
    chunks = ["<a2ui-json>", raw, "</a2ui-json>"]
    parts: list = []
    for ch in chunks:
      parts.extend(
          parser.process_event(_DeltaEvent("content_block_delta", _TextDelta(ch), 0))
      )
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert a2ui_parts, f"El componente {name} no emitió payload en modo tags"
    # Comparación semántica (el parser puede reordenar componentes)
    assert _normalizar(a2ui_parts[0].a2ui_json) == _normalizar(payload)

  def test_bloque_tags_con_texto_alrededor(self, catalog_v09, name, payload):
    """Texto antes y después del bloque no interfiere con la extracción."""
    parser = ClaudeStreamParser(catalog=catalog_v09)
    raw = json.dumps(payload)
    chunks = ["Aquí tienes:\n", "<a2ui-json>", raw, "</a2ui-json>", "\n¿Bien?"]
    parts: list = []
    for ch in chunks:
      parts.extend(
          parser.process_event(_DeltaEvent("content_block_delta", _TextDelta(ch), 0))
      )
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert a2ui_parts
    assert _normalizar(a2ui_parts[0].a2ui_json) == _normalizar(payload)


# --- Test de cobertura: los 18 componentes están definidos ---------


class TestCoberturaComponentes:
  """Verifica que COMPONENT_SPECS cubre los 18 componentes del catálogo."""

  def test_hay_18_especificaciones(self):
    assert len(COMPONENT_SPECS) == 18

  def test_nombres_son_unicos(self):
    names = [s[0] for s in COMPONENT_SPECS]
    assert len(names) == len(set(names))

  def test_cubre_todos_los_componentes_del_catalogo(self, catalog_v09):
    """Los nombres de COMPONENT_SPECS coinciden con los del catálogo."""
    catalog_components = set(catalog_v09.catalog_schema["components"].keys())
    spec_names = {s[0] for s in COMPONENT_SPECS}
    assert spec_names == catalog_components

  def test_todas_las_specs_construyen_payloads_validos(self, catalog_v09):
    """Cada spec genera un payload que valida."""
    for spec in COMPONENT_SPECS:
      payload = build_payload(spec)
      validate_tool_input(catalog_v09, payload, strict_integrity=True)
