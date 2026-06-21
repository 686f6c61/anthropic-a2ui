"""Especificaciones de payloads A2UI válidos para TODOS los componentes.

Este módulo define payloads mínimos que validan contra el esquema, para cada
componente único de A2UI en cualquier catálogo oficial de cualquier versión:

- 18 componentes del Basic Catalog v0.9 (Text, Image, Icon, Video, AudioPlayer,
  Row, Column, List, Card, Tabs, Modal, Divider, Button, TextField, CheckBox,
  ChoicePicker, Slider, DateTimeInput).
- ``MultipleChoice`` del catálogo standard v0.8 (legacy, reemplazado por
  ChoicePicker en v0.9).
- 5 componentes del catálogo minimal v0.9 (Text, Row, Column, Button,
  TextField) para verificar compatibilidad con catálogos reducidos.

Total: 19 componentes únicos en todos los catálogos oficiales de A2UI.

Cada especificación incluye:

- ``name``: nombre del componente.
- ``root_component``: objeto con el componente y sus campos required, que
  se usará como componente raíz (id ``root``).
- ``extra_components``: lista de componentes adicionales (hijos) que el
  componente raíz referencia por ID.
"""

from __future__ import annotations

from typing import Any

CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"


def _text(id: str, text: str) -> dict[str, Any]:
  """Atajo para crear un componente Text."""
  return {"id": id, "component": "Text", "text": text}


def _button(id: str, label: str, action_name: str = "click") -> dict[str, Any]:
  """Atajo para crear un Button con un Text hijo."""
  return {
      "id": id,
      "component": "Button",
      "child": f"{id}-label",
      "action": {"event": {"name": action_name}},
  }


# Cada entrada: (nombre, componente_raiz, componentes_extra)
# El componente raíz lleva id="root"; los extras van aparte.
COMPONENT_SPECS: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = [
    # --- Componentes simples (sin hijos) -------------------------------
    (
        "Text",
        {"id": "root", "component": "Text", "text": "Hola mundo"},
        [],
    ),
    (
        "Image",
        {"id": "root", "component": "Image", "url": "https://example.com/a.png"},
        [],
    ),
    (
        "Icon",
        {"id": "root", "component": "Icon", "name": "add"},
        [],
    ),
    (
        "Video",
        {"id": "root", "component": "Video", "url": "https://example.com/v.mp4"},
        [],
    ),
    (
        "AudioPlayer",
        {"id": "root", "component": "AudioPlayer", "url": "https://example.com/a.mp3"},
        [],
    ),
    (
        "Divider",
        {"id": "root", "component": "Divider"},
        [],
    ),
    # --- Componentes con un hijo (child) -------------------------------
    (
        "Card",
        {"id": "root", "component": "Card", "child": "card-content"},
        [_text("card-content", "Contenido de tarjeta")],
    ),
    (
        "Button",
        {
            "id": "root",
            "component": "Button",
            "child": "btn-label",
            "action": {"event": {"name": "submit"}},
        },
        [_text("btn-label", "Enviar")],
    ),
    # --- Layout: hijos múltiples (children) ----------------------------
    (
        "Row",
        {"id": "root", "component": "Row", "children": ["row-child"]},
        [_text("row-child", "Hijo de Row")],
    ),
    (
        "Column",
        {"id": "root", "component": "Column", "children": ["col-child"]},
        [_text("col-child", "Hijo de Column")],
    ),
    (
        "List",
        {"id": "root", "component": "List", "children": ["list-child"]},
        [_text("list-child", "Elemento de lista")],
    ),
    # --- Tabs: lista de {title, child} --------------------------------
    (
        "Tabs",
        {
            "id": "root",
            "component": "Tabs",
            "tabs": [{"title": "Pestaña 1", "child": "tab-content"}],
        },
        [_text("tab-content", "Contenido de pestaña")],
    ),
    # --- Modal: trigger + content -------------------------------------
    (
        "Modal",
        {
            "id": "root",
            "component": "Modal",
            "trigger": "modal-trigger",
            "content": "modal-content",
        },
        [
            _button("modal-trigger", "Abrir", action_name="open-modal"),
            _text("modal-trigger-label", "Abrir"),
            _text("modal-content", "Contenido del modal"),
        ],
    ),
    # --- Inputs -------------------------------------------------------
    (
        "TextField",
        {"id": "root", "component": "TextField", "label": "Nombre"},
        [],
    ),
    (
        "CheckBox",
        {
            "id": "root",
            "component": "CheckBox",
            "label": "Aceptar términos",
            "value": True,
        },
        [],
    ),
    (
        "ChoicePicker",
        {
            "id": "root",
            "component": "ChoicePicker",
            "options": [
                {"label": "Opción A", "value": "a"},
                {"label": "Opción B", "value": "b"},
            ],
            "value": ["a"],
        },
        [],
    ),
    (
        "Slider",
        {"id": "root", "component": "Slider", "value": 5, "max": 10},
        [],
    ),
    (
        "DateTimeInput",
        {"id": "root", "component": "DateTimeInput", "value": "2026-01-01"},
        [],
    ),
]


def build_payload(
    spec: tuple[str, dict[str, Any], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
  """Construye un payload A2UI completo a partir de una especificación.

  Genera dos mensajes: ``createSurface`` y ``updateComponents``, con el
  componente raíz y los extras de la spec.

  Args:
    spec: Tupla ``(name, root_component, extra_components)`` de
      ``COMPONENT_SPECS``.

  Returns:
    Lista de dos mensajes A2UI listos para validar.
  """
  _, root, extras = spec
  components = [root, *extras]
  return [
      {
          "version": "v0.9",
          "createSurface": {"surfaceId": "test-surface", "catalogId": CATALOG_ID},
      },
      {
          "version": "v0.9",
          "updateComponents": {
              "surfaceId": "test-surface",
              "components": components,
          },
      },
  ]


def all_payloads() -> list[tuple[str, list[dict[str, Any]]]]:
  """Devuelve ``[(name, payload), ...]`` para los 18 componentes del Basic v0.9.

  Atajo para parametrizar tests: ``@pytest.mark.parametrize("name, payload",
  all_payloads())``.
  """
  return [
      (name, build_payload(spec))
      for name, spec in zip([s[0] for s in COMPONENT_SPECS], COMPONENT_SPECS)
  ]


# --- v0.8: catálogo standard (legacy) ------------------------------
#
# v0.8 usa una estructura de mensajes distinta (beginRendering/surfaceUpdate
# en vez de createSurface/updateComponents) y los componentes van envueltos
# en ``component: {Tipo: {...}}`` con wrappers literalString/literalArray
# para valores dinámicos.

CATALOG_ID_V08 = "https://a2ui.org/specification/v0_8/standard_catalog_definition.json"

# Mapeo de componentes v0.8 que NO están en v0.9 (MultipleChoice).
# Los 17 componentes compartidos se validan con el builder de v0.9;
# aquí solo definimos el componente exclusivo de v0.8.
V08_EXTRA_SPECS: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = [
    (
        "MultipleChoice",
        {
            "id": "root",
            "component": {
                "MultipleChoice": {
                    "selections": {"literalArray": ["a"]},
                    "options": [
                        {"label": {"literalString": "Opción A"}, "value": "a"},
                        {"label": {"literalString": "Opción B"}, "value": "b"},
                    ],
                }
            },
        },
        [],
    ),
]


def build_v08_payload(
    spec: tuple[str, dict[str, Any], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
  """Construye un payload A2UI v0.8 (beginRendering + surfaceUpdate).

  Args:
    spec: Tupla ``(name, root_component, extra_components)``.

  Returns:
    Lista de dos mensajes A2UI v0.8.
  """
  _, root, extras = spec
  components = [root, *extras]
  return [
      {
          "beginRendering": {
              "surfaceId": "test-surface",
              "root": "root",
              "catalogId": CATALOG_ID_V08,
          }
      },
      {
          "surfaceUpdate": {
              "surfaceId": "test-surface",
              "components": components,
          }
      },
  ]


def all_v08_payloads() -> list[tuple[str, list[dict[str, Any]]]]:
  """Devuelve ``[(name, payload), ...]`` para los componentes exclusivos v0.8."""
  return [
      (name, build_v08_payload(spec))
      for name, spec in zip([s[0] for s in V08_EXTRA_SPECS], V08_EXTRA_SPECS)
  ]


# --- v0.9 minimal: catálogo reducido (5 componentes, 1 función) ----
#
# El catálogo minimal de v0.9 define Text, Row, Column, Button y TextField
# más la función capitalize. Verifica que el paquete funciona con cualquier
# CatalogConfig, no solo con BasicCatalog.

MINIMAL_CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/minimal/catalog.json"

MINIMAL_SPECS: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = [
    (
        "Text",
        {"id": "root", "component": "Text", "text": "Hola minimal"},
        [],
    ),
    (
        "Row",
        {"id": "root", "component": "Row", "children": ["row-child"]},
        [{"id": "row-child", "component": "Text", "text": "Hijo"}],
    ),
    (
        "Column",
        {"id": "root", "component": "Column", "children": ["col-child"]},
        [{"id": "col-child", "component": "Text", "text": "Hijo"}],
    ),
    (
        "Button",
        {
            "id": "root",
            "component": "Button",
            "child": "btn-label",
            "action": {"event": {"name": "click"}},
        },
        [{"id": "btn-label", "component": "Text", "text": "Click"}],
    ),
    (
        "TextField",
        {"id": "root", "component": "TextField", "label": "Campo minimal"},
        [],
    ),
]


def build_minimal_payload(
    spec: tuple[str, dict[str, Any], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
  """Construye un payload A2UI v0.9 con el catalogId del minimal."""
  _, root, extras = spec
  components = [root, *extras]
  return [
      {
          "version": "v0.9",
          "createSurface": {
              "surfaceId": "test-surface",
              "catalogId": MINIMAL_CATALOG_ID,
          },
      },
      {
          "version": "v0.9",
          "updateComponents": {
              "surfaceId": "test-surface",
              "components": components,
          },
      },
  ]


def all_minimal_payloads() -> list[tuple[str, list[dict[str, Any]]]]:
  """Devuelve ``[(name, payload), ...]`` para los 5 componentes del minimal."""
  return [
      (name, build_minimal_payload(spec))
      for name, spec in zip([s[0] for s in MINIMAL_SPECS], MINIMAL_SPECS)
  ]


def all_unique_component_names() -> list[str]:
  """Devuelve los nombres de TODOS los componentes únicos de A2UI.

  Incluye los 18 del Basic v0.9, MultipleChoice de v0.8 y los 5 del minimal
  (que son subconjunto de Basic, pero se listan para cobertura explícita).
  Total: 19 componentes únicos.
  """
  basic = [s[0] for s in COMPONENT_SPECS]
  v08_extra = [s[0] for s in V08_EXTRA_SPECS]
  # minimal es subconjunto de basic, no añade nombres nuevos
  return list(dict.fromkeys(basic + v08_extra))
