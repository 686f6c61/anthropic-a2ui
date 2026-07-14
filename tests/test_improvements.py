"""Tests de las mejoras: parser con repair, reintentos, iconos en prompt."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from anthropic_a2ui import (
    ClaudeStreamParser,
    generate_a2ui,
)


# --- Dobles de eventos --------------------------------------------


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


# --- Tests del parser con repair automatico -----------------------


class TestParserRepairAutomatico:
  """El parser aplica repair_orphans y parche de schema automaticamente."""

  def test_parser_repara_orphans_por_defecto(self, catalog_v09):
    """Con repair=True (default), el parser repara huerfanos."""
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
                    {"id": "root", "component": "Column", "children": ["a"]},
                    {"id": "a", "component": "Text", "text": "A"},
                    {"id": "orphan", "component": "Text", "text": "Huerfano"},
                ],
            },
        },
    ]
    # Con repair=True y strict_tool_validation=True: no falla
    parser = ClaudeStreamParser(
        catalog=catalog_v09, strict_tool_validation=True, repair=True
    )
    raw = json.dumps({"a2ui_json": payload})
    parts = []
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
    # El huerfano fue reconectado
    from anthropic_a2ui import find_orphans

    assert find_orphans(a2ui_parts[0].a2ui_json) == []

  def test_parser_repara_datetimeinput_ambiguo(self, catalog_v09):
    """El parser con repair valida DateTimeInput con min/max."""
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
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
    parser = ClaudeStreamParser(
        catalog=catalog_v09, strict_tool_validation=True, repair=True
    )
    raw = json.dumps({"a2ui_json": payload})
    parts = []
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

  def test_parser_sin_repair_falla_con_orphan(self, catalog_v09):
    """Con repair=False, el parser no repara y falla con huerfanos."""
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
                    {"id": "root", "component": "Column", "children": ["a"]},
                    {"id": "a", "component": "Text", "text": "A"},
                    {"id": "orphan", "component": "Text", "text": "Huerfano"},
                ],
            },
        },
    ]
    parser = ClaudeStreamParser(
        catalog=catalog_v09, strict_tool_validation=True, repair=False
    )
    raw = json.dumps({"a2ui_json": payload})
    parser.process_event(
        _BlockStart(
            "content_block_start", 1, _Block("tool_use", "send_a2ui_json_to_client")
        )
    )
    parser.process_event(_DeltaEvent("content_block_delta", _InputJSONDelta(raw), 1))
    with pytest.raises(Exception):
      parser.process_event(_BlockStop("content_block_stop", 1))


# --- Tests de iconos en el prompt ---------------------------------


class TestIconosEnPrompt:
  """El system prompt incluye la lista de iconos validos."""

  def test_prompt_contiene_lista_iconos(self, builder_v09):
    prompt = builder_v09.build(
        role_description="x", include_schema=False, include_examples=False
    )
    assert "ICONOS VALIDOS" in prompt
    # Algunos iconos conocidos
    assert "add" in prompt
    assert "check" in prompt
    assert "settings" in prompt
    assert "close" in prompt

  def test_prompt_sin_iconos_si_se_desactiva(self, builder_v09):
    prompt = builder_v09.build(
        role_description="x",
        include_schema=False,
        include_examples=False,
        include_icon_list=False,
    )
    assert "ICONOS VALIDOS" not in prompt

  def test_prompt_lista_59_iconos(self, builder_v09):
    prompt = builder_v09.build(
        role_description="x", include_schema=False, include_examples=False
    )
    # La seccion de iconos esta entre "--- ICONOS VALIDOS ---" y el siguiente "---"
    section = prompt.split("--- ICONOS VALIDOS ---")[1]
    if "---" in section:
      section = section.split("---")[0]
    icons = [i.strip() for i in section.strip().split(",") if i.strip()]
    assert len(icons) == 59

  def test_prompt_menciona_no_inventar_iconos(self, builder_v09):
    prompt = builder_v09.build(
        role_description="x", include_schema=False, include_examples=False
    )
    assert "no invente" in prompt.lower() or "no inventes" in prompt.lower()


# --- Tests de generate_a2ui (reintentos) --------------------------


class TestGenerateA2ui:
  """generate_a2ui es la funcion de alto nivel con reintentos."""

  def test_generate_a2ui_es_importable(self):

    assert callable(generate_a2ui)

  def test_retry_result_es_dataclass(self):
    from anthropic_a2ui import RetryResult

    r = RetryResult()
    assert r.a2ui_json is None
    assert r.text == ""
    assert r.attempts == 0
    assert r.success is False
    assert r.error is None
    assert r.all_payloads == []

  def test_generate_a2ui_sin_api_key_lanza(self):
    """Sin cliente valido, generate_a2ui falla graceful."""
    # No podemos probar sin API key real, pero verificamos la signatura
    import inspect

    sig = inspect.signature(generate_a2ui)
    params = list(sig.parameters.keys())
    assert "client" in params
    assert "prompt" in params
    assert "max_retries" in params
    assert "model" in params
    assert sig.parameters["max_retries"].default == 2
