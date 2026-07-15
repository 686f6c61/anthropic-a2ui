"""Tests de las reparaciones de payloads A2UI.

Cubre los dos arreglos del módulo ``repair.py``:

1. **``patch_catalog_schema``**: cambia ``oneOf`` por ``anyOf`` en
   ``DateTimeInput.min/max`` para evitar el falso negativo del formato
   ambiguo (bug del schema de A2UI).
2. **``repair_orphans``**: reconecta componentes huérfanos al árbol ``root``.
3. **``validate_tool_input`` con ``repair=True``**: integra ambas
   reparaciones y valida payloads que antes fallaban.
"""

from __future__ import annotations

import json

import pytest

from anthropic_a2ui import (
    find_orphans,
    patch_catalog_schema,
    repair_markdown_text,
    repair_orphans,
    validate_tool_input,
)

from ._a2ui_specs import CATALOG_ID


# --- Tests de patch_catalog_schema ---------------------------------


class TestPatchCatalogSchema:
  """Parchea el oneOf ambiguo de DateTimeInput.min/max."""

  def test_parchea_oneof_a_anyof_en_min(self, catalog_v09):
    patched = patch_catalog_schema(catalog_v09.catalog_schema)
    dti = patched["components"]["DateTimeInput"]
    for sub in dti.get("allOf", []):
      if "properties" in sub:
        min_prop = sub["properties"].get("min", {})
        for ae in min_prop.get("allOf", []):
          if "then" in ae:
            assert "anyOf" in ae["then"], "min debe tener anyOf despues del parche"
            assert (
                "oneOf" not in ae["then"]
            ), "min no debe tener oneOf despues del parche"

  def test_parchea_oneof_a_anyof_en_max(self, catalog_v09):
    patched = patch_catalog_schema(catalog_v09.catalog_schema)
    dti = patched["components"]["DateTimeInput"]
    for sub in dti.get("allOf", []):
      if "properties" in sub:
        max_prop = sub["properties"].get("max", {})
        for ae in max_prop.get("allOf", []):
          if "then" in ae:
            assert "anyOf" in ae["then"]
            assert "oneOf" not in ae["then"]

  def test_no_modifica_el_original(self, catalog_v09):
    original = catalog_v09.catalog_schema
    original_json = json.dumps(original, sort_keys=True)
    patch_catalog_schema(original)
    assert json.dumps(original, sort_keys=True) == original_json

  def test_no_rompe_otros_componentes(self, catalog_v09):
    patched = patch_catalog_schema(catalog_v09.catalog_schema)
    assert set(patched["components"].keys()) == set(
        catalog_v09.catalog_schema["components"].keys()
    )

  def test_datetimeinput_con_min_max_valida_con_parche(self, catalog_v09):
    """El payload que antes fallaba ahora valida con repair=True."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{
                    "id": "root",
                    "component": "DateTimeInput",
                    "value": "2026-01-01",
                    "enableDate": True,
                    "min": "2025-01-01",
                    "max": "2027-12-31",
                    "label": "Fecha",
                }],
            },
        },
    ]
    # Sin repair: falla
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, payload, repair=False)
    # Con repair: pasa
    validate_tool_input(catalog_v09, payload, repair=True)

  def test_datetimeinput_con_datetime_valida_con_parche(self, catalog_v09):
    """DateTimeInput con formato date-time completo tambien valida."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{
                    "id": "root",
                    "component": "DateTimeInput",
                    "value": "2026-01-01T12:00",
                    "enableDate": True,
                    "enableTime": True,
                    "min": "2025-01-01T00:00:00Z",
                    "max": "2027-12-31T23:59:59Z",
                    "label": "Fecha y hora",
                }],
            },
        },
    ]
    validate_tool_input(catalog_v09, payload, repair=True)


# --- Tests de repair_orphans ---------------------------------------


class TestRepairOrphans:
  """Repara componentes huérfanos reconectándolos al árbol root."""

  def test_payload_sin_orphans_no_cambia(self):
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Column", "children": ["c1"]},
                    {"id": "c1", "component": "Text", "text": "Hola"},
                ],
            },
        },
    ]
    repaired = repair_orphans(payload)
    assert repaired == payload

  def test_payload_con_orphan_se_repara(self):
    """Un componente huérfano se reconecta al root."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Column", "children": ["c1"]},
                    {"id": "c1", "component": "Text", "text": "Conectado"},
                    {"id": "orphan", "component": "Text", "text": "Huerfano"},
                ],
            },
        },
    ]
    assert find_orphans(payload) == ["orphan"]
    repaired = repair_orphans(payload)
    assert find_orphans(repaired) == []
    # El orphan debe estar en los children del root
    root = repaired[1]["updateComponents"]["components"][0]
    assert "orphan" in root["children"]

  def test_orphan_en_root_column_se_anade_a_children(self):
    """Si root es Column, el orphan se añade a children."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Column", "children": ["a"]},
                    {"id": "a", "component": "Text", "text": "A"},
                    {"id": "b", "component": "Text", "text": "B huerfano"},
                    {"id": "c", "component": "Text", "text": "C huerfano"},
                ],
            },
        },
    ]
    assert sorted(find_orphans(payload)) == ["b", "c"]
    repaired = repair_orphans(payload)
    assert find_orphans(repaired) == []
    root = repaired[1]["updateComponents"]["components"][0]
    assert "b" in root["children"]
    assert "c" in root["children"]

  def test_orphan_en_root_row_se_anade_a_children(self):
    """Si root es Row, el orphan se añade a children."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Row", "children": ["a"]},
                    {"id": "a", "component": "Text", "text": "A"},
                    {"id": "lost", "component": "Text", "text": "Perdido"},
                ],
            },
        },
    ]
    repaired = repair_orphans(payload)
    root = repaired[1]["updateComponents"]["components"][0]
    assert "lost" in root["children"]

  def test_orphan_en_root_card_envuelve_en_column(self):
    """Si root es Card (tiene child, no children), se crea un Column."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Card", "child": "a"},
                    {"id": "a", "component": "Text", "text": "A"},
                    {"id": "orphan", "component": "Text", "text": "Huerfano"},
                ],
            },
        },
    ]
    repaired = repair_orphans(payload)
    assert find_orphans(repaired) == []
    root = repaired[1]["updateComponents"]["components"][0]
    # root sigue siendo Card, pero su child ahora es un Column nuevo
    assert root["component"] == "Card"
    new_col_id = root["child"]
    new_col = next(
        c
        for c in repaired[1]["updateComponents"]["components"]
        if c["id"] == new_col_id
    )
    assert new_col["component"] == "Column"
    assert "a" in new_col["children"]
    assert "orphan" in new_col["children"]

  def test_orphan_en_root_hoja_crea_nuevo_root_valido(self, catalog_v09):
    """Si root es una hoja, se envuelve sin perder el id root."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Text", "text": "Principal"},
                    {"id": "orphan", "component": "Text", "text": "Huerfano"},
                ],
            },
        },
    ]

    repaired = repair_orphans(payload)
    components = repaired[1]["updateComponents"]["components"]
    root = next(c for c in components if c["id"] == "root")

    assert root["component"] == "Column"
    assert "root-inner" in root["children"]
    assert "orphan" in root["children"]
    assert find_orphans(repaired) == []
    validate_tool_input(catalog_v09, payload, repair=True)

  def test_find_orphans_sin_root_devuelve_vacio(self):
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "no-root", "component": "Text", "text": "Sin root"},
                ],
            },
        },
    ]
    assert find_orphans(payload) == []

  def test_find_orphans_payload_vacio(self):
    assert find_orphans([]) == []

  def test_repair_no_rompe_payload_valido(self, catalog_v09, sample_a2ui_json):
    """Un payload válido no se altera tras repair_orphans."""
    repaired = repair_orphans(sample_a2ui_json)
    # Debe seguir validando
    validate_tool_input(catalog_v09, repaired, repair=True)

  def test_repair_orphans_caso_real_haiku(self, catalog_v09):
    """Reproduce el caso real de Haiku: accessibility-button-text huerfano."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {
                        "id": "root",
                        "component": "Column",
                        "children": ["header", "row-demo", "access-section"],
                    },
                    {"id": "header", "component": "Text", "text": "Layout"},
                    {"id": "row-demo", "component": "Row", "children": ["r1"]},
                    {"id": "r1", "component": "Text", "text": "Row item"},
                    {
                        "id": "access-section",
                        "component": "Card",
                        "child": "access-container",
                    },
                    {
                        "id": "access-container",
                        "component": "Column",
                        "children": ["access-title", "access-btn"],
                    },
                    {
                        "id": "access-title",
                        "component": "Text",
                        "text": "Accessibility",
                    },
                    {
                        "id": "access-btn",
                        "component": "Button",
                        "child": "access-btn-text",
                        "action": {"event": {"name": "click"}},
                    },
                    {"id": "access-btn-text", "component": "Text", "text": "Click"},
                ],
            },
        },
    ]
    # Este payload no tiene huerfanos (todo conectado)
    assert find_orphans(payload) == []
    validate_tool_input(catalog_v09, payload, repair=True)


# --- Tests de integración: validate_tool_input con repair ----------


class TestRepairMarkdownText:
  """El texto visible no debe depender de un renderer Markdown."""

  def test_elimina_markdown_de_campos_de_presentacion(self):
    payload = [{
        "version": "v0.9",
        "updateComponents": {
            "surfaceId": "s",
            "components": [
                {
                    "id": "title",
                    "component": "Text",
                    "text": "## **Configuracion** de la cuenta",
                },
                {
                    "id": "language",
                    "component": "ChoicePicker",
                    "label": "*Idioma*",
                    "options": [
                        {"label": "[Espanol](https://example.com)", "value": "es"}
                    ],
                },
                {
                    "id": "tabs",
                    "component": "Tabs",
                    "tabs": [{"title": "`Preferencias`", "child": "title"}],
                },
            ],
        },
    }]
    repairs: list[str] = []

    repaired = repair_markdown_text(payload, repair_log=repairs)
    components = repaired[0]["updateComponents"]["components"]

    assert components[0]["text"] == "Configuracion de la cuenta"
    assert components[1]["label"] == "Idioma"
    assert components[1]["options"][0]["label"] == "Espanol"
    assert components[2]["tabs"][0]["title"] == "Preferencias"
    assert len(repairs) == 4
    assert payload[0]["updateComponents"]["components"][0]["text"].startswith("##")

  def test_conserva_rutas_urls_y_texto_no_markdown(self):
    payload = [{
        "version": "v0.9",
        "updateComponents": {
            "surfaceId": "s",
            "components": [
                {"id": "text", "component": "Text", "text": "C# developer"},
                {
                    "id": "image",
                    "component": "Image",
                    "url": "https://example.com/image#hero.png",
                    "description": "Imagen principal",
                },
            ],
        },
    }]

    assert repair_markdown_text(payload) == payload

  def test_validate_con_repair_aplica_limpieza_de_markdown(self, catalog_v09):
    """El flujo publico aplica la limpieza antes de devolver el payload."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Text", "text": "# Estado de cuenta"},
                ],
            },
        },
    ]

    repaired = validate_tool_input(catalog_v09, payload, repair=True)

    assert (
        repaired[1]["updateComponents"]["components"][0]["text"] == "Estado de cuenta"
    )
    assert (
        payload[1]["updateComponents"]["components"][0]["text"] == "# Estado de cuenta"
    )


class TestValidateConRepair:
  """validate_tool_input con repair=True integra ambos arreglos."""

  def test_datetimeinput_repair_true_pasa(self, catalog_v09):
    """El caso que fallaba en la prueba de fuego ahora pasa con repair."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{
                    "id": "root",
                    "component": "DateTimeInput",
                    "value": "2026-01-01",
                    "enableDate": True,
                    "enableTime": True,
                    "min": "2025-01-01",
                    "max": "2027-12-31",
                    "label": "Cita",
                }],
            },
        },
    ]
    # Sin repair: falla
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, payload, repair=False)
    # Con repair: pasa
    validate_tool_input(catalog_v09, payload, repair=True)

  def test_orphan_repair_true_pasa(self, catalog_v09):
    """Un payload con huerfano valida con repair=True."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Column", "children": ["a"]},
                    {"id": "a", "component": "Text", "text": "A"},
                    {"id": "orphan", "component": "Text", "text": "Huerfano"},
                ],
            },
        },
    ]
    # Sin repair: falla por orphan
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, payload, repair=False)
    # Con repair: pasa
    validate_tool_input(catalog_v09, payload, repair=True)

  def test_repair_false_sigue_validando_payloads_correctos(
      self, catalog_v09, sample_a2ui_json
  ):
    """repair=False no rompe payloads que ya eran válidos."""
    validate_tool_input(catalog_v09, sample_a2ui_json, repair=False)

  def test_repair_true_no_rompe_payloads_correctos(self, catalog_v09, sample_a2ui_json):
    """repair=True no rompe payloads que ya eran válidos."""
    validate_tool_input(catalog_v09, sample_a2ui_json, repair=True)

  def test_repair_combina_ambos_arreglos(self, catalog_v09):
    """Un payload con DateTimeInput ambiguo Y huerfano se repara."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Column", "children": ["dt"]},
                    {
                        "id": "dt",
                        "component": "DateTimeInput",
                        "value": "2026-01-01",
                        "enableDate": True,
                        "min": "2025-01-01",
                        "max": "2027-12-31",
                        "label": "Fecha",
                    },
                    {"id": "orphan", "component": "Text", "text": "Huerfano"},
                ],
            },
        },
    ]
    # Sin repair: falla por ambos motivos
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, payload, repair=False)
    # Con repair: pasa
    validate_tool_input(catalog_v09, payload, repair=True)


# --- Tests de repair_icons -----------------------------------------


class TestRepairIcons:
  """Repara nombres de iconos invalidos."""

  def test_icon_cloud_se_mapea_a_info(self, catalog_v09):
    """cloud no esta en el enum, se mapea a info."""
    from anthropic_a2ui import repair_icons

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Icon", "name": "cloud"},
                ],
            },
        },
    ]
    repaired = repair_icons(payload)
    icon = repaired[1]["updateComponents"]["components"][0]
    assert icon["name"] == "info"

  def test_icon_trash_se_mapea_a_delete(self, catalog_v09):
    """trash se mapea a delete (alias conocido)."""
    from anthropic_a2ui import repair_icons

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Icon", "name": "trash"},
                ],
            },
        },
    ]
    repaired = repair_icons(payload)
    assert repaired[1]["updateComponents"]["components"][0]["name"] == "delete"

  def test_icon_valido_no_cambia(self, catalog_v09):
    """Un icono valido no se modifica."""
    from anthropic_a2ui import repair_icons

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Icon", "name": "add"},
                ],
            },
        },
    ]
    repaired = repair_icons(payload)
    assert repaired[1]["updateComponents"]["components"][0]["name"] == "add"

  def test_icon_function_call_se_sustituye_por_info(self, catalog_v09):
    """Un Icon.name que es un FunctionCall (objeto) se sustituye por info."""
    from anthropic_a2ui import repair_icons

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {
                        "id": "root",
                        "component": "Icon",
                        "name": {"call": "ternary", "args": {}, "returnType": "string"},
                    },
                ],
            },
        },
    ]
    repaired = repair_icons(payload)
    assert repaired[1]["updateComponents"]["components"][0]["name"] == "info"

  def test_repair_icons_valida_despues(self, catalog_v09):
    """Tras repair_icons, un payload con icono invalido valida."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Icon", "name": "cloud"},
                ],
            },
        },
    ]
    # Sin repair: falla
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, payload, repair=False)
    # Con repair: pasa
    validate_tool_input(catalog_v09, payload, repair=True)

  def test_icon_sunny_se_mapea_a_info(self, catalog_v09):
    """sunny no esta en el enum ni en aliases, se sustituye por info."""
    from anthropic_a2ui import repair_icons

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Icon", "name": "sunny"},
                ],
            },
        },
    ]
    repaired = repair_icons(payload)
    assert repaired[1]["updateComponents"]["components"][0]["name"] == "info"

  def test_no_modifica_payload_sin_icons(self, catalog_v09):
    """Un payload sin Icon no se modifica."""
    from anthropic_a2ui import repair_icons

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Text", "text": "Hola"},
                ],
            },
        },
    ]
    repaired = repair_icons(payload)
    assert repaired == payload


# --- Tests de repair_functions -------------------------------------


class TestRepairFunctions:
  """Repara FunctionCalls con funciones inexistentes."""

  def test_ternary_en_text_se_sustituye(self, catalog_v09):
    """ternary no existe en el catalogo, se sustituye por string vacio."""
    from anthropic_a2ui import repair_functions

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {
                        "id": "root",
                        "component": "Text",
                        "text": {
                            "call": "ternary",
                            "args": {
                                "condition": {},
                                "trueValue": "star",
                                "falseValue": "starOff",
                            },
                            "returnType": "string",
                        },
                    },
                ],
            },
        },
    ]
    repaired = repair_functions(payload)
    text = repaired[1]["updateComponents"]["components"][0]["text"]
    assert text == ""  # returnType string -> ""

  def test_funcion_valida_no_cambia(self, catalog_v09):
    """Una funcion valida no se modifica."""
    from anthropic_a2ui import repair_functions

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {
                        "id": "root",
                        "component": "Text",
                        "text": {
                            "call": "formatString",
                            "args": {"value": "Hola"},
                            "returnType": "string",
                        },
                    },
                ],
            },
        },
    ]
    repaired = repair_functions(payload)
    assert (
        repaired[1]["updateComponents"]["components"][0]["text"]
        == payload[1]["updateComponents"]["components"][0]["text"]
    )

  def test_ternary_en_check_se_elimina(self, catalog_v09):
    """Un check con funcion invalida se elimina de la lista."""
    from anthropic_a2ui import repair_functions

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {
                        "id": "root",
                        "component": "TextField",
                        "label": "X",
                        "checks": [
                            {
                                "condition": {
                                    "call": "ternary",
                                    "args": {},
                                    "returnType": "boolean",
                                },
                                "message": "Error",
                            },
                            {
                                "condition": {
                                    "call": "required",
                                    "args": {"value": {"path": "/x"}},
                                    "returnType": "boolean",
                                },
                                "message": "Obligatorio",
                            },
                        ],
                    },
                ],
            },
        },
    ]
    repaired = repair_functions(payload)
    checks = repaired[1]["updateComponents"]["components"][0]["checks"]
    # El check con ternary se elimina, el de required se mantiene
    assert len(checks) == 1
    assert checks[0]["condition"]["call"] == "required"

  def test_repair_functions_valida_despues(self, catalog_v09):
    """Tras repair_functions, un payload con ternary valida."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {
                        "id": "root",
                        "component": "Text",
                        "text": {
                            "call": "ternary",
                            "args": {},
                            "returnType": "string",
                        },
                    },
                ],
            },
        },
    ]
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, payload, repair=False)
    validate_tool_input(catalog_v09, payload, repair=True)

  def test_no_modifica_payload_sin_functions(self, catalog_v09):
    """Un payload sin FunctionCalls no se modifica."""
    from anthropic_a2ui import repair_functions

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Text", "text": "Hola"},
                ],
            },
        },
    ]
    repaired = repair_functions(payload)
    assert repaired == payload


# --- Tests de repair_childlists ------------------------------------


class TestRepairChildlists:
  """Repara children dinamicos en Row/Column."""

  def test_column_con_childlist_dinamico_se_convierte_a_estatico(self, catalog_v09):
    """Un Column con children dinamico {componentId, path} se convierte a estatico."""
    from anthropic_a2ui import repair_childlists

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {
                        "id": "root",
                        "component": "Column",
                        "children": [
                            {"componentId": "gallery-image", "path": "/images"}
                        ],
                    },
                    {
                        "id": "gallery-image",
                        "component": "Image",
                        "url": "https://x.com/a.png",
                    },
                ],
            },
        },
    ]
    repaired = repair_childlists(payload)
    root = repaired[1]["updateComponents"]["components"][0]
    assert root["children"] == ["gallery-image"]

  def test_row_con_childlist_dinamico_se_convierte(self, catalog_v09):
    """Un Row con children dinamico se convierte a estatico."""
    from anthropic_a2ui import repair_childlists

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {
                        "id": "root",
                        "component": "Row",
                        "children": [{"componentId": "img", "path": "/items"}],
                    },
                    {"id": "img", "component": "Image", "url": "https://x.com/a.png"},
                ],
            },
        },
    ]
    repaired = repair_childlists(payload)
    assert repaired[1]["updateComponents"]["components"][0]["children"] == ["img"]

  def test_column_con_children_estatico_no_cambia(self, catalog_v09):
    """Un Column con children estatico (strings) no se modifica."""
    from anthropic_a2ui import repair_childlists

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {"id": "root", "component": "Column", "children": ["a", "b"]},
                    {"id": "a", "component": "Text", "text": "A"},
                    {"id": "b", "component": "Text", "text": "B"},
                ],
            },
        },
    ]
    repaired = repair_childlists(payload)
    assert repaired == payload

  def test_list_con_childlist_dinamico_no_cambia(self, catalog_v09):
    """List SI permite children dinamico, no se modifica."""
    from anthropic_a2ui import repair_childlists

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {
                        "id": "root",
                        "component": "List",
                        "children": {"componentId": "item", "path": "/items"},
                    },
                ],
            },
        },
    ]
    repaired = repair_childlists(payload)
    # List no se toca
    assert repaired[1]["updateComponents"]["components"][0]["children"] == {
        "componentId": "item",
        "path": "/items",
    }

  def test_repair_childlists_valida_despues(self, catalog_v09):
    """Tras repair_childlists, un payload con children dinamico en Column valida."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [
                    {
                        "id": "root",
                        "component": "Column",
                        "children": [{"componentId": "img", "path": "/images"}],
                    },
                    {"id": "img", "component": "Image", "url": "https://x.com/a.png"},
                ],
            },
        },
    ]
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, payload, repair=False)
    validate_tool_input(catalog_v09, payload, repair=True)
