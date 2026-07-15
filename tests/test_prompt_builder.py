"""Tests del prompt builder.

Verifican que ``ClaudeA2uiPromptBuilder`` produce un prompt coherente con
el formato A2UI: contiene las etiquetas ``<a2ui-json>`` (para que el parser
de tags funcione), incluye el esquema y respeta la versión.
"""

import pytest

from anthropic_a2ui import (
    DEFAULT_VERSION,
    SUPPORTED_VERSIONS,
    ClaudeA2uiPromptBuilder,
)


class TestClaudeA2uiPromptBuilder:

  def test_build_devuelve_string_no_vacio(self, builder_v09):
    prompt = builder_v09.build(role_description="Construye formularios.")
    assert isinstance(prompt, str)
    assert len(prompt) > 100

  def test_build_contiene_etiquetas_a2ui_json(self, builder_v09):
    prompt = builder_v09.build(role_description="Agente de UI")
    assert "<a2ui-json>" in prompt
    assert "</a2ui-json>" in prompt

  def test_build_contiene_role_description(self, builder_v09):
    prompt = builder_v09.build(role_description="Construye formularios de contacto.")
    assert "Construye formularios de contacto." in prompt

  def test_build_incluye_schema(self, builder_v09):
    prompt = builder_v09.build(
        role_description="x", include_schema=True, include_examples=False
    )
    # El esquema JSON Schema incluye la palabra clave 'A2UI Message Schema'
    assert "A2UI Message Schema" in prompt or "server_to_client" in prompt

  def test_build_sin_schema(self, builder_v09):
    prompt_no_schema = builder_v09.build(
        role_description="x", include_schema=False, include_examples=False
    )
    prompt_con_schema = builder_v09.build(
        role_description="x", include_schema=True, include_examples=False
    )
    # Sin esquema, el prompt es notablemente más corto (no incluye el JSON Schema)
    assert len(prompt_no_schema) < len(prompt_con_schema)
    # El marker ---BEGIN A2UI JSON SCHEMA--- solo aparece con esquema
    assert "---BEGIN A2UI JSON SCHEMA---" not in prompt_no_schema
    assert "---BEGIN A2UI JSON SCHEMA---" in prompt_con_schema

  def test_build_incluye_ejemplos(self, builder_v09):
    prompt = builder_v09.build(
        role_description="x", include_schema=False, include_examples=True
    )
    # Los ejemplos few-shot vienen como bloques <a2ui-json>
    assert "<a2ui-json>" in prompt

  def test_build_incluye_reglas_de_presentacion_sin_markdown(self, builder_v09):
    prompt = builder_v09.build(role_description="x", include_schema=False)
    assert "No uses sintaxis Markdown" in prompt
    assert "Text.variant" in prompt
    assert "formularios inicialmente vacios" in prompt
    assert "URL HTTPS publica y directa" in prompt
    assert "Google Storage/Google GTV" in prompt

  def test_version_por_defecto_es_09(self):
    builder = ClaudeA2uiPromptBuilder()
    assert builder.version == DEFAULT_VERSION
    assert DEFAULT_VERSION == "0.9"

  def test_version_invalid_lanza(self):
    with pytest.raises(ValueError, match="Versión no soportada"):
      ClaudeA2uiPromptBuilder(version="1.0")

  def test_versions_soportadas_contiene_09(self):
    assert "0.9" in SUPPORTED_VERSIONS
    assert "0.8" in SUPPORTED_VERSIONS

  def test_get_catalog_devuelve_a2uicatalog(self, builder_v09):
    cat = builder_v09.get_catalog()
    assert cat is not None
    # A2uiCatalog expone catalog_id y validator
    assert hasattr(cat, "catalog_id")
    assert hasattr(cat, "validator")

  def test_get_validator_devuelve_validador(self, builder_v09):
    val = builder_v09.get_validator()
    assert val is not None
    # El validador expone get_version
    assert val.get_version() == "0.9"

  def test_build_con_allowed_components(self, builder_v09):
    # Podar a Text y Button reduce el prompt (menos componentes en el esquema)
    full = builder_v09.build(role_description="x", include_schema=True)
    pruned = builder_v09.build(
        role_description="x",
        include_schema=True,
        allowed_components=["Text", "Button"],
    )
    # El podado menciona menos componentes
    assert "TextField" in full
    assert "TextField" not in pruned or len(pruned) < len(full)
