"""Prueba de fuego exhaustiva: 3 modelos, todas las funciones, todos los
mensajes, todas las propiedades opcionales.

Ejecuta casos de prueba diseñados para forzar que Claude use:

- Las 15 funciones del catálogo (14 basic + capitalize del minimal).
- Los 4 tipos de mensaje (createSurface, updateComponents, updateDataModel,
  deleteSurface).
- Todas las propiedades opcionales (variant, justify, align, direction,
  axis, fit, description, label, min, max, enableDate, enableTime, filterable,
  displayStyle, validationRegexp, theme, sendDataModel, accessibility, weight,
  checks, iconUrl, agentDisplayName, primaryColor).

Con 3 modelos:
- claude-haiku-4-5 (Kaiku)
- claude-opus-4-7 (Opus 4.7)
- claude-opus-4-8 (Opus 4.8)

Los resultados se guardan en results_exhaustive/ para el viewer.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

import anthropic

from anthropic_a2ui import (
  ClaudeA2uiPromptBuilder,
  ClaudeStreamParser,
  create_a2ui_tool,
  validate_tool_input,
)

RESULTS_DIR = Path(__file__).parent / "results_exhaustive"
RESULTS_DIR.mkdir(exist_ok=True)

MAX_TOKENS = 16384

MODELS = [
  "claude-haiku-4-5-20251001",
  "claude-opus-4-7",
  "claude-opus-4-8",
]

# Casos diseñados para forzar TODO. Cada caso tiene un prompt que pide
# explícitamente las funciones/propiedades que queremos ejercitar.
TEST_CASES = [
  {
    "id": "01_todas_funciones_validacion",
    "prompt": (
      "Crea un formulario de registro con los siguientes campos y "
      "validaciones:\n"
      "- Nombre: obligatorio, mínimo 2 caracteres (función length).\n"
      "- Email: obligatorio, formato email válido (función email).\n"
      "- Código postal: obligatorio, solo dígitos (función regex con patrón "
      "^[0-9]{5}$).\n"
      "- Edad: número entre 18 y 120 (función numeric con min 18 max 120).\n"
      "- Acepto términos: checkbox obligatorio (función required).\n"
      "Usa las funciones del catálogo A2UI en los checks de cada campo. "
      "El formulario debe estar en una Card con un título."
    ),
    "targets": ["required", "regex", "length", "numeric", "email"],
    "description": "Funciones de validación: required, regex, length, numeric, email",
  },
  {
    "id": "02_todas_funciones_formato",
    "prompt": (
      "Crea un panel de información financiera que use funciones de "
      "formato del catálogo A2UI:\n"
      "- Un texto que salude al usuario por nombre usando formatString "
      "(interpola 'Hola ${/name}').\n"
      "- Un texto que muestre un número formateado con 2 decimales usando "
      "formatNumber.\n"
      "- Un texto que muestre un precio en EUR usando formatCurrency.\n"
      "- Un texto que muestre la fecha actual formateada como 'dd/MM/yyyy' "
      "usando formatDate.\n"
      "- Un texto que diga '1 item' o 'N items' según un contador usando "
      "pluralize.\n"
      "Usa las funciones como FunctionCall en la propiedad text de cada "
      "componente Text."
    ),
    "targets": ["formatString", "formatNumber", "formatCurrency", "formatDate", "pluralize"],
    "description": "Funciones de formato: formatString, formatNumber, formatCurrency, formatDate, pluralize",
  },
  {
    "id": "03_funciones_logicas_y_openurl",
    "prompt": (
      "Crea una interfaz con:\n"
      "- Un TextField para una contraseña que sea válida solo si tiene "
      "contenido (required) Y NO está vacía. Usa la función 'and' con dos "
      "condiciones y la función 'not' para combinarlas.\n"
      "- Un TextField que sea válido si está vacío O si pasa una validación "
      "regex. Usa la función 'or'.\n"
      "- Un botón 'Abrir documentación' que al pulsarlo ejecute openUrl "
      "con la URL https://docs.example.com. Usa functionCall en la action "
      "del botón.\n"
      "Combina las funciones lógicas and, or, not en los checks."
    ),
    "targets": ["and", "or", "not", "openUrl"],
    "description": "Funciones lógicas: and, or, not + openUrl en action",
  },
  {
    "id": "04_todos_mensajes_y_ciclo_vida",
    "prompt": (
      "Crea una interfaz que demuestre el ciclo de vida completo de una "
      "superficie A2UI:\n"
      "1. Primero crea una superficie con createSurface (incluye theme con "
      "primaryColor '#FF5722', iconUrl y agentDisplayName 'Demo'.\n"
      "2. Luego actualiza los componentes con updateComponents (una columna "
      "con un título y un texto).\n"
      "3. Luego actualiza el data model con updateDataModel, estableciendo "
      "/title a 'Hola mundo' y /count a 5 (dos mensajes updateDataModel "
      "separados).\n"
      "4. Finalmente elimina la superficie con deleteSurface.\n"
      "Envía los 4 tipos de mensaje en orden: createSurface, "
      "updateComponents, updateDataModel, deleteSurface."
    ),
    "targets": ["createSurface", "updateComponents", "updateDataModel", "deleteSurface"],
    "description": "Ciclo de vida: createSurface + updateComponents + updateDataModel + deleteSurface",
  },
  {
    "id": "05_todas_props_opcionales_layout",
    "prompt": (
      "Crea una interfaz que use TODAS las propiedades opcionales de "
      "layout:\n"
      "- Un Row con justify='spaceBetween' y align='center'.\n"
      "- Un Column con justify='spaceAround' y align='stretch'.\n"
      "- Un List con direction='horizontal' y align='center'.\n"
      "- Un Divider con axis='vertical'.\n"
      "- Componentes hijos con weight (por ejemplo weight=2 en un hijo del "
      "Row y weight=0.5 en otro).\n"
      "- Usa accessibility con label y description en al menos un "
      "componente.\n"
      "Demuestra que cada propiedad de layout funciona."
    ),
    "targets": ["justify", "align", "direction", "axis", "weight", "accessibility"],
    "description": "Props layout: justify, align, direction, axis, weight, accessibility",
  },
  {
    "id": "06_todas_props_opcionales_inputs",
    "prompt": (
      "Crea una interfaz que use TODAS las propiedades opcionales de los "
      "componentes de entrada:\n"
      "- Un TextField con variant='longText' y validationRegexp='^[A-Z].*'.\n"
      "- Un TextField con variant='number'.\n"
      "- Un TextField con variant='obscured' (para contraseña).\n"
      "- Un ChoicePicker con variant='multipleSelection', "
      "displayStyle='chips' y filterable=true.\n"
      "- Un Slider con label='Volumen', min=0 y max=100.\n"
      "- Un DateTimeInput con enableDate=true, enableTime=true, "
      "label='Fecha y hora', min='2025-01-01' y max='2027-12-31'.\n"
      "- Un CheckBox con label y value=true.\n"
      "- Un Button con variant='primary' y otro con variant='borderless'.\n"
      "Usa cada propiedad opcional al menos una vez."
    ),
    "targets": ["variant", "validationRegexp", "displayStyle", "filterable", "min", "max", "enableDate", "enableTime", "label"],
    "description": "Props inputs: variant, validationRegexp, displayStyle, filterable, min, max, enableDate, enableTime",
  },
  {
    "id": "07_todas_props_opcionales_media_y_tema",
    "prompt": (
      "Crea una interfaz que use TODAS las propiedades opcionales de media "
      "y tema:\n"
      "- createSurface con theme completo: primaryColor='#00BFFF', "
      "iconUrl='https://example.com/icon.png', agentDisplayName='Galería'.\n"
      "- createSurface con sendDataModel=true.\n"
      "- Un Image con fit='cover', variant='largeFeature' y "
      "description='Foto principal'.\n"
      "- Un Image con variant='avatar'.\n"
      "- Un AudioPlayer con description='Pista de audio'.\n"
      "- Un Icon con name='settings'.\n"
      "- Un Text con variant='h1' y otro con variant='caption'.\n"
      "Demuestra cada propiedad opcional de media y tema."
    ),
    "targets": ["primaryColor", "iconUrl", "agentDisplayName", "sendDataModel", "fit", "variant", "description"],
    "description": "Props media+tema: theme, sendDataModel, fit, variant, description, iconUrl",
  },
  {
    "id": "08_todo_junto_dashboard_completo",
    "prompt": (
      "Crea un dashboard completo que combine todo lo posible:\n"
      "- createSurface con theme (primaryColor, agentDisplayName) y "
      "sendDataModel=true.\n"
      "- updateDataModel para inicializar datos (ventas, nombreUsuario, "
      "fechaActual).\n"
      "- updateComponents con:\n"
      "  * Row con justify='spaceBetween' conteniendo 3 Cards.\n"
      "  * Cada Card tiene un Text con variant='h3' (título) y un Text con "
      "formatCurrency o formatNumber.\n"
      "  * Un List con direction='vertical' de productos.\n"
      "  * Un ChoicePicker con displayStyle='chips' y filterable=true.\n"
      "  * Un Slider con label y min/max.\n"
      "  * Un DateTimeInput con enableDate y enableTime.\n"
      "  * Un Button primary con action que use formatString en su label.\n"
      "  * Un Modal con trigger y content.\n"
      "  * Un Divider con axis='horizontal'.\n"
      "  * Un Text con pluralize.\n"
      "  * accessibility en al menos un componente.\n"
      "  * weight en hijos del Row.\n"
      "- Un segundo updateDataModel para actualizar /ventas a un valor nuevo.\n"
      "Usa tantas funciones y propiedades del catálogo como puedas."
    ),
    "targets": ["createSurface", "updateComponents", "updateDataModel", "formatCurrency", "formatNumber", "formatString", "pluralize", "theme", "sendDataModel", "Modal", "Divider", "accessibility", "weight"],
    "description": "Dashboard completo: combina todo (mensajes, funciones, props, componentes)",
  },
]


def run_test(
  client: anthropic.Anthropic,
  builder: ClaudeA2uiPromptBuilder,
  tool: dict,
  parser: ClaudeStreamParser,
  model: str,
  case: dict,
) -> dict:
  result = {
    "id": case["id"],
    "model": model,
    "description": case["description"],
    "prompt": case["prompt"],
    "targets": case["targets"],
    "status": "pending",
    "text": "",
    "a2ui_json": None,
    "error": None,
    "validation_ok": False,
    "elapsed_ms": 0,
    "components_used": [],
    "functions_used": [],
    "messages_used": [],
    "properties_used": [],
  }

  start = time.monotonic()
  catalog = builder.get_catalog()

  try:
    with client.messages.stream(
      model=model,
      system=builder.build(
        role_description=(
          "Eres un asistente experto que construye interfaces de usuario "
          "declarativas usando el protocolo A2UI. Cuando el usuario pida "
          "una UI, invoca la tool send_a2ui_json_to_client con un payload "
          "A2UI válido. Usa todas las funciones del catálogo (required, "
          "regex, length, numeric, email, formatString, formatNumber, "
          "formatCurrency, formatDate, pluralize, openUrl, and, or, not) "
          "cuando sean apropiadas. Usa todas las propiedades opcionales de "
          "los componentes (variant, justify, align, direction, axis, fit, "
          "weight, accessibility, checks, displayStyle, filterable, min, "
          "max, enableDate, enableTime, validationRegexp, label, "
          "description, theme, sendDataModel). Combina los tipos de "
          "mensaje createSurface, updateComponents, updateDataModel y "
          "deleteSurface según el flujo. Pon el esfuerzo en la calidad y "
          "completitud del JSON A2UI."
        ),
        include_schema=True,
        include_examples=True,
      ),
      tools=[tool],
      max_tokens=MAX_TOKENS,
      messages=[{"role": "user", "content": case["prompt"]}],
    ) as stream:
      text_parts = []
      a2ui_payloads = []

      for event in stream:
        for part in parser.process_event(event):
          if part.text:
            text_parts.append(part.text)
          if part.a2ui_json is not None:
            a2ui_payloads.append(part.a2ui_json)

      result["text"] = "".join(text_parts)
      result["elapsed_ms"] = int((time.monotonic() - start) * 1000)

      if a2ui_payloads:
        payload = a2ui_payloads[0]
        result["a2ui_json"] = payload

        # Analizar qué se usó
        result["components_used"] = _extract_components(payload)
        result["functions_used"] = _extract_functions(payload)
        result["messages_used"] = _extract_messages(payload)
        result["properties_used"] = _extract_properties(payload)

        # Validar
        try:
          validate_tool_input(catalog, payload, strict_integrity=True)
          result["validation_ok"] = True
          result["status"] = "ok"
        except Exception as ve:
          result["validation_ok"] = False
          result["status"] = "invalid"
          result["error"] = f"Validación: {type(ve).__name__}: {str(ve)[:500]}"
      else:
        result["status"] = "no_a2ui"
        result["error"] = "Claude no generó A2UI"

  except Exception as exc:
    result["status"] = "error"
    result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    result["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    traceback.print_exc()

  return result


def _extract_components(payload):
  comps = set()
  for msg in payload:
    if "updateComponents" in msg:
      for c in msg["updateComponents"]["components"]:
        comps.add(c.get("component", "?"))
  return sorted(comps)


def _extract_functions(payload):
  funcs = set()
  for msg in payload:
    if "updateComponents" in msg:
      for c in msg["updateComponents"]["components"]:
        for check in c.get("checks", []):
          cond = check.get("condition", {})
          if isinstance(cond, dict) and "call" in cond:
            funcs.add(cond["call"])
        text = c.get("text", {})
        if isinstance(text, dict) and "call" in text:
          funcs.add(text["call"])
        action = c.get("action", {})
        if "functionCall" in action:
          funcs.add(action["functionCall"].get("call", "?"))
  return sorted(funcs)


def _extract_messages(payload):
  msgs = set()
  for m in payload:
    for k in m:
      if k != "version":
        msgs.add(k)
  return sorted(msgs)


def _extract_properties(payload):
  props = set()
  for msg in payload:
    if "createSurface" in msg:
      cs = msg["createSurface"]
      for k in cs:
        if k not in ("surfaceId", "catalogId"):
          props.add(f"createSurface.{k}")
      if "theme" in cs:
        for tk in cs["theme"]:
          props.add(f"theme.{tk}")
    if "updateComponents" in msg:
      for c in msg["updateComponents"]["components"]:
        for k in c:
          if k not in ("id", "component"):
            props.add(k)
    if "updateDataModel" in msg:
      dmu = msg["updateDataModel"]
      for k in dmu:
        if k != "surfaceId":
          props.add(f"updateDataModel.{k}")
  return sorted(props)


def main():
  api_key = os.environ.get("ANTHROPIC_API_KEY")
  if not api_key:
    print("ERROR: Define ANTHROPIC_API_KEY.", file=sys.stderr)
    sys.exit(1)

  builder = ClaudeA2uiPromptBuilder(version="0.9")
  catalog = builder.get_catalog()
  tool = create_a2ui_tool(catalog)
  parser = ClaudeStreamParser(catalog=catalog, strict_tool_validation=False)

  client = anthropic.Anthropic(api_key=api_key)

  total = len(MODELS) * len(TEST_CASES)
  print(f"Prueba exhaustiva: {len(TEST_CASES)} casos × {len(MODELS)} modelos = {total} ejecuciones")
  print(f"Resultados: {RESULTS_DIR}")
  print("=" * 70)

  all_results = []
  stats = {"ok": 0, "invalid": 0, "no_a2ui": 0, "error": 0}

  # Set de TODO lo que queremos cubrir
  all_targets_components = {
    "Text", "Image", "Icon", "Video", "AudioPlayer", "Row", "Column",
    "List", "Card", "Tabs", "Modal", "Divider", "Button", "TextField",
    "CheckBox", "ChoicePicker", "Slider", "DateTimeInput",
  }
  all_targets_functions = {
    "required", "regex", "length", "numeric", "email", "formatString",
    "formatNumber", "formatCurrency", "formatDate", "pluralize", "openUrl",
    "and", "or", "not",
  }
  all_targets_messages = {
    "createSurface", "updateComponents", "updateDataModel", "deleteSurface",
  }
  all_targets_props = {
    "variant", "justify", "align", "direction", "axis", "fit", "description",
    "label", "min", "max", "enableDate", "enableTime", "filterable",
    "displayStyle", "validationRegexp", "weight", "accessibility", "checks",
    "theme", "sendDataModel", "primaryColor", "iconUrl", "agentDisplayName",
  }

  covered_components = set()
  covered_functions = set()
  covered_messages = set()
  covered_props = set()

  i = 0
  for model in MODELS:
    model_short = model.replace("claude-", "").replace("-20251001", "").replace("-20250929", "")
    print(f"\n{'='*70}")
    print(f"Modelo: {model} ({model_short})")
    print(f"{'='*70}")

    for case in TEST_CASES:
      i += 1
      print(f"\n[{i}/{total}] {case['id']} [{model_short}]")
      print(f"  {case['description']}")

      result = run_test(client, builder, tool, parser, model, case)
      all_results.append(result)

      # Guardar JSON
      if result["a2ui_json"] is not None:
        json_path = RESULTS_DIR / f"{model_short}__{case['id']}.json"
        with open(json_path, "w", encoding="utf-8") as f:
          json.dump(result["a2ui_json"], f, indent=2, ensure_ascii=False)

      # Acumular cobertura
      covered_components.update(result["components_used"])
      covered_functions.update(result["functions_used"])
      covered_messages.update(result["messages_used"])
      covered_props.update(result["properties_used"])

      # Reporte
      status = result["status"]
      elapsed = result["elapsed_ms"]
      stats[status] = stats.get(status, 0) + 1

      if status == "ok":
        print(f"  ✓ OK ({elapsed}ms) — comps={len(result['components_used'])} "
              f"funcs={len(result['functions_used'])} "
              f"msgs={len(result['messages_used'])} "
              f"props={len(result['properties_used'])}")
      elif status == "invalid":
        print(f"  ✗ INVALID ({elapsed}ms) — {result['error'][:100]}")
      elif status == "no_a2ui":
        print(f"  ⚠ SIN A2UI ({elapsed}ms)")
      else:
        print(f"  ✗ ERROR ({elapsed}ms) — {result['error'][:100]}")

  # Resumen de cobertura
  print(f"\n{'='*70}")
  print(f"COBERTURA TOTAL")
  print(f"{'='*70}")
  print(f"Componentes: {len(covered_components)}/{len(all_targets_components)} "
        f"({len(covered_components)*100//len(all_targets_components)}%)")
  missing_c = all_targets_components - covered_components
  if missing_c:
    print(f"  Faltan: {sorted(missing_c)}")
  print(f"Funciones: {len(covered_functions)}/{len(all_targets_functions)} "
        f"({len(covered_functions)*100//len(all_targets_functions)}%)")
  missing_f = all_targets_functions - covered_functions
  if missing_f:
    print(f"  Faltan: {sorted(missing_f)}")
  print(f"Mensajes: {len(covered_messages)}/{len(all_targets_messages)} "
        f"({len(covered_messages)*100//len(all_targets_messages)}%)")
  missing_m = all_targets_messages - covered_messages
  if missing_m:
    print(f"  Faltan: {sorted(missing_m)}")
  print(f"Propiedades: {len(covered_props)}/{len(all_targets_props)} "
        f"({len(covered_props)*100//len(all_targets_props)}%)")
  missing_p = all_targets_props - covered_props
  if missing_p:
    print(f"  Faltan: {sorted(missing_p)}")

  print(f"\n{'='*70}")
  print(f"Por modelo:")
  for model in MODELS:
    model_short = model.replace("claude-", "").replace("-20251001", "").replace("-20250929", "")
    model_results = [r for r in all_results if r["model"] == model]
    ok = sum(1 for r in model_results if r["status"] == "ok")
    print(f"  {model_short:15s} {ok}/{len(model_results)} OK")

  # Guardar resumen
  summary = {
    "models": MODELS,
    "total": total,
    "stats": stats,
    "coverage": {
      "components": {
        "covered": sorted(covered_components),
        "missing": sorted(missing_c),
        "total": len(all_targets_components),
      },
      "functions": {
        "covered": sorted(covered_functions),
        "missing": sorted(missing_f),
        "total": len(all_targets_functions),
      },
      "messages": {
        "covered": sorted(covered_messages),
        "missing": sorted(missing_m),
        "total": len(all_targets_messages),
      },
      "properties": {
        "covered": sorted(covered_props),
        "missing": sorted(missing_p),
        "total": len(all_targets_props),
      },
    },
    "results": [
      {
        "id": r["id"],
        "model": r["model"],
        "description": r["description"],
        "status": r["status"],
        "validation_ok": r["validation_ok"],
        "elapsed_ms": r["elapsed_ms"],
        "error": r["error"],
        "text": r["text"][:200] if r["text"] else "",
        "has_json": r["a2ui_json"] is not None,
        "components_used": r["components_used"],
        "functions_used": r["functions_used"],
        "messages_used": r["messages_used"],
        "properties_used": r["properties_used"],
      }
      for r in all_results
    ],
  }
  summary_path = RESULTS_DIR / "summary.json"
  with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

  print(f"\nResumen guardado: {summary_path}")
  print(f"\nViewer: http://localhost:8765/viewer_exhaustive.html")


if __name__ == "__main__":
  main()