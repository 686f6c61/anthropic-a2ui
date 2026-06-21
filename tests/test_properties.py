"""Tests de tema y propiedades opcionales de componentes A2UI v0.9.

A2UI permite muchas propiedades opcionales en componentes y en createSurface.
Estos tests verifican que cada propiedad opcional valida correctamente:

- **Tema**: ``primaryColor``, ``iconUrl``, ``agentDisplayName`` en createSurface.
- **Variant**: ``variant`` en Text (h1, h2, caption, body), Button (primary,
  borderless), TextField (longText, number, obscured), ChoicePicker
  (multipleSelection, mutuallyExclusive).
- **Layout**: ``justify``, ``align`` en Row/Column, ``direction`` en List,
  ``weight`` en hijos de Row/Column.
- **Inputs**: ``validationRegexp`` en TextField, ``min``/``max`` en Slider,
  ``displayStyle``/``filterable`` en ChoicePicker, ``enableDate``/
  ``enableTime`` en DateTimeInput.
- **Accesibilidad**: ``accessibility`` con ``label`` y ``description``.
- **sendDataModel**: en createSurface.
- **Icon**: ``name`` con ``svgPath`` personalizado.
- **Image**: ``fit`` y ``variant``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from anthropic_a2ui import (
    ClaudeStreamParser,
    to_a2ui_part,
    validate_tool_input,
)

from ._a2ui_specs import CATALOG_ID


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


def _make_payload(root_component, extras=None):
  """Construye un payload v0.9 con createSurface + updateComponents."""
  components = [{"id": "root", **root_component}]
  if extras:
    components.extend(extras)
  return [
      {
          "version": "v0.9",
          "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
      },
      {
          "version": "v0.9",
          "updateComponents": {"surfaceId": "s", "components": components},
      },
  ]


def _text(id, text):
  return {"id": id, "component": "Text", "text": text}


# --- Tests de tema -------------------------------------------------


class TestTema:
  """Propiedades de theme en createSurface."""

  def test_primary_color(self, catalog_v09):
    payload = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "s",
                "catalogId": CATALOG_ID,
                "theme": {"primaryColor": "#00BFFF"},
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{"id": "root", "component": "Text", "text": "X"}],
            },
        },
    ]
    validate_tool_input(catalog_v09, payload)

  def test_primary_color_formato_invalido(self, catalog_v09):
    """primaryColor debe ser hexadecimal #RRGGBB."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "s",
                "catalogId": CATALOG_ID,
                "theme": {"primaryColor": "blue"},
            },
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
      validate_tool_input(catalog_v09, payload)

  def test_icon_url(self, catalog_v09):
    payload = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "s",
                "catalogId": CATALOG_ID,
                "theme": {"iconUrl": "https://example.com/icon.png"},
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{"id": "root", "component": "Text", "text": "X"}],
            },
        },
    ]
    validate_tool_input(catalog_v09, payload)

  def test_agent_display_name(self, catalog_v09):
    payload = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "s",
                "catalogId": CATALOG_ID,
                "theme": {"agentDisplayName": "Mi agente"},
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{"id": "root", "component": "Text", "text": "X"}],
            },
        },
    ]
    validate_tool_input(catalog_v09, payload)

  def test_tema_completo(self, catalog_v09):
    payload = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "s",
                "catalogId": CATALOG_ID,
                "theme": {
                    "primaryColor": "#FF5722",
                    "iconUrl": "https://example.com/icon.png",
                    "agentDisplayName": "Asistente",
                },
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{"id": "root", "component": "Text", "text": "X"}],
            },
        },
    ]
    validate_tool_input(catalog_v09, payload)

  def test_send_data_model_true(self, catalog_v09):
    payload = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "s",
                "catalogId": CATALOG_ID,
                "sendDataModel": True,
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{"id": "root", "component": "Text", "text": "X"}],
            },
        },
    ]
    validate_tool_input(catalog_v09, payload)


# --- Tests de variant ----------------------------------------------


class TestVariant:
  """Propiedad variant en varios componentes."""

  @pytest.mark.parametrize("variant", ["h1", "h2", "h3", "h4", "h5", "caption", "body"])
  def test_text_variant(self, catalog_v09, variant):
    payload = _make_payload({"component": "Text", "text": "X", "variant": variant})
    validate_tool_input(catalog_v09, payload)

  @pytest.mark.parametrize("variant", ["default", "primary", "borderless"])
  def test_button_variant(self, catalog_v09, variant):
    payload = _make_payload(
        {
            "component": "Button",
            "child": "btn",
            "action": {"event": {"name": "x"}},
            "variant": variant,
        },
        extras=[_text("btn", "Click")],
    )
    validate_tool_input(catalog_v09, payload)

  @pytest.mark.parametrize("variant", ["longText", "number", "shortText", "obscured"])
  def test_textfield_variant(self, catalog_v09, variant):
    payload = _make_payload(
        {"component": "TextField", "label": "Campo", "variant": variant}
    )
    validate_tool_input(catalog_v09, payload)

  @pytest.mark.parametrize("variant", ["multipleSelection", "mutuallyExclusive"])
  def test_choicepicker_variant(self, catalog_v09, variant):
    payload = _make_payload({
        "component": "ChoicePicker",
        "options": [{"label": "A", "value": "a"}],
        "value": ["a"],
        "variant": variant,
    })
    validate_tool_input(catalog_v09, payload)

  def test_text_variant_invalido(self, catalog_v09):
    payload = _make_payload({"component": "Text", "text": "X", "variant": "h6"})
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, payload)


# --- Tests de layout (justify, align, direction, weight) -----------


class TestLayout:
  """Propiedades de layout en Row, Column, List y weight en hijos."""

  @pytest.mark.parametrize(
      "justify",
      [
          "center",
          "end",
          "spaceAround",
          "spaceBetween",
          "spaceEvenly",
          "start",
          "stretch",
      ],
  )
  def test_row_justify(self, catalog_v09, justify):
    payload = _make_payload(
        {"component": "Row", "children": ["c1"], "justify": justify},
        extras=[_text("c1", "X")],
    )
    validate_tool_input(catalog_v09, payload)

  @pytest.mark.parametrize("align", ["start", "center", "end", "stretch"])
  def test_row_align(self, catalog_v09, align):
    payload = _make_payload(
        {"component": "Row", "children": ["c1"], "align": align},
        extras=[_text("c1", "X")],
    )
    validate_tool_input(catalog_v09, payload)

  @pytest.mark.parametrize(
      "justify",
      [
          "start",
          "center",
          "end",
          "spaceBetween",
          "spaceAround",
          "spaceEvenly",
          "stretch",
      ],
  )
  def test_column_justify(self, catalog_v09, justify):
    payload = _make_payload(
        {"component": "Column", "children": ["c1"], "justify": justify},
        extras=[_text("c1", "X")],
    )
    validate_tool_input(catalog_v09, payload)

  def test_list_direction_horizontal(self, catalog_v09):
    payload = _make_payload(
        {"component": "List", "children": ["c1"], "direction": "horizontal"},
        extras=[_text("c1", "X")],
    )
    validate_tool_input(catalog_v09, payload)

  def test_list_direction_vertical(self, catalog_v09):
    payload = _make_payload(
        {"component": "List", "children": ["c1"], "direction": "vertical"},
        extras=[_text("c1", "X")],
    )
    validate_tool_input(catalog_v09, payload)

  def test_weight_en_hijo_de_row(self, catalog_v09):
    payload = _make_payload(
        {"component": "Row", "children": ["c1"]},
        extras=[{"id": "c1", "component": "Text", "text": "X", "weight": 2}],
    )
    validate_tool_input(catalog_v09, payload)

  def test_weight_en_hijo_de_column(self, catalog_v09):
    payload = _make_payload(
        {"component": "Column", "children": ["c1"]},
        extras=[{"id": "c1", "component": "Text", "text": "X", "weight": 0.5}],
    )
    validate_tool_input(catalog_v09, payload)

  def test_child_list_template_dinamico(self, catalog_v09):
    """ChildList con template {componentId, path} en vez de array estático."""
    payload = _make_payload(
        {
            "component": "List",
            "children": {"componentId": "item-tmpl", "path": "/items"},
        },
        extras=[{"id": "item-tmpl", "component": "Text", "text": {"path": "/name"}}],
    )
    validate_tool_input(catalog_v09, payload)


# --- Tests de inputs (validationRegexp, min/max, displayStyle) -----


class TestInputsOpcionales:
  """Propiedades opcionales de componentes de entrada."""

  def test_textfield_validation_regexp(self, catalog_v09):
    payload = _make_payload(
        {"component": "TextField", "label": "Código", "validationRegexp": "^[0-9]{4}$"}
    )
    validate_tool_input(catalog_v09, payload)

  def test_slider_con_min_y_label(self, catalog_v09):
    payload = _make_payload(
        {"component": "Slider", "value": 5, "max": 10, "min": 0, "label": "Edad"}
    )
    validate_tool_input(catalog_v09, payload)

  def test_slider_sin_min(self, catalog_v09):
    """min es opcional (default 0)."""
    payload = _make_payload({"component": "Slider", "value": 5, "max": 10})
    validate_tool_input(catalog_v09, payload)

  def test_choicepicker_display_style_chips(self, catalog_v09):
    payload = _make_payload({
        "component": "ChoicePicker",
        "options": [{"label": "A", "value": "a"}],
        "value": ["a"],
        "displayStyle": "chips",
    })
    validate_tool_input(catalog_v09, payload)

  def test_choicepicker_display_style_checkbox(self, catalog_v09):
    payload = _make_payload({
        "component": "ChoicePicker",
        "options": [{"label": "A", "value": "a"}],
        "value": ["a"],
        "displayStyle": "checkbox",
    })
    validate_tool_input(catalog_v09, payload)

  def test_choicepicker_filterable(self, catalog_v09):
    payload = _make_payload({
        "component": "ChoicePicker",
        "options": [{"label": "A", "value": "a"}],
        "value": ["a"],
        "filterable": True,
    })
    validate_tool_input(catalog_v09, payload)

  def test_datetimeinput_enable_date(self, catalog_v09):
    payload = _make_payload({
        "component": "DateTimeInput",
        "value": "2026-01-01",
        "enableDate": True,
        "label": "Fecha",
    })
    validate_tool_input(catalog_v09, payload)

  def test_datetimeinput_enable_time(self, catalog_v09):
    payload = _make_payload({
        "component": "DateTimeInput",
        "value": "12:00",
        "enableTime": True,
        "label": "Hora",
    })
    validate_tool_input(catalog_v09, payload)

  def test_datetimeinput_sin_enable(self, catalog_v09):
    """enableDate y enableTime son opcionales (default False)."""
    payload = _make_payload({"component": "DateTimeInput", "value": ""})
    validate_tool_input(catalog_v09, payload)


# --- Tests de accesibilidad ----------------------------------------


class TestAccesibilidad:
  """Propiedad accessibility en componentes."""

  def test_text_con_accessibility_label(self, catalog_v09):
    payload = _make_payload({
        "component": "Text",
        "text": "X",
        "accessibility": {"label": "Título principal"},
    })
    validate_tool_input(catalog_v09, payload)

  def test_text_con_accessibility_description(self, catalog_v09):
    payload = _make_payload({
        "component": "Text",
        "text": "X",
        "accessibility": {"description": "Descripción larga"},
    })
    validate_tool_input(catalog_v09, payload)

  def test_text_con_accessibility_completo(self, catalog_v09):
    payload = _make_payload({
        "component": "Text",
        "text": "X",
        "accessibility": {"label": "Título", "description": "Descripción"},
    })
    validate_tool_input(catalog_v09, payload)

  def test_button_con_accessibility(self, catalog_v09):
    payload = _make_payload(
        {
            "component": "Button",
            "child": "btn",
            "action": {"event": {"name": "x"}},
            "accessibility": {"label": "Enviar"},
        },
        extras=[_text("btn", "X")],
    )
    validate_tool_input(catalog_v09, payload)

  def test_textfield_con_accessibility(self, catalog_v09):
    payload = _make_payload({
        "component": "TextField",
        "label": "Email",
        "accessibility": {"label": "Correo electrónico"},
    })
    validate_tool_input(catalog_v09, payload)


# --- Tests de Image e Icon opcionales ------------------------------


class TestImageIcon:
  """Propiedades opcionales de Image e Icon."""

  @pytest.mark.parametrize("fit", ["contain", "cover", "fill", "none", "scaleDown"])
  def test_image_fit(self, catalog_v09, fit):
    payload = _make_payload(
        {"component": "Image", "url": "https://x.com/a.png", "fit": fit}
    )
    validate_tool_input(catalog_v09, payload)

  @pytest.mark.parametrize(
      "variant",
      ["icon", "avatar", "smallFeature", "mediumFeature", "largeFeature", "header"],
  )
  def test_image_variant(self, catalog_v09, variant):
    payload = _make_payload(
        {"component": "Image", "url": "https://x.com/a.png", "variant": variant}
    )
    validate_tool_input(catalog_v09, payload)

  def test_image_con_description(self, catalog_v09):
    payload = _make_payload({
        "component": "Image",
        "url": "https://x.com/a.png",
        "description": "Foto de perfil",
    })
    validate_tool_input(catalog_v09, payload)

  def test_icon_con_svg_path(self, catalog_v09):
    payload = _make_payload(
        {"component": "Icon", "name": {"svgPath": "M3 3L3 21M3 3L21 3"}}
    )
    validate_tool_input(catalog_v09, payload)

  def test_icon_con_data_binding(self, catalog_v09):
    """Icon con name bindeado al data model."""
    payload = _make_payload({"component": "Icon", "name": {"path": "/iconName"}})
    validate_tool_input(catalog_v09, payload)

  @pytest.mark.parametrize(
      "icon_name", ["add", "close", "check", "delete", "search", "settings", "star"]
  )
  def test_icon_nombres_bundled(self, catalog_v09, icon_name):
    payload = _make_payload({"component": "Icon", "name": icon_name})
    validate_tool_input(catalog_v09, payload)

  def test_icon_nombre_invalido_sin_repair(self, catalog_v09):
    """Icon con nombre no permitido falla sin repair."""
    payload = _make_payload({"component": "Icon", "name": "iconoInexistente"})
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, payload, repair=False)


# --- Tests de round-trip de propiedades opcionales -----------------


class TestRoundTripPropiedades:
  """Las propiedades opcionales sobreviven el round-trip por el stream."""

  def test_text_variant_round_trip(self, catalog_v09):
    payload = _make_payload({"component": "Text", "text": "Título", "variant": "h1"})
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=True)
    parts = _run_tool_use_stream(parser, payload)
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert a2ui_parts[0].a2ui_json == payload

  def test_tema_round_trip(self, catalog_v09):
    payload = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "s",
                "catalogId": CATALOG_ID,
                "theme": {"primaryColor": "#00BFFF", "agentDisplayName": "Agente"},
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{"id": "root", "component": "Text", "text": "X"}],
            },
        },
    ]
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=True)
    parts = _run_tool_use_stream(parser, payload)
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert a2ui_parts[0].a2ui_json == payload

  def test_accessibility_round_trip(self, catalog_v09):
    payload = _make_payload(
        {"component": "Text", "text": "X", "accessibility": {"label": "Título"}}
    )
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=True)
    parts = _run_tool_use_stream(parser, payload)
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert a2ui_parts[0].a2ui_json == payload

  def test_propiedades_se_convierten_a_a2uipart(self, catalog_v09):
    payload = _make_payload({"component": "Text", "text": "X", "variant": "h1"})
    part = to_a2ui_part(payload)
    assert part.data == payload
    assert json.loads(part.to_json_string()) == payload
