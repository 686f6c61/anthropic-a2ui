"""Prueba de fuego con prompts 100% naturales.

El usuario habla normal en una conversacion. Nunca menciona A2UI, ni
funciones del catalogo, ni propiedades, ni esquemas. Solo pide cosas como
cualquier humano o bot haria. Claude debe responder con A2UI
automaticamente porque el system prompt (que nuestro paquete construye) le
dice como.

Se prueban 3 modelos: Haiku 4.5, Opus 4.7, Opus 4.8.
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

RESULTS_DIR = Path(__file__).parent / "results_natural"
RESULTS_DIR.mkdir(exist_ok=True)
MAX_TOKENS = 16384

MODELS = [
  "claude-haiku-4-5-20251001",
  "claude-opus-4-7",
  "claude-opus-4-8",
]

# Prompts 100% naturales. Como hablaria un humano o un bot en una
# conversacion real. Sin mencionar A2UI, componentes, funciones, esquemas
# ni nada tecnico.
TEST_CASES = [
  {
    "id": "01_formulario_paciente",
    "prompt": "Hazme un formulario para registrar un paciente en una clinica. Necesita nombre completo, fecha de nacimiento, email, telefono, grupo sanguineo y un boton para enviar.",
    "description": "Registro de paciente (formulario medico)",
  },
  {
    "id": "02_carrito_compra",
    "prompt": "Estoy montando una tienda online. Muéstrame un carrito de la compra con tres productos: un portatil a 1299 euros, un raton a 29 euros y unos auriculares a 89 euros. Que se vea el total y un boton de finalizar compra.",
    "description": "Carrito de compra con totales",
  },
  {
    "id": "03_panel_clima",
    "prompt": "Dame el panel de control de una app del clima. Tiene que mostrar la temperatura actual en grande, la ciudad, un icono de sol o nube, y debajo una fila con humedad, viento y probabilidad de lluvia.",
    "description": "Panel de clima (datos visuales)",
  },
  {
    "id": "04_encuesta_satisfaccion",
    "prompt": "Quiero enviar una encuesta de satisfaccion a mis clientes. 5 estrellas para puntuar, un campo para dejar un comentario, elegir si quieren respuesta (si/no) y un boton de enviar.",
    "description": "Encuesta de satisfaccion (inputs mixtos)",
  },
  {
    "id": "05_calendario_citas",
    "prompt": "Necesito una pantalla para agendar una reunion. Que se pueda picks la fecha y hora, elegir la duracion (30 min, 1h, 2h) y poner un titulo. Un boton de crear reunion.",
    "description": "Agendar reunion (fecha/hora + seleccion)",
  },
  {
    "id": "06_perfil_usuario",
    "prompt": "Muéstrame una tarjeta de perfil de un usuario llamado Ana Garcia. Foto de avatar, su nombre, su cargo (Desarrolladora Senior), una bio corta, y dos botones: seguir y enviar mensaje.",
    "description": "Perfil de usuario (tarjeta con avatar)",
  },
  {
    "id": "07_configuracion_cuenta",
    "prompt": "Creame la pagina de configuracion de mi cuenta. Que tenga: cambiar el idioma (español, ingles, frances), notificaciones por email on/off, modo oscuro on/off, y un boton de guardar.",
    "description": "Configuracion de cuenta (switches + select)",
  },
  {
    "id": "08_lista_tareas",
    "prompt": "Hazme una lista de tareas para un proyecto. Tres tareas: disennar la landing, programar el backend y configurar el deploy. Cada una con un checkbox para marcarla como hecha y la prioridad (alta, media, baja). Un boton de anadir tarea nueva.",
    "description": "Lista de tareas (checkboxes + prioridades)",
  },
  {
    "id": "09_galeria_producto",
    "prompt": "Quiero enseñar un producto en mi web. Una pestana con la descripcion y precio, otra pestana con galeria de 3 fotos, y una tercera con un video del producto en accion.",
    "description": "Ficha de producto con pestanas (tabs)",
  },
  {
    "id": "10_confirmacion_borrar",
    "prompt": "Cuando el usuario pulse borrar cuenta en mi app, quiero que salga un aviso diciendo que se va a borrar todo y no se puede deshacer, con un boton de cancelar y otro de borrar definitivamente.",
    "description": "Modal de confirmacion (ventana emergente)",
  },
]


def extract_usage(payload):
  """Extrae que uso Claude del payload para estadisticas."""
  components = set()
  functions = set()
  messages = set()
  props = set()
  for msg in payload:
    for k in msg:
      if k != "version":
        messages.add(k)
    if "createSurface" in msg:
      cs = msg["createSurface"]
      for k in cs:
        if k not in ("surfaceId", "catalogId"):
          props.add(k)
      if "theme" in cs:
        for tk in cs["theme"]:
          props.add(f"theme.{tk}")
    if "updateComponents" in msg:
      for c in msg["updateComponents"].get("components", []):
        components.add(c.get("component", "?"))
        for k in c:
          if k not in ("id", "component"):
            props.add(k)
        for check in c.get("checks", []):
          cond = check.get("condition", {})
          if isinstance(cond, dict) and "call" in cond:
            functions.add(cond["call"])
        text = c.get("text", {})
        if isinstance(text, dict) and "call" in text:
          functions.add(text["call"])
        action = c.get("action", {})
        if "functionCall" in action:
          functions.add(action["functionCall"].get("call", "?"))
    if "updateDataModel" in msg:
      for k in msg["updateDataModel"]:
        if k != "surfaceId":
          props.add(f"dataModel.{k}")
  return {
    "components": sorted(components),
    "functions": sorted(functions),
    "messages": sorted(messages),
    "properties": sorted(props),
  }


def run_test(client, builder, tool, parser, model, case):
  result = {
    "id": case["id"],
    "model": model,
    "description": case["description"],
    "prompt": case["prompt"],
    "status": "pending",
    "text": "",
    "a2ui_json": None,
    "error": None,
    "validation_ok": False,
    "elapsed_ms": 0,
    "usage": None,
  }

  start = time.monotonic()
  catalog = builder.get_catalog()

  try:
    with client.messages.stream(
      model=model,
      system=builder.build(
        role_description=(
          "Eres un asistente util que ayuda a los usuarios creando "
          "interfaces de usuario interactivas. Cuando el usuario te pida "
          "una interfaz, formulario, panel, tarjeta, lista o cualquier "
          "elemento visual, usa la tool send_a2ui_json_to_client para "
          "entregarle una UI que pueda renderizar directamente. Si el "
          "usuario pide algo que no es una interfaz, responde normalmente "
          "con texto."
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
        result["usage"] = extract_usage(payload)
        try:
          validate_tool_input(catalog, payload, repair=True)
          result["validation_ok"] = True
          result["status"] = "ok"
        except Exception as ve:
          result["validation_ok"] = False
          result["status"] = "invalid"
          result["error"] = f"{type(ve).__name__}: {str(ve)[:400]}"
      else:
        result["status"] = "no_a2ui"
        result["error"] = "Claude no genero UI"
        if result["text"]:
          result["error"] += f" — respondio con texto: {result['text'][:150]}"

  except Exception as exc:
    result["status"] = "error"
    result["error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
    result["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    traceback.print_exc()

  return result


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
  print(f"Prueba natural: {len(TEST_CASES)} casos x {len(MODELS)} modelos = {total} ejecuciones")
  print(f"Prompts 100% naturales, sin mencionar A2UI")
  print("=" * 70)

  all_results = []
  stats = {"ok": 0, "invalid": 0, "no_a2ui": 0, "error": 0}

  # Cobertura acumulada
  all_components = set()
  all_functions = set()
  all_messages = set()
  all_props = set()

  i = 0
  for model in MODELS:
    ms = model.replace("claude-", "").replace("-20251001", "").replace("-20250929", "")
    print(f"\n{'='*70}")
    print(f"Modelo: {ms}")
    print(f"{'='*70}")

    for case in TEST_CASES:
      i += 1
      print(f"\n[{i}/{total}] {case['id']} [{ms}]")
      print(f"  Prompt: {case['prompt'][:80]}...")

      result = run_test(client, builder, tool, parser, model, case)
      all_results.append(result)

      if result["a2ui_json"] is not None:
        json_path = RESULTS_DIR / f"{ms}__{case['id']}.json"
        with open(json_path, "w", encoding="utf-8") as f:
          json.dump(result["a2ui_json"], f, indent=2, ensure_ascii=False)

      if result["usage"]:
        all_components.update(result["usage"]["components"])
        all_functions.update(result["usage"]["functions"])
        all_messages.update(result["usage"]["messages"])
        all_props.update(result["usage"]["properties"])

      status = result["status"]
      elapsed = result["elapsed_ms"]
      stats[status] = stats.get(status, 0) + 1

      if status == "ok":
        u = result["usage"]
        print(f"  OK ({elapsed}ms) — {len(u['components'])} comps, "
              f"{len(u['functions'])} funcs, {len(u['messages'])} msgs")
      elif status == "invalid":
        print(f"  INVALID ({elapsed}ms) — {result['error'][:100]}")
      elif status == "no_a2ui":
        print(f"  SIN A2UI ({elapsed}ms) — {result['error'][:100]}")
      else:
        print(f"  ERROR ({elapsed}ms) — {result['error'][:100]}")

  # Resumen
  print(f"\n{'='*70}")
  print(f"COBERTURA TOTAL (prompts naturales)")
  print(f"{'='*70}")
  print(f"Componentes usados: {len(all_components)} — {sorted(all_components)}")
  print(f"Funciones usadas: {len(all_functions)} — {sorted(all_functions)}")
  print(f"Tipos de mensaje: {len(all_messages)} — {sorted(all_messages)}")
  print(f"Propiedades: {len(all_props)}")

  print(f"\nPor modelo:")
  for model in MODELS:
    ms = model.replace("claude-", "").replace("-20251001", "").replace("-20250929", "")
    mr = [r for r in all_results if r["model"] == model]
    ok = sum(1 for r in mr if r["status"] == "ok")
    print(f"  {ms:15s} {ok}/{len(mr)} OK")

  # Guardar summary
  summary = {
    "models": MODELS,
    "total": total,
    "stats": stats,
    "coverage": {
      "components": sorted(all_components),
      "functions": sorted(all_functions),
      "messages": sorted(all_messages),
      "properties": sorted(all_props),
    },
    "results": [
      {
        "id": r["id"],
        "model": r["model"],
        "description": r["description"],
        "prompt": r["prompt"],
        "status": r["status"],
        "validation_ok": r["validation_ok"],
        "elapsed_ms": r["elapsed_ms"],
        "error": r["error"],
        "text": r["text"][:300] if r["text"] else "",
        "has_json": r["a2ui_json"] is not None,
        "usage": r["usage"],
      }
      for r in all_results
    ],
  }
  summary_path = RESULTS_DIR / "summary.json"
  with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

  print(f"\nResumen: {stats['ok']} OK, {stats['invalid']} invalidos, "
        f"{stats['no_a2ui']} sin A2UI, {stats['error']} errores")
  print(f"Guardado: {summary_path}")


if __name__ == "__main__":
  main()