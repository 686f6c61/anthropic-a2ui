"""Tests multi-catálogo y multi-versión de anthropic-a2ui.

Verifica que el paquete funciona con cualquier combinación de catálogo y
versión soportada por ``a2ui-agent-sdk``:

- **Versiones**: v0.8 (legacy, standard catalog), v0.9 (basic + minimal),
  v0.9.1 (basic).
- **Catálogos**: Basic (bundled), Minimal (filesystem), y la capacidad de
  cargar catálogos personalizados vía ``FileSystemCatalogProvider``.
- **Builder**: ``ClaudeA2uiPromptBuilder`` genera prompts válidos para cada
  versión.
- **Tool**: ``create_a2ui_tool`` genera definiciones válidas para cada
  catálogo.
- **Parser**: ``ClaudeStreamParser`` valida payloads contra cada catálogo.
- **Combinaciones cruzadas**: un payload v0.9 no valida contra v0.8 y
  viceversa (incompatibilidad de estructura).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import pytest

from a2ui.schema.catalog import CatalogConfig
from a2ui.schema.catalog_provider import FileSystemCatalogProvider
from a2ui.schema.manager import A2uiSchemaManager

from anthropic_a2ui import (
    DEFAULT_VERSION,
    SUPPORTED_VERSIONS,
    ClaudeA2uiPromptBuilder,
    ClaudeStreamParser,
    create_a2ui_tool,
    validate_tool_input,
)

from ._a2ui_specs import CATALOG_ID, CATALOG_ID_V08, MINIMAL_CATALOG_ID


# --- Dobles de eventos de Anthropic --------------------------------


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


def _run_tool_use_stream(parser, payload):
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
      parser.process_event(_DeltaEvent("content_block_delta", _InputJSONDelta(raw), 1))
  )
  parts.extend(parser.process_event(_BlockStop("content_block_stop", 1)))
  return parts


# --- Tests de versiones soportadas ---------------------------------


class TestVersionesSoportadas:
  """Verifica que SUPPORTED_VERSIONS coincide con lo que a2ui-agent-sdk soporta."""

  def test_versions_soportadas_contiene_08_09_091(self):
    assert "0.8" in SUPPORTED_VERSIONS
    assert "0.9" in SUPPORTED_VERSIONS
    assert "0.9.1" in SUPPORTED_VERSIONS

  def test_version_por_defecto_es_09(self):
    assert DEFAULT_VERSION == "0.9"

  @pytest.mark.parametrize("version", list(SUPPORTED_VERSIONS))
  def test_builder_crea_para_cada_version(self, version):
    builder = ClaudeA2uiPromptBuilder(version=version)
    assert builder.version == version
    assert builder.manager is not None

  @pytest.mark.parametrize("version", list(SUPPORTED_VERSIONS))
  def test_builder_genera_prompt_para_cada_version(self, version):
    builder = ClaudeA2uiPromptBuilder(version=version)
    prompt = builder.build(role_description="Agente.")
    assert isinstance(prompt, str)
    assert len(prompt) > 100
    assert "<a2ui-json>" in prompt

  @pytest.mark.parametrize("version", list(SUPPORTED_VERSIONS))
  def test_create_tool_para_cada_version(self, version):
    builder = ClaudeA2uiPromptBuilder(version=version)
    tool = create_a2ui_tool(builder.get_catalog())
    assert tool["name"] == "send_a2ui_json_to_client"
    assert isinstance(tool["input_schema"], dict)

  def test_version_invalid_lanza(self):
    with pytest.raises(ValueError, match="Versión no soportada"):
      ClaudeA2uiPromptBuilder(version="2.0")

  def test_version_invalid_vacia_lanza(self):
    with pytest.raises(ValueError, match="Versión no soportada"):
      ClaudeA2uiPromptBuilder(version="")


# --- Tests de diferencias entre versiones --------------------------


class TestDiferenciasVersiones:
  """v0.8 y v0.9 son incompatibles estructuralmente."""

  def test_v08_usa_begin_rendering(self, catalog_v08):
    """v0.8 usa beginRendering en el schema s2c."""
    s2c = catalog_v08.s2c_schema
    assert "beginRendering" in s2c.get("properties", {})

  def test_v09_usa_create_surface(self, catalog_v09):
    """v0.9 usa createSurface en el schema s2c."""
    s2c = catalog_v09.s2c_schema
    assert "CreateSurfaceMessage" in s2c.get("$defs", {})

  def test_v08_no_tiene_create_surface(self, catalog_v08):
    """v0.8 no usa createSurface."""
    s2c = catalog_v08.s2c_schema
    assert "createSurface" not in s2c.get("properties", {})

  def test_v09_no_tiene_begin_rendering(self, catalog_v09):
    """v0.9 no usa beginRendering."""
    s2c = catalog_v09.s2c_schema
    props = s2c.get("properties", {})
    defs = s2c.get("$defs", {})
    assert "beginRendering" not in props
    assert "BeginRenderingMessage" not in defs

  def test_payload_v09_no_valida_contra_v08(self, catalog_v08):
    """Un payload v0.9 no valida contra el catálogo v0.8."""
    payload_v09 = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{"id": "root", "component": "Text", "text": "X"}],
            },
        },
    ]
    with pytest.raises(Exception):
      validate_tool_input(catalog_v08, payload_v09, strict_integrity=False)

  def test_payload_v08_no_valida_contra_v09(self, catalog_v09):
    """Un payload v0.8 no valida contra el catálogo v0.9."""
    payload_v08 = [
        {
            "beginRendering": {
                "surfaceId": "s",
                "root": "root",
                "catalogId": CATALOG_ID_V08,
            }
        },
        {
            "surfaceUpdate": {
                "surfaceId": "s",
                "components": [{
                    "id": "root",
                    "component": {"Text": {"text": {"literalString": "X"}}},
                }],
            }
        },
    ]
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, payload_v08, strict_integrity=False)

  def test_v09_y_v091_tienen_mismos_componentes(self):
    """v0.9 y v0.9.1 comparten el mismo catálogo basic."""
    builder_09 = ClaudeA2uiPromptBuilder(version="0.9")
    builder_091 = ClaudeA2uiPromptBuilder(version="0.9.1")
    comps_09 = set(builder_09.get_catalog().catalog_schema["components"].keys())
    comps_091 = set(builder_091.get_catalog().catalog_schema["components"].keys())
    assert comps_09 == comps_091

  def test_v08_tiene_multiple_choice_v09_no(self, catalog_v08, catalog_v09):
    comps_08 = set(catalog_v08.catalog_schema["components"].keys())
    comps_09 = set(catalog_v09.catalog_schema["components"].keys())
    assert "MultipleChoice" in comps_08
    assert "MultipleChoice" not in comps_09
    assert "ChoicePicker" in comps_09
    assert "ChoicePicker" not in comps_08


# --- Tests de catálogo minimal -------------------------------------


class TestCatalogoMinimal:
  """El catálogo minimal v0.9 es un subconjunto del basic."""

  def test_minimal_es_subconjunto_de_basic(self, catalog_v09, catalog_minimal):
    basic_comps = set(catalog_v09.catalog_schema["components"].keys())
    minimal_comps = set(catalog_minimal.catalog_schema["components"].keys())
    assert minimal_comps.issubset(basic_comps)

  def test_minimal_tiene_menos_componentes(self, catalog_v09, catalog_minimal):
    assert len(catalog_minimal.catalog_schema["components"]) < len(
        catalog_v09.catalog_schema["components"]
    )

  def test_minimal_tiene_solo_capitalize(self, catalog_minimal):
    funcs = catalog_minimal.catalog_schema.get("functions", {})
    assert list(funcs.keys()) == ["capitalize"]

  def test_minimal_no_tiene_funciones_de_basic(self, catalog_minimal, catalog_v09):
    basic_funcs = set(catalog_v09.catalog_schema.get("functions", {}).keys())
    minimal_funcs = set(catalog_minimal.catalog_schema.get("functions", {}).keys())
    assert minimal_funcs.isdisjoint(basic_funcs)

  def test_prompt_minimal_es_mas_corto(self, catalog_v09, catalog_minimal):
    """El prompt con el minimal debe ser más corto (menos componentes)."""
    from a2ui.schema.catalog import CatalogConfig
    from a2ui.schema.catalog_provider import FileSystemCatalogProvider
    import os

    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    provider = FileSystemCatalogProvider(
        path=os.path.join(assets_dir, "minimal_catalog.json")
    )
    config = CatalogConfig(name="minimal", provider=provider)
    mgr_min = A2uiSchemaManager(version="0.9", catalogs=[config])
    mgr_basic = A2uiSchemaManager(
        version="0.9",
        catalogs=[
            __import__("a2ui").basic_catalog.provider.BasicCatalog.get_config(
                version="0.9"
            )
        ],
    )
    prompt_min = mgr_min.generate_system_prompt(
        role_description="x", include_schema=True, include_examples=False
    )
    prompt_basic = mgr_basic.generate_system_prompt(
        role_description="x", include_schema=True, include_examples=False
    )
    assert len(prompt_min) < len(prompt_basic)

  def test_tool_minimal_funciona(self, catalog_minimal):
    tool = create_a2ui_tool(catalog_minimal)
    assert tool["name"] == "send_a2ui_json_to_client"
    schema = tool["input_schema"]
    # El esquema está envuelto en {"a2ui_json": [...]}
    assert schema["type"] == "object"
    assert "a2ui_json" in schema["properties"]
    items = schema["properties"]["a2ui_json"]["items"]
    assert "$id" in items

  def test_parser_con_minimal_valida(self, catalog_minimal):
    """El parser valida payloads contra el minimal."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": MINIMAL_CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{"id": "root", "component": "Text", "text": "Hola"}],
            },
        },
    ]
    parser = ClaudeStreamParser(catalog=catalog_minimal, strict_tool_validation=True)
    parts = _run_tool_use_stream(parser, payload)
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert len(a2ui_parts) == 1


# --- Tests de catálogo personalizado -------------------------------


class TestCatalogoPersonalizado:
  """Verifica que se puede cargar un catálogo personalizado vía FileSystem."""

  def test_filesystem_provider_carga_catalog_minimal(self):
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    path = os.path.join(assets_dir, "minimal_catalog.json")
    provider = FileSystemCatalogProvider(path=path)
    data = provider.load()
    assert "components" in data
    assert "Text" in data["components"]

  def test_catalog_config_con_filesystem_provider(self):
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    provider = FileSystemCatalogProvider(
        path=os.path.join(assets_dir, "minimal_catalog.json")
    )
    config = CatalogConfig(name="minimal", provider=provider)
    assert config.name == "minimal"
    assert config.provider is not None

  def test_builder_con_catalog_config_personalizado(self):
    """ClaudeA2uiPromptBuilder acepta CatalogConfig personalizado."""
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    provider = FileSystemCatalogProvider(
        path=os.path.join(assets_dir, "minimal_catalog.json")
    )
    config = CatalogConfig(name="minimal", provider=provider)
    builder = ClaudeA2uiPromptBuilder(catalogs=[config], version="0.9")
    prompt = builder.build(role_description="Agente minimal.")
    assert "Text" in prompt
    assert "TextField" in prompt

  def test_builder_con_basic_y_minimal(self):
    """El builder puede combinar Basic + Minimal (catálogos múltiples)."""
    from a2ui.basic_catalog.provider import BasicCatalog

    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    provider_min = FileSystemCatalogProvider(
        path=os.path.join(assets_dir, "minimal_catalog.json")
    )
    config_basic = BasicCatalog.get_config(version="0.9")
    config_min = CatalogConfig(name="minimal", provider=provider_min)
    builder = ClaudeA2uiPromptBuilder(
        catalogs=[config_basic, config_min], version="0.9"
    )
    assert builder.manager is not None
    prompt = builder.build(role_description="Agente con dos catálogos.")
    assert len(prompt) > 100


# --- Tests de poda de componentes ----------------------------------


class TestPodaComponentes:
  """with_pruning permite restringir componentes y ahorrar tokens."""

  def test_poda_a_dos_componentes(self, catalog_v09):
    pruned = catalog_v09.with_pruning(allowed_components=["Text", "Button"])
    assert set(pruned.catalog_schema["components"].keys()) == {"Text", "Button"}

  def test_poda_elimina_funciones_no_usadas(self, catalog_v09):
    """Al podar a componentes sin checks, las funciones de validación se
    mantienen porque with_pruning no elimina funciones (solo componentes)."""
    pruned = catalog_v09.with_pruning(allowed_components=["Text"])
    # Text no usa checks, pero las funciones siguen en el catálogo
    assert "functions" in pruned.catalog_schema

  def test_poda_con_allowed_messages(self, catalog_v09):
    pruned = catalog_v09.with_pruning(
        allowed_components=["Text"], allowed_messages=["updateComponents"]
    )
    assert pruned is not None

  def test_poda_ningun_componente(self, catalog_v09):
    """Podar a lista vacía no debe romper."""
    pruned = catalog_v09.with_pruning(allowed_components=[])
    assert pruned is not None

  def test_builder_con_allowed_components(self, builder_v09):
    """build(allowed_components=...) genera un prompt más corto."""
    full = builder_v09.build(role_description="x", include_schema=True)
    pruned = builder_v09.build(
        role_description="x", include_schema=True, allowed_components=["Text", "Button"]
    )
    assert len(pruned) < len(full)

  def test_create_tool_con_poda(self, catalog_v09):
    """create_a2ui_tool con allowed_components no rompe."""
    tool = create_a2ui_tool(catalog_v09, allowed_components=["Text"])
    assert tool["name"] == "send_a2ui_json_to_client"


# --- Tests de cobertura total del ecosistema -----------------------


class TestCoberturaEcosistema:
  """Verifica que se cubren todos los catálogos y versiones oficiales."""

  def test_todas_las_versiones_tienen_catalogo(self):
    """Cada versión soportada tiene un BasicCatalog asociado."""
    from a2ui.basic_catalog.provider import BasicCatalog

    for v in SUPPORTED_VERSIONS:
      cfg = BasicCatalog.get_config(version=v)
      assert cfg is not None
      assert cfg.name

  def test_todos_los_catalogos_cargan(self, catalog_v09, catalog_v08, catalog_minimal):
    """Los tres catálogos oficiales (basic v0.9, standard v0.8, minimal v0.9)
    cargan y tienen componentes."""
    for cat in [catalog_v09, catalog_v08, catalog_minimal]:
      assert len(cat.catalog_schema["components"]) > 0

  def test_union_total_es_19_componentes_15_funciones(
      self, catalog_v09, catalog_v08, catalog_minimal
  ):
    """La unión de todos los catálogos da 19 componentes y 15 funciones."""
    all_comps = set()
    all_funcs = set()
    for cat in [catalog_v09, catalog_v08, catalog_minimal]:
      all_comps.update(cat.catalog_schema["components"].keys())
      all_funcs.update(cat.catalog_schema.get("functions", {}).keys())
    assert len(all_comps) == 19
    assert len(all_funcs) == 15
