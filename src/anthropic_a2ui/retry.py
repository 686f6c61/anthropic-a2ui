"""Generacion de A2UI con Claude: multi-turno, reintentos, caching y async.

Este modulo es la capa de alto nivel del paquete. Ofrece cuatro funciones:

- ``generate_a2ui``: llamada unica con reintentos.
- ``generate_a2ui_async``: version async de ``generate_a2ui``.
- ``A2uiConversation``: conversacion multi-turno incremental.
- ``A2uiConversationAsync``: version async de ``A2uiConversation``.

Todas soportan prompt caching (``cache_control``) para reducir coste y
latencia, y reparacion automatica de payloads A2UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import anthropic

from .prompt_builder import ClaudeA2uiPromptBuilder
from .stream_parser import ClaudeStreamParser
from .tool import create_a2ui_tool, validate_tool_input


@dataclass
class RetryResult:
  """Resultado de una llamada con reintentos.

  Attributes:
    a2ui_json: El payload A2UI validado si tuvo exito, o ``None`` si fallo.
    text: Texto conversacional acumulado de todos los intentos.
    attempts: Numero de intentos realizados.
    success: Si se consiguio un A2UI valido.
    error: Mensaje de error del ultimo intento si fallo.
    all_payloads: Todos los payloads generados (validos e invalidos).
    repairs: Lista de reparaciones aplicadas (si ``log_repairs=True``).
  """

  a2ui_json: Optional[list[dict[str, Any]]] = None
  text: str = ""
  attempts: int = 0
  success: bool = False
  error: Optional[str] = None
  all_payloads: list[Any] = field(default_factory=list)
  repairs: list[str] = field(default_factory=list)


def _build_system_block(
    system_prompt: str,
    *,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
  """Construye el bloque system con cache_control si esta activado.

  Anthropic soporta prompt caching anadiendo ``cache_control`` al ultimo
  bloque del system prompt. Esto reduce coste y latencia en llamadas
  repetidas con el mismo system prompt (es el caso tipico de A2UI, donde
  el system prompt es grande y no cambia entre llamadas).

  Args:
    system_prompt: El system prompt completo.
    use_cache: Si activar prompt caching.

  Returns:
    Lista de bloques para el parametro ``system`` de la API de Anthropic.
    Con cache: ``[{"type": "text", "text": ..., "cache_control": {"type": "ephemeral"}}]``.
    Sin cache: ``[{"type": "text", "text": ...}]``.
  """
  block: dict[str, Any] = {"type": "text", "text": system_prompt}
  if use_cache:
    block["cache_control"] = {"type": "ephemeral"}
  return [block]


def _run_attempt(
    client: anthropic.Anthropic,
    model: str,
    system_blocks: list[dict[str, Any]],
    tool: dict[str, Any],
    max_tokens: int,
    messages: list[dict[str, Any]],
    catalog: Any,
    log_repairs: bool,
) -> tuple[Optional[list], str, Optional[str], list[str]]:
  """Ejecuta un intento de generacion.

  Returns:
    Tupla (a2ui_payload, text, error, repairs).
  """
  parser = ClaudeStreamParser(catalog=catalog, strict_tool_validation=True, repair=True)

  a2ui_payload: Optional[list] = None
  text_parts: list[str] = []
  repairs: list[str] = []

  try:
    with client.messages.stream(
        model=model,
        system=system_blocks,
        tools=[tool],
        max_tokens=max_tokens,
        messages=messages,
    ) as stream:
      for event in stream:
        for part in parser.process_event(event):
          if part.text:
            text_parts.append(part.text)
          if part.a2ui_json is not None:
            a2ui_payload = part.a2ui_json

      text = "".join(text_parts)

      if a2ui_payload is not None:
        try:
          validate_tool_input(catalog, a2ui_payload, repair=True)
          # Detectar reparaciones comparando antes/después
          if log_repairs:
            repairs = _detect_repairs(a2ui_payload, catalog)
          return a2ui_payload, text, None, repairs
        except Exception as ve:
          return a2ui_payload, text, f"{type(ve).__name__}: {str(ve)[:400]}", []
      else:
        return (
            None,
            text,
            (
                "Claude no genero A2UI. Responde solo con la tool "
                "send_a2ui_json_to_client cuando el usuario pida una interfaz."
            ),
            [],
        )

  except Exception as exc:
    return None, "", f"{type(exc).__name__}: {str(exc)[:400]}", []


def _detect_repairs(payload: list[dict[str, Any]], catalog: Any) -> list[str]:
  """Detecta que reparaciones se aplicaron comparando el payload original.

  Como el parser ya aplica reparaciones, comparamos el payload resultante
  con lo que el validador estricto rechazaria. Esto es aproximado: solo
  detecta iconos sustituidos por 'info' y funciones eliminadas.
  """
  repairs = []
  for msg in payload:
    if "updateComponents" not in msg:
      continue
    for comp in msg["updateComponents"].get("components", []):
      if comp.get("component") == "Icon" and comp.get("name") == "info":
        repairs.append(f"Icon '{comp['id']}' sustituido por 'info'")
      if isinstance(comp.get("text"), str) and comp.get("text") == "":
        repairs.append(f"Text '{comp['id']}' vacio (posible funcion eliminada)")
  return repairs


def generate_a2ui(
    client: anthropic.Anthropic,
    prompt: str,
    *,
    builder: Optional[ClaudeA2uiPromptBuilder] = None,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 8192,
    max_retries: int = 2,
    role_description: str = (
        "Eres un asistente util que crea interfaces de usuario. "
        "Cuando el usuario pida una interfaz, usa la tool "
        "send_a2ui_json_to_client."
    ),
    use_cache: bool = True,
    log_repairs: bool = False,
) -> RetryResult:
  """Llama a Claude y devuelve A2UI valido, reintentando si falla.

  Args:
    client: Cliente de Anthropic (``anthropic.Anthropic()``).
    prompt: Prompt natural del usuario.
    builder: Builder de prompt. Si es ``None``, se crea uno con v0.9.
    model: Modelo de Claude a usar.
    max_tokens: Maximo de tokens por intento.
    max_retries: Numero maximo de reintentos si la validacion falla.
    role_description: Descripcion del rol para el system prompt.
    use_cache: Si activar prompt caching para reducir coste. Por defecto
      ``True``. El system prompt de A2UI es grande y no cambia entre
      llamadas, asi que caching reduce coste ~80%.
    log_repairs: Si registrar que reparaciones se aplicaron. Por defecto
      ``False``. Si es ``True``, ``RetryResult.repairs`` contiene una lista
      de descripciones legibles.

  Returns:
    ``RetryResult`` con el A2UI validado, texto y metadatos.

  Example:
    ```python
    import anthropic
    from anthropic_a2ui import generate_a2ui

    client = anthropic.Anthropic()
    result = generate_a2ui(
        client,
        "hazme un formulario de registro",
        model="claude-haiku-4-5-20251001",
        log_repairs=True,
    )

    if result.success:
        render(result.a2ui_json)
        for r in result.repairs:
            print(f"Reparado: {r}")
    else:
        print(f"Fallo: {result.error}")
    ```
  """
  if builder is None:
    builder = ClaudeA2uiPromptBuilder(version="0.9")

  catalog = builder.get_catalog()
  tool = create_a2ui_tool(catalog)
  system_prompt = builder.build(
      role_description=role_description,
      include_schema=True,
      include_examples=True,
  )
  system_blocks = _build_system_block(system_prompt, use_cache=use_cache)

  messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
  result = RetryResult()
  all_text_parts: list[str] = []

  for attempt in range(1, max_retries + 2):
    result.attempts = attempt
    a2ui_payload, text, error, repairs = _run_attempt(
        client, model, system_blocks, tool, max_tokens, messages, catalog, log_repairs
    )
    all_text_parts.append(text)
    result.repairs.extend(repairs)

    if a2ui_payload is not None:
      result.all_payloads.append(a2ui_payload)

    if error is None:
      result.a2ui_json = a2ui_payload
      result.text = "\n".join(all_text_parts)
      result.success = True
      return result

    # Preparar feedback para reintentar
    if attempt > max_retries:
      result.error = error
      result.text = "\n".join(all_text_parts)
      return result

    if a2ui_payload is not None:
      messages.append({
          "role": "assistant",
          "content": [{
              "type": "tool_use",
              "id": f"toolu_retry_{attempt}",
              "name": "send_a2ui_json_to_client",
              "input": {"a2ui_json": a2ui_payload},
          }],
      })
      messages.append({
          "role": "user",
          "content": [{
              "type": "tool_result",
              "tool_use_id": f"toolu_retry_{attempt}",
              "content": (
                  f"El JSON A2UI no es valido: {error}\n\nCorrige y envia de nuevo."
              ),
              "is_error": True,
          }],
      })
    else:
      messages.append(
          {"role": "assistant", "content": [{"type": "text", "text": text}]}
      )
      messages.append({
          "role": "user",
          "content": f"{error} Usa la tool send_a2ui_json_to_client.",
      })

  result.error = error
  result.text = "\n".join(all_text_parts)
  return result


async def generate_a2ui_async(
    client: anthropic.AsyncAnthropic,
    prompt: str,
    *,
    builder: Optional[ClaudeA2uiPromptBuilder] = None,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 8192,
    max_retries: int = 2,
    role_description: str = (
        "Eres un asistente util que crea interfaces de usuario. "
        "Cuando el usuario pida una interfaz, usa la tool "
        "send_a2ui_json_to_client."
    ),
    use_cache: bool = True,
    log_repairs: bool = False,
) -> RetryResult:
  """Version async de ``generate_a2ui``.

  Usa ``anthropic.AsyncAnthropic`` y ``messages.stream`` async. El resto
  de parametros y el retorno son identicos a ``generate_a2ui``.

  Example:
    ```python
    import anthropic
    from anthropic_a2ui import generate_a2ui_async

    client = anthropic.AsyncAnthropic()
    result = await generate_a2ui_async(
        client,
        "hazme un formulario",
        model="claude-haiku-4-5-20251001",
    )
    ```
  """
  if builder is None:
    builder = ClaudeA2uiPromptBuilder(version="0.9")

  catalog = builder.get_catalog()
  tool = create_a2ui_tool(catalog)
  system_prompt = builder.build(
      role_description=role_description,
      include_schema=True,
      include_examples=True,
  )
  system_blocks = _build_system_block(system_prompt, use_cache=use_cache)

  messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
  result = RetryResult()
  all_text_parts: list[str] = []

  for attempt in range(1, max_retries + 2):
    result.attempts = attempt
    a2ui_payload, text, error, repairs = await _run_attempt_async(
        client, model, system_blocks, tool, max_tokens, messages, catalog, log_repairs
    )
    all_text_parts.append(text)
    result.repairs.extend(repairs)

    if a2ui_payload is not None:
      result.all_payloads.append(a2ui_payload)

    if error is None:
      result.a2ui_json = a2ui_payload
      result.text = "\n".join(all_text_parts)
      result.success = True
      return result

    if attempt > max_retries:
      result.error = error
      result.text = "\n".join(all_text_parts)
      return result

    if a2ui_payload is not None:
      messages.append({
          "role": "assistant",
          "content": [{
              "type": "tool_use",
              "id": f"toolu_retry_{attempt}",
              "name": "send_a2ui_json_to_client",
              "input": {"a2ui_json": a2ui_payload},
          }],
      })
      messages.append({
          "role": "user",
          "content": [{
              "type": "tool_result",
              "tool_use_id": f"toolu_retry_{attempt}",
              "content": (
                  f"El JSON A2UI no es valido: {error}\n\nCorrige y envia de nuevo."
              ),
              "is_error": True,
          }],
      })
    else:
      messages.append(
          {"role": "assistant", "content": [{"type": "text", "text": text}]}
      )
      messages.append({
          "role": "user",
          "content": f"{error} Usa la tool send_a2ui_json_to_client.",
      })

  result.error = error
  result.text = "\n".join(all_text_parts)
  return result


async def _run_attempt_async(
    client: anthropic.AsyncAnthropic,
    model: str,
    system_blocks: list[dict[str, Any]],
    tool: dict[str, Any],
    max_tokens: int,
    messages: list[dict[str, Any]],
    catalog: Any,
    log_repairs: bool,
) -> tuple[Optional[list], str, Optional[str], list[str]]:
  """Version async de ``_run_attempt``."""
  parser = ClaudeStreamParser(catalog=catalog, strict_tool_validation=True, repair=True)

  a2ui_payload: Optional[list] = None
  text_parts: list[str] = []
  repairs: list[str] = []

  try:
    async with client.messages.stream(
        model=model,
        system=system_blocks,
        tools=[tool],
        max_tokens=max_tokens,
        messages=messages,
    ) as stream:
      async for event in stream:
        for part in parser.process_event(event):
          if part.text:
            text_parts.append(part.text)
          if part.a2ui_json is not None:
            a2ui_payload = part.a2ui_json

      text = "".join(text_parts)

      if a2ui_payload is not None:
        try:
          validate_tool_input(catalog, a2ui_payload, repair=True)
          if log_repairs:
            repairs = _detect_repairs(a2ui_payload, catalog)
          return a2ui_payload, text, None, repairs
        except Exception as ve:
          return a2ui_payload, text, f"{type(ve).__name__}: {str(ve)[:400]}", []
      else:
        return (
            None,
            text,
            (
                "Claude no genero A2UI. Responde solo con la tool "
                "send_a2ui_json_to_client cuando el usuario pida una interfaz."
            ),
            [],
        )

  except Exception as exc:
    return None, "", f"{type(exc).__name__}: {str(exc)[:400]}", []


# --- Conversacion multi-turno --------------------------------------


@dataclass
class ConversationTurn:
  """Un turno de conversacion.

  Attributes:
    user_prompt: Lo que dijo el usuario.
    a2ui_json: El A2UI generado (o None si no genero).
    text: Texto conversacional de Claude.
    success: Si el A2UI fue valido.
    error: Error si fallo.
  """

  user_prompt: str
  a2ui_json: Optional[list[dict[str, Any]]] = None
  text: str = ""
  success: bool = False
  error: Optional[str] = None


class A2uiConversation:
  """Conversacion multi-turno que genera A2UI incrementalmente.

  Mantiene el historial de mensajes entre el usuario y Claude, de modo que
  el usuario puede iterar sobre la UI: "hazme un formulario" -> "anade un
  campo de telefono" -> "cambia el boton a azul". Claude recibe el contexto
  completo y genera un A2UI nuevo que refleja los cambios.

  Attributes:
    turns: Lista de turnos de la conversacion.
    last_a2ui_json: El ultimo A2UI valido generado.

  Example:
    ```python
    import anthropic
    from anthropic_a2ui import A2uiConversation

    client = anthropic.Anthropic()
    conv = A2uiConversation(client, model="claude-haiku-4-5-20251001")

    # Turno 1
    r1 = conv.send("hazme un formulario de contacto")
    # r1.a2ui_json tiene el formulario

    # Turno 2: iterar
    r2 = conv.send("anade un campo de telefono")
    # r2.a2ui_json tiene el formulario + telefono

    # Turno 3: iterar
    r3 = conv.send("cambia el color del boton a rojo")
    # r3.a2ui_json tiene el formulario + telefono + boton rojo
    ```
  """

  def __init__(
      self,
      client: anthropic.Anthropic,
      *,
      builder: Optional[ClaudeA2uiPromptBuilder] = None,
      model: str = "claude-sonnet-4-6",
      max_tokens: int = 8192,
      max_retries: int = 2,
      role_description: str = (
          "Eres un asistente util que crea interfaces de usuario. "
          "Cuando el usuario pida una interfaz o un cambio en una interfaz, "
          "usa la tool send_a2ui_json_to_client. Si el usuario pide "
          "modificar una interfaz existente, genera el A2UI completo con "
          "los cambios aplicados."
      ),
      use_cache: bool = True,
      log_repairs: bool = False,
  ) -> None:
    self.client = client
    self.model = model
    self.max_tokens = max_tokens
    self.max_retries = max_retries
    self.use_cache = use_cache
    self.log_repairs = log_repairs

    if builder is None:
      builder = ClaudeA2uiPromptBuilder(version="0.9")
    self.builder = builder
    self.catalog = builder.get_catalog()
    self.tool = create_a2ui_tool(self.catalog)
    system_prompt = builder.build(
        role_description=role_description,
        include_schema=True,
        include_examples=True,
    )
    self.system_blocks = _build_system_block(system_prompt, use_cache=use_cache)

    self.messages: list[dict[str, Any]] = []
    self.turns: list[ConversationTurn] = []
    self.last_a2ui_json: Optional[list[dict[str, Any]]] = None

  def send(self, prompt: str) -> ConversationTurn:
    """Envia un mensaje al usuario y devuelve el turno.

    Args:
      prompt: Mensaje natural del usuario.

    Returns:
      ``ConversationTurn`` con el A2UI generado y metadatos.
    """
    self.messages.append({"role": "user", "content": prompt})
    turn = ConversationTurn(user_prompt=prompt)

    for attempt in range(1, self.max_retries + 2):
      a2ui_payload, text, error, repairs = _run_attempt(
          self.client,
          self.model,
          self.system_blocks,
          self.tool,
          self.max_tokens,
          self.messages,
          self.catalog,
          self.log_repairs,
      )

      if error is None and a2ui_payload is not None:
        turn.a2ui_json = a2ui_payload
        turn.text = text
        turn.success = True
        self.last_a2ui_json = a2ui_payload
        # Anadir respuesta de Claude al historial
        tool_use_id = f"toolu_turn_{len(self.turns)}_{attempt}"
        self.messages.append(_tool_use_message(tool_use_id, a2ui_payload))
        self.messages.append(_tool_result_message(tool_use_id))
        self.turns.append(turn)
        return turn

      if a2ui_payload is not None:
        self.messages.append({
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": f"toolu_turn_{len(self.turns)}_{attempt}",
                "name": "send_a2ui_json_to_client",
                "input": {"a2ui_json": a2ui_payload},
            }],
        })
        self.messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": f"toolu_turn_{len(self.turns)}_{attempt}",
                "content": (
                    f"El JSON A2UI no es valido: {error}\n\nCorrige y envia de nuevo."
                ),
                "is_error": True,
            }],
        })
      else:
        self.messages.append({
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        })
        self.messages.append({
            "role": "user",
            "content": f"{error} Usa la tool send_a2ui_json_to_client.",
        })

      if attempt > self.max_retries:
        turn.error = error
        turn.text = text
        self.turns.append(turn)
        return turn

    turn.error = error
    turn.text = text
    self.turns.append(turn)
    return turn

  def reset(self) -> None:
    """Reinicia la conversacion manteniendo el system prompt."""
    self.messages = []
    self.turns = []
    self.last_a2ui_json = None


class A2uiConversationAsync:
  """Version async de ``A2uiConversation``.

  Usa ``anthropic.AsyncAnthropic``. El metodo ``send`` es una corutina.

  Example:
    ```python
    import anthropic
    from anthropic_a2ui import A2uiConversationAsync

    client = anthropic.AsyncAnthropic()
    conv = A2uiConversationAsync(client)

    r1 = await conv.send("hazme un formulario")
    r2 = await conv.send("anade un campo de email")
    ```
  """

  def __init__(
      self,
      client: anthropic.AsyncAnthropic,
      *,
      builder: Optional[ClaudeA2uiPromptBuilder] = None,
      model: str = "claude-sonnet-4-6",
      max_tokens: int = 8192,
      max_retries: int = 2,
      role_description: str = (
          "Eres un asistente util que crea interfaces de usuario. "
          "Cuando el usuario pida una interfaz o un cambio en una interfaz, "
          "usa la tool send_a2ui_json_to_client."
      ),
      use_cache: bool = True,
      log_repairs: bool = False,
  ) -> None:
    self.client = client
    self.model = model
    self.max_tokens = max_tokens
    self.max_retries = max_retries
    self.use_cache = use_cache
    self.log_repairs = log_repairs

    if builder is None:
      builder = ClaudeA2uiPromptBuilder(version="0.9")
    self.builder = builder
    self.catalog = builder.get_catalog()
    self.tool = create_a2ui_tool(self.catalog)
    system_prompt = builder.build(
        role_description=role_description,
        include_schema=True,
        include_examples=True,
    )
    self.system_blocks = _build_system_block(system_prompt, use_cache=use_cache)

    self.messages: list[dict[str, Any]] = []
    self.turns: list[ConversationTurn] = []
    self.last_a2ui_json: Optional[list[dict[str, Any]]] = None

  async def send(self, prompt: str) -> ConversationTurn:
    """Envia un mensaje y devuelve el turno (async)."""
    self.messages.append({"role": "user", "content": prompt})
    turn = ConversationTurn(user_prompt=prompt)

    for attempt in range(1, self.max_retries + 2):
      a2ui_payload, text, error, repairs = await _run_attempt_async(
          self.client,
          self.model,
          self.system_blocks,
          self.tool,
          self.max_tokens,
          self.messages,
          self.catalog,
          self.log_repairs,
      )

      if error is None and a2ui_payload is not None:
        turn.a2ui_json = a2ui_payload
        turn.text = text
        turn.success = True
        self.last_a2ui_json = a2ui_payload
        tool_use_id = f"toolu_turn_{len(self.turns)}_{attempt}"
        self.messages.append(_tool_use_message(tool_use_id, a2ui_payload))
        self.messages.append(_tool_result_message(tool_use_id))
        self.turns.append(turn)
        return turn

      if a2ui_payload is not None:
        self.messages.append({
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": f"toolu_turn_{len(self.turns)}_{attempt}",
                "name": "send_a2ui_json_to_client",
                "input": {"a2ui_json": a2ui_payload},
            }],
        })
        self.messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": f"toolu_turn_{len(self.turns)}_{attempt}",
                "content": (
                    f"El JSON A2UI no es valido: {error}\n\nCorrige y envia de nuevo."
                ),
                "is_error": True,
            }],
        })
      else:
        self.messages.append({
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        })
        self.messages.append({
            "role": "user",
            "content": f"{error} Usa la tool send_a2ui_json_to_client.",
        })

      if attempt > self.max_retries:
        turn.error = error
        turn.text = text
        self.turns.append(turn)
        return turn

    turn.error = error
    turn.text = text
    self.turns.append(turn)
    return turn

  def reset(self) -> None:
    """Reinicia la conversacion."""
    self.messages = []
    self.turns = []
    self.last_a2ui_json = None


# --- Tercer modo: structured output --------------------------------


def create_a2ui_response_format(
    catalog: Any,
    *,
    allowed_components: Optional[list[str]] = None,
) -> dict[str, Any]:
  """Crea el formato JSON para ``output_config.format`` de Anthropic.

  Anthropic soporta structured outputs con ``output_config.format`` y
  ``type: "json_schema"`` para garantizar que la respuesta sea JSON
  parseable sin necesidad de tools ni tags. Este modo es util cuando se
  quiere UI pura sin texto conversacional.

  El esquema se envuelve igual que en ``create_a2ui_tool`` (en
  ``{"a2ui_json": [...]}``) para evitar ``oneOf`` en la raiz.

  Args:
    catalog: ``A2uiCatalog``.
    allowed_components: Subconjunto de componentes para podar.

  Returns:
    Dict listo para pasarlo como ``output_config={"format": ...}``:
    ``{"type": "json_schema", "schema": {...}}``.

  Example:
    ```python
    output_format = create_a2ui_response_format(builder.get_catalog())
    response = client.messages.create(
        model="claude-sonnet-4-6",
        system=system_prompt,
        output_config={"format": output_format},
        messages=[{"role": "user", "content": "hazme un formulario"}],
    )
    # response.content[0].text es un JSON string con {"a2ui_json": [...]}
    ```
  """
  from .tool import create_a2ui_tool

  # Reutilizar la envoltura de create_a2ui_tool
  tool = create_a2ui_tool(catalog, allowed_components=allowed_components)
  return {
      "type": "json_schema",
      "schema": tool["input_schema"],
  }


def create_a2ui_output_config(
    catalog: Any,
    *,
    allowed_components: Optional[list[str]] = None,
) -> dict[str, Any]:
  """Crea ``output_config`` completo para structured outputs de Anthropic."""
  return {
      "format": create_a2ui_response_format(
          catalog, allowed_components=allowed_components
      )
  }


def parse_json_response(message: Any, catalog: Any) -> list[dict[str, Any]]:
  """Extrae y valida el A2UI de una respuesta con structured output.

  Cuando se usa ``output_config.format``, la respuesta de Claude viene como
  un ``TextBlock`` cuyo ``text`` es un JSON string con
  ``{"a2ui_json": [...]}``. Esta funcion lo extrae, desenvuelve, repara y
  valida.

  Args:
    message: El mensaje de respuesta de ``client.messages.create``.
    catalog: ``A2uiCatalog`` para validacion.

  Returns:
    Lista de mensajes A2UI validados y reparados.

  Raises:
    ValueError: Si el JSON no es valido o no contiene ``a2ui_json``.
  """
  import json

  # Extraer el texto del primer content block
  text = ""
  if hasattr(message, "content"):
    for block in message.content:
      if hasattr(block, "text"):
        text = block.text
        break
  elif isinstance(message, str):
    text = message

  if not text:
    raise ValueError("La respuesta no contiene texto")

  try:
    parsed = json.loads(text)
  except json.JSONDecodeError as exc:
    raise ValueError(f"La respuesta no es JSON valido: {exc}") from exc

  # Desenvolver a2ui_json
  if isinstance(parsed, dict) and "a2ui_json" in parsed:
    payload = parsed["a2ui_json"]
  elif isinstance(parsed, list):
    payload = parsed
  else:
    raise ValueError("La respuesta no contiene a2ui_json")

  payload = _repair_payload(payload)
  validate_tool_input(catalog, payload, repair=True)
  return payload


def _tool_use_message(tool_use_id: str, a2ui_payload: list[Any]) -> dict[str, Any]:
  """Construye el mensaje assistant que representa la tool A2UI usada."""
  return {
      "role": "assistant",
      "content": [{
          "type": "tool_use",
          "id": tool_use_id,
          "name": "send_a2ui_json_to_client",
          "input": {"a2ui_json": a2ui_payload},
      }],
  }


def _tool_result_message(tool_use_id: str) -> dict[str, Any]:
  """Construye el tool_result de exito para cerrar el bucle de Anthropic."""
  return {
      "role": "user",
      "content": [{
          "type": "tool_result",
          "tool_use_id": tool_use_id,
          "content": "A2UI recibido y renderizado por el cliente.",
      }],
  }


def _repair_payload(payload: Any) -> list[dict[str, Any]]:
  """Aplica las mismas reparaciones que el parser antes de devolver JSON."""
  from .repair import (
      repair_childlists,
      repair_functions,
      repair_icons,
      repair_orphans,
  )

  if isinstance(payload, list):
    repaired = payload
  else:
    repaired = [payload]
  repaired = repair_childlists(repaired)
  repaired = repair_orphans(repaired)
  repaired = repair_icons(repaired)
  repaired = repair_functions(repaired)
  return repaired
