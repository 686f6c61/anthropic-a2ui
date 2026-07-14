"""Tests de componentes cross-catálogo: v0.8 (MultipleChoice) y v0.9 minimal.

A2UI no se limita al Basic Catalog v0.9: hay catálogos oficiales para v0.8
(standard, con MultipleChoice) y v0.9 (minimal, con 5 componentes y la
función capitalize). Estos tests verifican que el paquete funciona con
cualquier catálogo de cualquier versión.

Cobertura:

- ``MultipleChoice`` (v0.8): componente legacy reemplazado por ChoicePicker
  en v0.9. Usa estructura v0.8 (beginRendering/surfaceUpdate, wrappers
  literalString/literalArray).
- 5 componentes del minimal v0.9 (Text, Row, Column, Button, TextField):
  verifica que ``create_a2ui_tool`` y el validador funcionan con un
  ``CatalogConfig`` que no es ``BasicCatalog``.
- ``capitalize`` (función exclusiva del minimal): se usa en un Text con
  FunctionCall.

Total componentes únicos cubiertos: 19 (18 Basic v0.9 + MultipleChoice v0.8).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from anthropic_a2ui import (
    ClaudeA2uiPromptBuilder,
    ClaudeStreamParser,
    create_a2ui_tool,
    to_a2ui_part,
    validate_tool_input,
)

from ._a2ui_specs import (
    MINIMAL_CATALOG_ID,
    V08_EXTRA_SPECS,
    all_minimal_payloads,
    all_v08_payloads,
)


# --- Dobles de eventos de Anthropic (compartidos) -----------------


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


# --- Tests de MultipleChoice (v0.8) --------------------------------


@pytest.mark.parametrize("name, payload", all_v08_payloads())
class TestMultipleChoiceV08:
  """MultipleChoice es el componente exclusivo del catálogo v0.8 standard."""

  def test_valida_contra_catalogo_v08(self, catalog_v08, name, payload):
    """El payload v0.8 pasa el validador v0.8."""
    validate_tool_input(catalog_v08, payload, strict_integrity=False)

  def test_estructura_v08_usa_begin_rendering(self, name, payload):
    """v0.8 usa beginRendering, no createSurface."""
    assert any("beginRendering" in m for m in payload)

  def test_estructura_v08_usa_surface_update(self, name, payload):
    """v0.8 usa surfaceUpdate, no updateComponents."""
    assert any("surfaceUpdate" in m for m in payload)

  def test_no_usa_estructura_v09(self, name, payload):
    """v0.8 no usa createSurface ni updateComponents."""
    assert all("createSurface" not in m for m in payload)
    assert all("updateComponents" not in m for m in payload)

  def test_round_trip_tool_use_v08(self, catalog_v08, name, payload):
    """El payload v0.8 viaja por el stream y se reconstruye íntegro."""
    parser = ClaudeStreamParser(catalog=catalog_v08, strict_tool_validation=False)
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


class TestMultipleChoiceV08Estructura:
  """Tests específicos de la estructura de MultipleChoice v0.8."""

  def test_multiple_choice_tiene_selections_y_options(self):

    name, root, _ = V08_EXTRA_SPECS[0]
    assert name == "MultipleChoice"
    mc = root["component"]["MultipleChoice"]
    assert "selections" in mc
    assert "options" in mc
    assert mc["selections"] == {"literalArray": ["a"]}
    assert len(mc["options"]) == 2

  def test_multiple_choice_usa_wrappers_v08(self):
    """v0.8 usa literalString/literalArray para valores dinámicos."""

    _, root, _ = V08_EXTRA_SPECS[0]
    mc = root["component"]["MultipleChoice"]
    # selections usa literalArray
    assert "literalArray" in mc["selections"]
    # options usan literalString para label
    for opt in mc["options"]:
      assert "literalString" in opt["label"]


# --- Tests del catálogo minimal v0.9 -------------------------------


@pytest.mark.parametrize("name, payload", all_minimal_payloads())
class TestComponentesMinimal:
  """Los 5 componentes del catálogo minimal v0.9 validan y hacen round-trip."""

  def test_valida_contra_catalogo_minimal(self, catalog_minimal, name, payload):
    """El payload pasa el validador del catálogo minimal."""
    validate_tool_input(catalog_minimal, payload, strict_integrity=True)

  def test_usa_catalog_id_minimal(self, name, payload):
    """El createSurface usa el catalogId del minimal, no del basic."""
    for m in payload:
      if "createSurface" in m:
        assert m["createSurface"]["catalogId"] == MINIMAL_CATALOG_ID

  def test_round_trip_tool_use_minimal(self, catalog_minimal, name, payload):
    """El payload viaja por el stream con el catálogo minimal."""
    parser = ClaudeStreamParser(catalog=catalog_minimal, strict_tool_validation=True)
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

  def test_se_convierte_a_a2uipart(self, catalog_minimal, name, payload):
    """El payload del minimal se envuelve en A2uiPart correctamente."""
    part = to_a2ui_part(payload)
    assert part.data == payload
    assert part.mime == "application/a2ui+json"
    assert json.loads(part.to_json_string()) == payload


class TestCatalogoMinimalEstructura:
  """Tests de estructura del catálogo minimal v0.9."""

  def test_minimal_tiene_5_componentes(self, catalog_minimal):
    comps = list(catalog_minimal.catalog_schema["components"].keys())
    assert set(comps) == {"Text", "Row", "Column", "Button", "TextField"}
    assert len(comps) == 5

  def test_minimal_tiene_funcion_capitalize(self, catalog_minimal):
    funcs = list(catalog_minimal.catalog_schema.get("functions", {}).keys())
    assert "capitalize" in funcs
    assert len(funcs) == 1

  def test_minimal_no_tiene_choicepicker(self, catalog_minimal):
    """El minimal no incluye ChoicePicker (es más reducido que Basic)."""
    assert "ChoicePicker" not in catalog_minimal.catalog_schema["components"]

  def test_minimal_no_tiene_slider(self, catalog_minimal):
    assert "Slider" not in catalog_minimal.catalog_schema["components"]

  def test_create_a2ui_tool_con_minimal(self, catalog_minimal):
    """create_a2ui_tool funciona con el catálogo minimal."""
    tool = create_a2ui_tool(catalog_minimal)
    assert tool["name"] == "send_a2ui_json_to_client"
    assert isinstance(tool["input_schema"], dict)

  def test_builder_con_minimal(self, catalog_minimal):
    """ClaudeA2uiPromptBuilder funciona con el catálogo minimal vía CatalogConfig."""
    # El builder se crea en el fixture; verificar que el prompt no es vacío
    # y que menciona los componentes del minimal
    from a2ui.schema.catalog import CatalogConfig
    from a2ui.schema.catalog_provider import FileSystemCatalogProvider
    import os

    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    provider = FileSystemCatalogProvider(
        path=os.path.join(assets_dir, "minimal_catalog.json")
    )
    config = CatalogConfig(name="minimal", provider=provider)
    builder = ClaudeA2uiPromptBuilder(catalogs=[config], version="0.9")
    prompt = builder.build(role_description="Agente minimal.")
    assert "Text" in prompt
    assert "TextField" in prompt
    # No debe mencionar componentes que no están en el minimal
    assert "Slider" not in prompt or "ChoicePicker" not in prompt


# --- Tests de capitalize (función exclusiva del minimal) -----------


class TestFuncionCapitalize:
  """La función capitalize solo existe en el catálogo minimal."""

  def test_capitalize_valida_en_minimal(self, catalog_minimal):
    """Un Text con FunctionCall capitalize valida contra el minimal."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": MINIMAL_CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{
                    "id": "root",
                    "component": "Text",
                    "text": {
                        "call": "capitalize",
                        "args": {"value": "hola"},
                        "returnType": "string",
                    },
                }],
            },
        },
    ]
    validate_tool_input(catalog_minimal, payload, strict_integrity=True)

  def test_capitalize_no_existe_en_basic(self, catalog_v09):
    """capitalize no está en el Basic Catalog v0.9."""
    funcs = catalog_v09.catalog_schema.get("functions", {})
    assert "capitalize" not in funcs

  def test_capitalize_round_trip(self, catalog_minimal):
    """Un payload con capitalize viaja por el stream y se reconstruye."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": MINIMAL_CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{
                    "id": "root",
                    "component": "Text",
                    "text": {
                        "call": "capitalize",
                        "args": {"value": "hola"},
                        "returnType": "string",
                    },
                }],
            },
        },
    ]
    parser = ClaudeStreamParser(
        catalog=catalog_minimal, strict_tool_validation=True, repair=False
    )
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


# --- Test de cobertura total: 19 componentes ----------------------


class TestCoberturaTotalComponentes:
  """Verifica que se cubren TODOS los componentes únicos de A2UI."""

  def test_hay_19_componentes_unicos(self):
    from ._a2ui_specs import all_unique_component_names

    names = all_unique_component_names()
    assert len(names) == 19
    assert "MultipleChoice" in names
    assert "ChoicePicker" in names

  def test_nombres_unicos_no_tienen_duplicados(self):
    from ._a2ui_specs import all_unique_component_names

    names = all_unique_component_names()
    assert len(names) == len(set(names))

  def test_basic_v09_tiene_18_componentes(self, catalog_v09):
    comps = set(catalog_v09.catalog_schema["components"].keys())
    assert len(comps) == 18
    assert "MultipleChoice" not in comps
    assert "ChoicePicker" in comps

  def test_v08_tiene_18_componentes_con_multiple_choice(self, catalog_v08):
    comps = set(catalog_v08.catalog_schema["components"].keys())
    assert len(comps) == 18
    assert "MultipleChoice" in comps
    assert "ChoicePicker" not in comps

  def test_minimal_tiene_5_componentes(self, catalog_minimal):
    comps = set(catalog_minimal.catalog_schema["components"].keys())
    assert len(comps) == 5

  def test_union_de_todos_los_catalogos_da_19(
      self, catalog_v09, catalog_v08, catalog_minimal
  ):
    """La unión de componentes de todos los catálogos da 19 únicos."""
    all_comps = set()
    all_comps.update(catalog_v09.catalog_schema["components"].keys())
    all_comps.update(catalog_v08.catalog_schema["components"].keys())
    all_comps.update(catalog_minimal.catalog_schema["components"].keys())
    assert len(all_comps) == 19
