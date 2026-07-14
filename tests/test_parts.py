"""Tests de los helpers de transporte (parts.py).

Estos tests son puros: no tocan Anthropic ni A2UI, solo JSON y dataclasses.
"""

import json

import pytest

from anthropic_a2ui import (
    MIME_A2UI,
    parse_a2ui_part_json,
    to_a2ui_part,
)


class TestA2uiPart:

  def test_crea_part_con_mime_por_defecto(self):
    part = to_a2ui_part({"createSurface": {}})
    assert part.mime == MIME_A2UI
    assert part.data == {"createSurface": {}}

  def test_mime_es_application_a2ui_json(self):
    assert MIME_A2UI == "application/a2ui+json"

  def test_to_json_string_serializa_compacta(self):
    part = to_a2ui_part({"a": 1})
    s = part.to_json_string()
    assert json.loads(s) == {"a": 1}
    # ensure_ascii=False por defecto: acepta unicode sin escapar
    part2 = to_a2ui_part({"t": "café"})
    assert "café" in part2.to_json_string()

  def test_to_json_string_pasa_kwargs(self):
    part = to_a2ui_part({"a": 1})
    s = part.to_json_string(indent=2)
    assert "\n" in s

  def test_to_dict_devuelve_estructura_plana(self):
    part = to_a2ui_part([1, 2, 3])
    d = part.to_dict()
    assert d == {"mimeType": MIME_A2UI, "data": [1, 2, 3]}

  def test_part_es_frozen(self):
    part = to_a2ui_part({})
    with pytest.raises((AttributeError, TypeError)):
      part.data = "x"  # type: ignore[misc]

  def test_mime_personalizado(self):
    part = to_a2ui_part({}, mime="application/x-test")
    assert part.mime == "application/x-test"


class TestParseA2uiPartJson:

  def test_parsea_str_valido(self):
    assert parse_a2ui_part_json('{"a": 1}') == {"a": 1}

  def test_parsea_bytes(self):
    assert parse_a2ui_part_json(b"[1, 2]") == [1, 2]

  def test_lanza_valueerror_si_invalido(self):
    with pytest.raises(ValueError):
      parse_a2ui_part_json("{invalido")

  def test_lanza_valueerror_si_vacio(self):
    with pytest.raises(ValueError):
      parse_a2ui_part_json("")
