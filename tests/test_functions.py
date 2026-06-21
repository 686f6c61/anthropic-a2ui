"""Tests parametrizados por cada función del catálogo A2UI.

Cubre las 15 funciones únicas: 14 del Basic Catalog v0.9 (required, regex,
length, numeric, email, formatString, formatNumber, formatCurrency,
formatDate, pluralize, openUrl, and, or, not) y ``capitalize`` del minimal
v0.9.

Para cada función se verifica:

1. **Validación**: el payload pasa ``A2uiValidator.validate``.
2. **Contexto correcto**: la función se usa donde el protocolo permite
   (checks, text dinámico o action).
3. **Round-trip tool use**: el payload viaja por el stream y se reconstruye.
4. **Transporte**: se convierte a ``A2uiPart`` correctamente.

Estos tests garantizan que Claude puede usar cualquier función del catálogo
en su contexto natural (validación, formato o acción).
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

from ._function_specs import (
    all_function_payloads,
    basic_function_payloads,
)


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
  """Ejecuta un stream simulado de tool use y devuelve los ResponsePart."""
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


# --- Tests de validación por función (Basic v0.9) ------------------


@pytest.mark.parametrize("name, context, payload", basic_function_payloads())
class TestFuncionesBasic:
  """Cada una de las 14 funciones del Basic v0.9 valida en su contexto."""

  def test_valida_contra_catalogo_basic(self, catalog_v09, name, context, payload):
    """El payload pasa el validador del Basic v0.9."""
    validate_tool_input(catalog_v09, payload, strict_integrity=True)

  def test_contexto_es_valido(self, name, context, payload):
    """El contexto está entre los permitidos."""
    assert context in ("check", "text", "action")

  def test_function_call_tiene_call_y_args(self, name, context, payload):
    """El FunctionCall dentro del payload tiene call y args."""
    # Buscar el FunctionCall en el payload
    raw = json.dumps(payload)
    assert f'"call": "{name}"' in raw
    assert '"args"' in raw

  def test_round_trip_tool_use(self, catalog_v09, name, context, payload):
    """El payload viaja por el stream y se reconstruye íntegro."""
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=True)
    parts = _run_tool_use_stream(parser, payload)
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert len(a2ui_parts) == 1
    assert a2ui_parts[0].a2ui_json == payload

  def test_se_convierte_a_a2uipart(self, name, context, payload):
    """El payload se envuelve en A2uiPart correctamente."""
    part = to_a2ui_part(payload)
    assert part.data == payload
    assert part.mime == "application/a2ui+json"


# --- Tests de contexto: checks vs text vs action -------------------


class TestContextoFunciones:
  """Verifica que cada función se usa en el contexto correcto."""

  def test_funciones_check_retornan_boolean(self):
    """Las funciones de check retornan boolean."""
    from ._function_specs import BASIC_FUNCTION_SPECS

    check_funcs = {
        "required",
        "regex",
        "length",
        "numeric",
        "email",
        "and",
        "or",
        "not",
    }
    for name, ctx, payload in BASIC_FUNCTION_SPECS:
      if ctx == "check":
        raw = json.dumps(payload)
        assert '"returnType": "boolean"' in raw, f"{name} debe retornar boolean"

  def test_funciones_text_retornan_string(self):
    """Las funciones de text retornan string."""
    from ._function_specs import BASIC_FUNCTION_SPECS

    text_funcs = {
        "formatString",
        "formatNumber",
        "formatCurrency",
        "formatDate",
        "pluralize",
    }
    for name, ctx, payload in BASIC_FUNCTION_SPECS:
      if ctx == "text":
        raw = json.dumps(payload)
        assert '"returnType": "string"' in raw, f"{name} debe retornar string"

  def test_openurl_retorna_void(self):
    """openUrl retorna void (no produce valor)."""
    from ._function_specs import BASIC_FUNCTION_SPECS

    for name, ctx, payload in BASIC_FUNCTION_SPECS:
      if name == "openUrl":
        raw = json.dumps(payload)
        assert '"returnType": "void"' in raw

  def test_funciones_check_en_checks_de_textfield(self):
    """Las funciones de check van dentro de checks[].condition."""
    from ._function_specs import BASIC_FUNCTION_SPECS

    for name, ctx, payload in BASIC_FUNCTION_SPECS:
      if ctx == "check":
        # El payload debe tener un componente TextField con checks
        found = False
        for m in payload:
          if "updateComponents" in m:
            for comp in m["updateComponents"]["components"]:
              if comp.get("component") == "TextField" and "checks" in comp:
                found = True
        assert found, f"{name} debe usarse en checks de TextField"

  def test_funciones_text_en_text_de_componente(self):
    """Las funciones de text van como valor de text de un Text."""
    from ._function_specs import BASIC_FUNCTION_SPECS

    for name, ctx, payload in BASIC_FUNCTION_SPECS:
      if ctx == "text":
        found = False
        for m in payload:
          if "updateComponents" in m:
            for comp in m["updateComponents"]["components"]:
              if comp.get("component") == "Text" and isinstance(comp.get("text"), dict):
                if "call" in comp["text"]:
                  found = True
        assert found, f"{name} debe usarse como text de un Text"

  def test_openurl_en_action_functioncall(self):
    """openUrl va dentro de action.functionCall de un Button."""
    from ._function_specs import BASIC_FUNCTION_SPECS

    for name, ctx, payload in BASIC_FUNCTION_SPECS:
      if name == "openUrl":
        found = False
        for m in payload:
          if "updateComponents" in m:
            for comp in m["updateComponents"]["components"]:
              if comp.get("component") == "Button":
                action = comp.get("action", {})
                if "functionCall" in action:
                  found = True
        assert found, "openUrl debe usarse en action.functionCall de Button"


# --- Tests de capitalize (minimal v0.9) ----------------------------


class TestFuncionCapitalize:
  """capitalize es la función exclusiva del catálogo minimal v0.9."""

  def test_capitalize_valida_en_minimal(self, catalog_minimal):
    from ._function_specs import CAPITALIZE_SPEC

    _, _, payload = CAPITALIZE_SPEC
    validate_tool_input(catalog_minimal, payload, strict_integrity=True)

  def test_capitalize_no_valida_en_basic_sin_repair(self, catalog_v09):
    """capitalize no existe en el Basic Catalog, asi que no valida sin repair."""
    from ._function_specs import CAPITALIZE_SPEC

    _, _, payload = CAPITALIZE_SPEC
    with pytest.raises(Exception):
      validate_tool_input(catalog_v09, payload, strict_integrity=True, repair=False)

  def test_capitalize_se_repara_en_basic(self, catalog_v09):
    """Con repair=True, capitalize se sustituye por un literal y valida."""
    from ._function_specs import CAPITALIZE_SPEC

    _, _, payload = CAPITALIZE_SPEC
    # repair_functions sustituye capitalize (no existe en basic) por ""
    validate_tool_input(catalog_v09, payload, strict_integrity=True, repair=True)

  def test_capitalize_retorna_string(self):
    from ._function_specs import CAPITALIZE_SPEC

    _, _, payload = CAPITALIZE_SPEC
    raw = json.dumps(payload)
    assert '"returnType": "string"' in raw

  def test_capitalize_round_trip(self, catalog_minimal):
    from ._function_specs import CAPITALIZE_SPEC

    _, _, payload = CAPITALIZE_SPEC
    # Sin repair para que capitalize se preserve (es valida en el minimal)
    parser = ClaudeStreamParser(
        catalog=catalog_minimal, strict_tool_validation=True, repair=False
    )
    parts = _run_tool_use_stream(parser, payload)
    a2ui_parts = [p for p in parts if p.a2ui_json is not None]
    assert len(a2ui_parts) == 1
    assert a2ui_parts[0].a2ui_json == payload


# --- Test de cobertura total: 15 funciones -------------------------


class TestCoberturaFunciones:
  """Verifica que se cubren TODAS las funciones únicas de A2UI."""

  def test_hay_15_funcs_unicas(self):
    from ._function_specs import all_function_payloads

    all_funcs = all_function_payloads()
    assert len(all_funcs) == 15

  def test_nombres_son_unicos(self):
    from ._function_specs import all_function_payloads

    names = [name for name, _, _ in all_function_payloads()]
    assert len(names) == len(set(names))

  def test_cubre_14_funcs_basic(self, catalog_v09):
    """Las 14 funciones del Basic están en las specs."""
    from ._function_specs import basic_function_payloads

    spec_names = {name for name, _, _ in basic_function_payloads()}
    catalog_funcs = set(catalog_v09.catalog_schema.get("functions", {}).keys())
    assert spec_names == catalog_funcs

  def test_cubre_capitalize_minimal(self, catalog_minimal):
    """capitalize del minimal está en las specs."""
    from ._function_specs import all_function_payloads

    all_names = {name for name, _, _ in all_function_payloads()}
    assert "capitalize" in all_names

  def test_union_da_15_funcs(self, catalog_v09, catalog_minimal):
    """La unión de funciones de Basic + Minimal da 15 únicas."""
    all_funcs = set()
    all_funcs.update(catalog_v09.catalog_schema.get("functions", {}).keys())
    all_funcs.update(catalog_minimal.catalog_schema.get("functions", {}).keys())
    assert len(all_funcs) == 15
