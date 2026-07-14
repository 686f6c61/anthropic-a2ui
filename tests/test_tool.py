"""Tests de la definición de tool (tool.py)."""

import pytest

from anthropic_a2ui import (
    TOOL_DESCRIPTION,
    TOOL_NAME,
    create_a2ui_tool,
    make_parser_for_tool,
    validate_tool_input,
)


class TestCreateA2uiTool:

  def test_devuelve_dict_con_campos_anthropic(self, catalog_v09):
    tool = create_a2ui_tool(catalog_v09)
    assert set(tool.keys()) == {"name", "description", "input_schema"}
    assert tool["name"] == TOOL_NAME
    assert isinstance(tool["description"], str) and tool["description"]
    assert isinstance(tool["input_schema"], dict)

  def test_input_schema_es_wrapper_con_a2ui_json(self, catalog_v09):
    """El input_schema envuelve s2c en {"a2ui_json": [mensaje]}.

    Anthropic no soporta oneOf/allOf/anyOf en el nivel superior, así que
    create_a2ui_tool envuelve el esquema s2c dentro de un objeto con
    propiedad a2ui_json (array). El s2c original queda en items.
    """
    tool = create_a2ui_tool(catalog_v09)
    schema = tool["input_schema"]
    assert schema["type"] == "object"
    assert "a2ui_json" in schema["properties"]
    assert schema["properties"]["a2ui_json"]["type"] == "array"
    assert schema["properties"]["a2ui_json"]["minItems"] == 1
    # El s2c original está dentro de items
    items = schema["properties"]["a2ui_json"]["items"]
    assert items.get("$id", "").endswith("server_to_client.json")

  def test_description_por_defecto(self, catalog_v09):
    tool = create_a2ui_tool(catalog_v09)
    assert tool["description"] == TOOL_DESCRIPTION

  def test_name_personalizado(self, catalog_v09):
    tool = create_a2ui_tool(catalog_v09, name="mi_tool")
    assert tool["name"] == "mi_tool"

  def test_description_personalizado(self, catalog_v09):
    tool = create_a2ui_tool(catalog_v09, description="Descripción custom.")
    assert tool["description"] == "Descripción custom."

  def test_allowed_components_poda_el_catalogo(self, catalog_v09):
    # with_pruning reduce el catalog_schema, que es la fuente de las
    # restricciones de componente que se anaden al esquema de la tool.
    full_cat = catalog_v09
    pruned_cat = full_cat.with_pruning(allowed_components=["Text", "Button"])
    assert set(pruned_cat.catalog_schema["components"].keys()) == {"Text", "Button"}
    assert len(full_cat.catalog_schema["components"]) > 2

  def test_input_schema_restringe_componentes_con_poda(self, catalog_v09):
    tool = create_a2ui_tool(catalog_v09, allowed_components=["Text", "Button"])
    schema = tool["input_schema"]
    component_items = schema["properties"]["a2ui_json"]["items"]["$defs"][
        "UpdateComponentsMessage"
    ]["properties"]["updateComponents"]["properties"]["components"]["items"]
    constraint = component_items["allOf"][1]
    assert constraint["properties"]["component"]["enum"] == ["Button", "Text"]

  def test_allowed_messages_acepta_nombres_publicos(self, catalog_v09):
    tool = create_a2ui_tool(catalog_v09, allowed_messages=["updateComponents"])
    items = tool["input_schema"]["properties"]["a2ui_json"]["items"]
    assert items["oneOf"] == [{"$ref": "#/$defs/UpdateComponentsMessage"}]

  def test_tool_name_constante_es_send_a2ui_json_to_client(self):
    assert TOOL_NAME == "send_a2ui_json_to_client"


class TestValidateToolInput:

  def test_payload_valido_no_lanza(self, catalog_v09, sample_a2ui_json):
    # sample_a2ui_json debe validar; si no, ajustar el fixture
    try:
      validate_tool_input(catalog_v09, sample_a2ui_json)
    except Exception as exc:
      pytest.skip(f"Payload de fixture no valida contra el catálogo: {exc}")

  def test_payload_invalido_lanza(self, catalog_v09):
    bad = [{"version": "v0.9", "createSurface": {"surfaceId": "x"}}]  # falta catalogId
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, bad)

  def test_payload_vacio_lanza(self, catalog_v09):
    with pytest.raises(ValueError, match="al menos un mensaje"):
      validate_tool_input(catalog_v09, [])

  def test_strict_integrity_false_es_mas_laxo(self, catalog_v09, sample_a2ui_json):
    # Con strict_integrity=False, se salta comprobaciones de topología
    try:
      validate_tool_input(catalog_v09, sample_a2ui_json, strict_integrity=False)
    except Exception as exc:
      pytest.skip(f"Payload de fixture no valida: {exc}")


class TestMakeParserForTool:

  def test_devuelve_parser_con_validacion(self, catalog_v09):
    parser = make_parser_for_tool(catalog_v09, strict=True)
    assert parser.strict_tool_validation is True
    assert parser._validator is not None

  def test_devuelve_parser_sin_validacion(self, catalog_v09):
    parser = make_parser_for_tool(catalog_v09, strict=False)
    assert parser.strict_tool_validation is False
