"""Prueba de fuego: llama a Claude con anthropic-a2ui y valida los resultados.

Este script NO construye A2UI a mano. Claude genera los JSON usando el
system prompt que nuestro paquete construye. El flujo es:

1. Crear builder, prompt, tool y parser con anthropic-a2ui.
2. Para cada caso de prueba, llamar a Claude con un prompt natural.
3. Si Claude invoca la tool, validar el JSON contra el esquema A2UI.
4. Si Claude emite tags <a2ui-json>, parsearlos.
5. Guardar cada JSON validado en results/ para que el viewer HTML lo renderice.

Los resultados se guardan como archivos JSON numerados para que el viewer
los cargue y los muestre visualmente con @a2ui/lit.

Requiere:
- ANTHROPIC_API_KEY en el entorno.
- anthropic-a2ui instalado (editable o desde PyPI).
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

import anthropic

from anthropic_a2ui import (
  ClaudeA2uiPromptBuilder,
  ClaudeStreamParser,
  create_a2ui_tool,
  to_a2ui_part,
  validate_tool_input,
)

# --- Configuración --------------------------------------------------

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 8192

# Casos de prueba: prompts naturales que un humano le pediría a Claude.
# Cada caso cubre un tipo de UI distinto para ejercitar componentes
# diferentes del catálogo A2UI.
TEST_CASES = [
  {
    "id": "01_formulario_contacto",
    "prompt": (
      "Crea un formulario de contacto con los siguientes campos: nombre "
      "completo, email, asunto y mensaje. Incluye un botón de envío. "
      "El email debe validar formato. Haz que el formulario sea vertical "
      "y claro."
    ),
    "description": "Formulario de contacto: TextField, Button, validación email",
  },
  {
    "id": "02_tarjeta_perfil",
    "prompt": (
      "Crea una tarjeta de perfil de usuario que muestre un avatar, el "
      "nombre como título, una breve biografía, y dos botones: 'Seguir' "
      "(primario) y 'Mensaje' (secundario)."
    ),
    "description": "Tarjeta de perfil: Card, Image, Text, Button variant",
  },
  {
    "id": "03_dashboard_ventas",
    "prompt": (
      "Crea un dashboard de ventas con tres tarjetas en una fila: "
      "ingresos totales, número de pedidos y clientes nuevos. Cada tarjeta "
      "tiene un título, un número grande y una etiqueta. Debajo, una "
      "lista de los 3 productos más vendidos con su nombre y precio."
    ),
    "description": "Dashboard: Row, Card, Text variant, List, formatCurrency",
  },
  {
    "id": "04_encuesta_preferencias",
    "prompt": (
      "Crea una encuesta de preferencias con tres preguntas: "
      "1) ¿Qué tipo de música prefieres? (elección múltiple: Rock, Jazz, "
      "Clásica, Electrónica). "
      "2) ¿Cuántas horas a la semana escuchas música? (slider 0-40). "
      "3) ¿Aceptas recibir newsletters? (checkbox). "
      "Incluye un botón de enviar."
    ),
    "description": "Encuesta: ChoicePicker, Slider, CheckBox, Button",
  },
  {
    "id": "05_calendario_cita",
    "prompt": (
      "Crea un formulario para agendar una cita médica: selecciona fecha "
      "y hora, tipo de consulta (selección única: Presencial, Videollamada), "
      "y un campo de notas. Muestra el tipo de consulta como chips "
      "filtrables."
    ),
    "description": "Cita médica: DateTimeInput, ChoicePicker chips, TextField",
  },
  {
    "id": "06_galeria_producto",
    "prompt": (
      "Crea una galería de producto con pestañas: una pestaña muestra la "
      "imagen principal y descripción, otra pestaña muestra una lista de "
      "tres imágenes thumbnails, y la tercera muestra un video del "
      "producto en acción."
    ),
    "description": "Galería: Tabs, Image, Text, List, Video",
  },
  {
    "id": "07_configuracion_notificaciones",
    "prompt": (
      "Crea un panel de configuración de notificaciones con switches "
      "(checkbox): notificaciones por email, push, SMS. Cada una con una "
      "descripción debajo. Usa un diseño en columnas con un título "
      "'Notificaciones'. Al final, un botón 'Guardar cambios'."
    ),
    "description": "Configuración: Column, CheckBox, Text, Button",
  },
  {
    "id": "08_modal_confirmacion",
    "prompt": (
      "Crea una interfaz que muestre un botón 'Eliminar cuenta'. Al "
      "pulsarlo, se abre un modal de confirmación con un mensaje de "
      "advertencia y dos botones: 'Cancelar' (secundario) y 'Eliminar "
      "definitivamente' (primario)."
    ),
    "description": "Modal: Modal, Button, Text, ventanas emergentes",
  },
]


# --- Ejecución ------------------------------------------------------


def run_test_case(
  client: anthropic.Anthropic,
  builder: ClaudeA2uiPromptBuilder,
  tool: dict,
  parser: ClaudeStreamParser,
  case: dict,
) -> dict:
  """Ejecuta un caso de prueba y devuelve el resultado.

  Returns:
    Dict con: id, description, status (ok/fail), text, a2ui_json, error,
    validation_ok, elapsed_ms.
  """
  result = {
    "id": case["id"],
    "description": case["description"],
    "prompt": case["prompt"],
    "status": "pending",
    "text": "",
    "a2ui_json": None,
    "error": None,
    "validation_ok": False,
    "elapsed_ms": 0,
  }

  start = time.monotonic()
  catalog = builder.get_catalog()

  try:
    # Llamar a Claude con streaming
    with client.messages.stream(
      model=MODEL,
      system=builder.build(
        role_description=(
          "Eres un asistente que construye interfaces de usuario "
          "declarativas usando el protocolo A2UI. Cuando el usuario pida "
          "una UI, invoca la tool send_a2ui_json_to_client con un payload "
          "A2UI válido. Sé conciso en el texto conversacional y pon el "
          "esfuerzo en la calidad del JSON."
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
        result["a2ui_json"] = a2ui_payloads[0]
        # Validar contra el esquema
        try:
          validate_tool_input(catalog, a2ui_payloads[0], strict_integrity=True)
          result["validation_ok"] = True
          result["status"] = "ok"
        except Exception as ve:
          result["validation_ok"] = False
          result["status"] = "invalid"
          result["error"] = f"Validación falló: {type(ve).__name__}: {str(ve)[:500]}"
      else:
        result["status"] = "no_a2ui"
        result["error"] = "Claude no generó ningún payload A2UI"

  except Exception as exc:
    result["status"] = "error"
    result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    result["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    traceback.print_exc()

  return result


def main() -> None:
  api_key = os.environ.get("ANTHROPIC_API_KEY")
  if not api_key:
    print("ERROR: Define ANTHROPIC_API_KEY.", file=sys.stderr)
    sys.exit(1)

  # Inicializar paquete
  builder = ClaudeA2uiPromptBuilder(version="0.9")
  catalog = builder.get_catalog()
  tool = create_a2ui_tool(catalog)
  parser = ClaudeStreamParser(catalog=catalog, strict_tool_validation=False)

  client = anthropic.Anthropic(api_key=api_key)

  print(f"Prueba de fuego: {len(TEST_CASES)} casos con {MODEL}")
  print(f"Renderer: @a2ui/lit v0.10.1 desde CDN")
  print(f"Resultados: {RESULTS_DIR}")
  print("=" * 60)

  all_results = []
  ok_count = 0
  invalid_count = 0
  no_a2ui_count = 0
  error_count = 0

  for i, case in enumerate(TEST_CASES, 1):
    print(f"\n[{i}/{len(TEST_CASES)}] {case['id']}: {case['description']}")
    print(f"  Prompt: {case['prompt'][:80]}...")

    result = run_test_case(client, builder, tool, parser, case)
    all_results.append(result)

    # Guardar el JSON A2UI en un archivo para el viewer
    if result["a2ui_json"] is not None:
      json_path = RESULTS_DIR / f"{case['id']}.json"
      with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result["a2ui_json"], f, indent=2, ensure_ascii=False)
      print(f"  JSON guardado: {json_path}")

    # Reporte
    status = result["status"]
    elapsed = result["elapsed_ms"]
    if status == "ok":
      ok_count += 1
      print(f"  ✓ OK ({elapsed}ms) — validación pasada")
      if result["text"]:
        print(f"  Texto: {result['text'][:100]}...")
    elif status == "invalid":
      invalid_count += 1
      print(f"  ✗ INVALID ({elapsed}ms) — {result['error']}")
    elif status == "no_a2ui":
      no_a2ui_count += 1
      print(f"  ⚠ SIN A2UI ({elapsed}ms) — Claude no generó UI")
      if result["text"]:
        print(f"  Texto: {result['text'][:200]}...")
    else:
      error_count += 1
      print(f"  ✗ ERROR ({elapsed}ms) — {result['error']}")

  # Guardar resumen
  summary = {
    "model": MODEL,
    "total": len(TEST_CASES),
    "ok": ok_count,
    "invalid": invalid_count,
    "no_a2ui": no_a2ui_count,
    "error": error_count,
    "results": [
      {
        "id": r["id"],
        "description": r["description"],
        "status": r["status"],
        "validation_ok": r["validation_ok"],
        "elapsed_ms": r["elapsed_ms"],
        "error": r["error"],
        "text": r["text"][:300] if r["text"] else "",
        "has_json": r["a2ui_json"] is not None,
      }
      for r in all_results
    ],
  }
  summary_path = RESULTS_DIR / "summary.json"
  with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

  print("\n" + "=" * 60)
  print(f"Resumen: {ok_count} OK, {invalid_count} inválidos, "
        f"{no_a2ui_count} sin A2UI, {error_count} errores")
  print(f"Resumen guardado: {summary_path}")
  print(f"\nPara ver los resultados visuales, abre:")
  print(f"  file://{RESULTS_DIR.parent / 'viewer.html'}")


if __name__ == "__main__":
  main()