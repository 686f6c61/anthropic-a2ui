"""Ejemplo de uso de anthropic-a2ui con el SDK de Anthropic.

Requiere:
- ``anthropic`` instalado (``uv pip install anthropic``)
- ``ANTHROPIC_API_KEY`` en el entorno

Ejecutar:
    python examples/hello_a2ui.py

El ejemplo usa el modo tool use: Claude invoca ``send_a2ui_json_to_client``
con un payload A2UI que se valida y se imprime.
"""

from __future__ import annotations

import json
import os
import sys

import anthropic

from anthropic_a2ui import (
  ClaudeA2uiPromptBuilder,
  ClaudeStreamParser,
  create_a2ui_tool,
  to_a2ui_part,
)


def main() -> None:
  api_key = os.environ.get("ANTHROPIC_API_KEY")
  if not api_key:
    print("Define ANTHROPIC_API_KEY.", file=sys.stderr)
    sys.exit(1)

  # 1. Construir prompt, tool y parser
  builder = ClaudeA2uiPromptBuilder(version="0.9")
  system_prompt = builder.build(
    role_description=(
      "Eres un asistente que construye interfaces de usuario con A2UI. "
      "Cuando el usuario pida una UI, invoca la tool send_a2ui_json_to_client."
    ),
    include_schema=True,
    include_examples=True,
  )
  catalog = builder.get_catalog()
  tool = create_a2ui_tool(catalog)
  parser = ClaudeStreamParser(catalog=catalog, strict_tool_validation=True)

  # 2. Llamar a Claude con stream
  client = anthropic.Anthropic(api_key=api_key)
  prompt = sys.argv[1] if len(sys.argv) > 1 else "Haz un formulario de contacto con nombre, email y mensaje."

  print(f"Prompt: {prompt}\n")
  with client.messages.stream(
    model="claude-sonnet-4-5",
    system=system_prompt,
    tools=[tool],
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}],
  ) as stream:
    for event in stream:
      for part in parser.process_event(event):
        if part.text:
          print(part.text, end="", flush=True)
        if part.a2ui_json is not None:
          print("\n--- A2UI JSON recibido ---")
          a2ui_part = to_a2ui_part(part.a2ui_json)
          print(a2ui_part.to_json_string(indent=2))
          print(f"--- MIME: {a2ui_part.mime} ---\n")


if __name__ == "__main__":
  main()