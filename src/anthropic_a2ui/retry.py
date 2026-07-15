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
from typing import Any, Optional, cast

import anthropic
from anthropic.types import MessageParam, TextBlockParam, ToolParam

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


@dataclass
class _AttemptResult:
  """Resultado interno de un intento, incluido su contexto de tool use."""

  a2ui_json: Optional[list[dict[str, Any]]] = None
  text: str = ""
  error: Optional[str] = None
  repairs: list[str] = field(default_factory=list)
  tool_use_id: str = ""
  tool_input: Any = None
  tool_used: bool = False
  retryable: bool = True


def _build_system_block(
    system_prompt: str,
    *,
    use_cache: bool = True,
) -> list[TextBlockParam]:
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
    Con cache se anade ``cache_control={"type": "ephemeral"}``.
    Sin cache: ``[{"type": "text", "text": ...}]``.
  """
  block = cast(TextBlockParam, {"type": "text", "text": system_prompt})
  if use_cache:
    block["cache_control"] = {"type": "ephemeral"}
  return [block]


def _run_attempt(
    client: anthropic.Anthropic,
    model: str,
    system_blocks: list[TextBlockParam],
    tool: ToolParam,
    max_tokens: int,
    messages: list[MessageParam],
    catalog: Any,
    log_repairs: bool,
) -> _AttemptResult:
  """Ejecuta un intento de generacion.

  Returns:
    ``_AttemptResult`` con payload, error y contexto de la tool.
  """
  parser = ClaudeStreamParser(catalog=catalog, strict_tool_validation=True, repair=True)

  a2ui_payload: Optional[list] = None
  text_parts: list[str] = []
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
          a2ui_payload = validate_tool_input(catalog, a2ui_payload, repair=True)
          return _AttemptResult(
              a2ui_json=a2ui_payload,
              text=text,
              repairs=list(parser.last_repairs) if log_repairs else [],
              tool_use_id=parser.last_tool_use_id,
              tool_input=parser.last_tool_input,
              tool_used=parser.last_tool_used,
          )
        except Exception as ve:
          return _AttemptResult(
              a2ui_json=a2ui_payload,
              text=text,
              error=_format_error(ve),
              tool_use_id=parser.last_tool_use_id,
              tool_input=parser.last_tool_input,
              tool_used=parser.last_tool_used,
          )
      else:
        return _AttemptResult(
            text=text,
            error=(
                "Claude no genero A2UI. Responde solo con la tool "
                "send_a2ui_json_to_client cuando el usuario pida una interfaz."
            ),
            tool_use_id=parser.last_tool_use_id,
            tool_input=parser.last_tool_input,
            tool_used=parser.last_tool_used,
        )

  except Exception as exc:
    payload = parser.last_a2ui_json
    return _AttemptResult(
        a2ui_json=payload if isinstance(payload, list) else None,
        text="".join(text_parts),
        error=_format_error(exc),
        repairs=list(parser.last_repairs) if log_repairs else [],
        tool_use_id=parser.last_tool_use_id,
        tool_input=parser.last_tool_input,
        tool_used=parser.last_tool_used,
        # El SDK de Anthropic ya reintenta fallos de transporte. Solo damos
        # feedback al modelo cuando realmente intento usar la tool A2UI.
        retryable=parser.last_tool_used,
    )


def _format_error(exc: Exception) -> str:
  """Formatea errores sin incluir respuestas completas potencialmente sensibles."""
  return f"{type(exc).__name__}: {str(exc)[:400]}"


def generate_a2ui(
    client: anthropic.Anthropic,
    prompt: str,
    *,
    builder: Optional[ClaudeA2uiPromptBuilder] = None,
    allowed_components: Optional[list[str]] = None,
    allowed_messages: Optional[list[str]] = None,
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
  _validate_generation_options(max_tokens=max_tokens, max_retries=max_retries)
  if builder is None:
    builder = ClaudeA2uiPromptBuilder(version="0.9")

  catalog = builder.get_catalog(
      allowed_components=allowed_components,
      allowed_messages=allowed_messages,
  )
  tool = cast(ToolParam, create_a2ui_tool(catalog))
  system_prompt = builder.build(
      role_description=role_description,
      allowed_components=allowed_components,
      allowed_messages=allowed_messages,
      include_schema=True,
      include_examples=True,
  )
  system_blocks = _build_system_block(system_prompt, use_cache=use_cache)

  messages: list[MessageParam] = [{"role": "user", "content": prompt}]
  result = RetryResult()
  all_text_parts: list[str] = []

  for attempt in range(1, max_retries + 2):
    result.attempts = attempt
    attempt_result = _run_attempt(
        client, model, system_blocks, tool, max_tokens, messages, catalog, log_repairs
    )
    if attempt_result.text:
      all_text_parts.append(attempt_result.text)
    result.repairs.extend(attempt_result.repairs)

    if attempt_result.a2ui_json is not None:
      result.all_payloads.append(attempt_result.a2ui_json)

    if attempt_result.error is None:
      result.a2ui_json = attempt_result.a2ui_json
      result.text = "\n".join(all_text_parts)
      result.success = True
      return result

    # Preparar feedback para reintentar
    if attempt > max_retries or not attempt_result.retryable:
      result.error = attempt_result.error
      result.text = "\n".join(all_text_parts)
      return result

    messages.extend(
        _retry_feedback_messages(attempt_result, fallback_id=f"toolu_retry_{attempt}")
    )

  result.error = attempt_result.error
  result.text = "\n".join(all_text_parts)
  return result


async def generate_a2ui_async(
    client: anthropic.AsyncAnthropic,
    prompt: str,
    *,
    builder: Optional[ClaudeA2uiPromptBuilder] = None,
    allowed_components: Optional[list[str]] = None,
    allowed_messages: Optional[list[str]] = None,
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
  _validate_generation_options(max_tokens=max_tokens, max_retries=max_retries)
  if builder is None:
    builder = ClaudeA2uiPromptBuilder(version="0.9")

  catalog = builder.get_catalog(
      allowed_components=allowed_components,
      allowed_messages=allowed_messages,
  )
  tool = cast(ToolParam, create_a2ui_tool(catalog))
  system_prompt = builder.build(
      role_description=role_description,
      allowed_components=allowed_components,
      allowed_messages=allowed_messages,
      include_schema=True,
      include_examples=True,
  )
  system_blocks = _build_system_block(system_prompt, use_cache=use_cache)

  messages: list[MessageParam] = [{"role": "user", "content": prompt}]
  result = RetryResult()
  all_text_parts: list[str] = []

  for attempt in range(1, max_retries + 2):
    result.attempts = attempt
    attempt_result = await _run_attempt_async(
        client, model, system_blocks, tool, max_tokens, messages, catalog, log_repairs
    )
    if attempt_result.text:
      all_text_parts.append(attempt_result.text)
    result.repairs.extend(attempt_result.repairs)

    if attempt_result.a2ui_json is not None:
      result.all_payloads.append(attempt_result.a2ui_json)

    if attempt_result.error is None:
      result.a2ui_json = attempt_result.a2ui_json
      result.text = "\n".join(all_text_parts)
      result.success = True
      return result

    if attempt > max_retries or not attempt_result.retryable:
      result.error = attempt_result.error
      result.text = "\n".join(all_text_parts)
      return result

    messages.extend(
        _retry_feedback_messages(attempt_result, fallback_id=f"toolu_retry_{attempt}")
    )

  result.error = attempt_result.error
  result.text = "\n".join(all_text_parts)
  return result


async def _run_attempt_async(
    client: anthropic.AsyncAnthropic,
    model: str,
    system_blocks: list[TextBlockParam],
    tool: ToolParam,
    max_tokens: int,
    messages: list[MessageParam],
    catalog: Any,
    log_repairs: bool,
) -> _AttemptResult:
  """Version async de ``_run_attempt``."""
  parser = ClaudeStreamParser(catalog=catalog, strict_tool_validation=True, repair=True)

  a2ui_payload: Optional[list] = None
  text_parts: list[str] = []
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
          a2ui_payload = validate_tool_input(catalog, a2ui_payload, repair=True)
          return _AttemptResult(
              a2ui_json=a2ui_payload,
              text=text,
              repairs=list(parser.last_repairs) if log_repairs else [],
              tool_use_id=parser.last_tool_use_id,
              tool_input=parser.last_tool_input,
              tool_used=parser.last_tool_used,
          )
        except Exception as ve:
          return _AttemptResult(
              a2ui_json=a2ui_payload,
              text=text,
              error=_format_error(ve),
              tool_use_id=parser.last_tool_use_id,
              tool_input=parser.last_tool_input,
              tool_used=parser.last_tool_used,
          )
      else:
        return _AttemptResult(
            text=text,
            error=(
                "Claude no genero A2UI. Responde solo con la tool "
                "send_a2ui_json_to_client cuando el usuario pida una interfaz."
            ),
            tool_use_id=parser.last_tool_use_id,
            tool_input=parser.last_tool_input,
            tool_used=parser.last_tool_used,
        )

  except Exception as exc:
    payload = parser.last_a2ui_json
    return _AttemptResult(
        a2ui_json=payload if isinstance(payload, list) else None,
        text="".join(text_parts),
        error=_format_error(exc),
        repairs=list(parser.last_repairs) if log_repairs else [],
        tool_use_id=parser.last_tool_use_id,
        tool_input=parser.last_tool_input,
        tool_used=parser.last_tool_used,
        retryable=parser.last_tool_used,
    )


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
  attempts: int = 0
  repairs: list[str] = field(default_factory=list)


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
      allowed_components: Optional[list[str]] = None,
      allowed_messages: Optional[list[str]] = None,
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
    _validate_generation_options(max_tokens=max_tokens, max_retries=max_retries)
    self.client = client
    self.model = model
    self.max_tokens = max_tokens
    self.max_retries = max_retries
    self.use_cache = use_cache
    self.log_repairs = log_repairs

    if builder is None:
      builder = ClaudeA2uiPromptBuilder(version="0.9")
    self.builder = builder
    self.catalog = builder.get_catalog(
        allowed_components=allowed_components,
        allowed_messages=allowed_messages,
    )
    self.tool = cast(ToolParam, create_a2ui_tool(self.catalog))
    system_prompt = builder.build(
        role_description=role_description,
        allowed_components=allowed_components,
        allowed_messages=allowed_messages,
        include_schema=True,
        include_examples=True,
    )
    self.system_blocks = _build_system_block(system_prompt, use_cache=use_cache)

    self.messages: list[MessageParam] = []
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
    text_parts: list[str] = []

    for attempt in range(1, self.max_retries + 2):
      turn.attempts = attempt
      attempt_result = _run_attempt(
          self.client,
          self.model,
          self.system_blocks,
          self.tool,
          self.max_tokens,
          self.messages,
          self.catalog,
          self.log_repairs,
      )
      if attempt_result.text:
        text_parts.append(attempt_result.text)
      turn.repairs.extend(attempt_result.repairs)

      if attempt_result.error is None and attempt_result.a2ui_json is not None:
        turn.a2ui_json = attempt_result.a2ui_json
        turn.text = "\n".join(text_parts)
        turn.success = True
        self.last_a2ui_json = attempt_result.a2ui_json
        # Anadir respuesta de Claude al historial
        tool_use_id = attempt_result.tool_use_id or (
            f"toolu_turn_{len(self.turns)}_{attempt}"
        )
        self.messages.append(
            _tool_use_message(
                tool_use_id,
                attempt_result.a2ui_json,
                text=attempt_result.text,
            )
        )
        self.messages.append(_tool_result_message(tool_use_id))
        self.turns.append(turn)
        return turn

      has_more_attempts = attempt <= self.max_retries and attempt_result.retryable
      if has_more_attempts:
        self.messages.extend(
            _retry_feedback_messages(
                attempt_result,
                fallback_id=f"toolu_turn_{len(self.turns)}_{attempt}",
            )
        )
        continue

      # Si Claude ya uso la tool, cerrar ese uso incluso cuando no haya otro
      # intento. Si no, conservar solo su respuesta de texto en el historial.
      if attempt_result.tool_used:
        tool_use_id = attempt_result.tool_use_id or (
            f"toolu_turn_{len(self.turns)}_{attempt}"
        )
        self.messages.append(
            _tool_use_message(
                tool_use_id,
                attempt_result.a2ui_json,
                tool_input=attempt_result.tool_input,
                text=attempt_result.text,
            )
        )
        self.messages.append(
            _tool_error_result_message(tool_use_id, attempt_result.error)
        )
      elif attempt_result.text:
        self.messages.append(_assistant_text_message(attempt_result.text))

      turn.error = attempt_result.error
      turn.text = "\n".join(text_parts)
      self.turns.append(turn)
      return turn

    turn.error = "No se ejecuto ningun intento de generacion"
    turn.text = "\n".join(text_parts)
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
      allowed_components: Optional[list[str]] = None,
      allowed_messages: Optional[list[str]] = None,
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
    _validate_generation_options(max_tokens=max_tokens, max_retries=max_retries)
    self.client = client
    self.model = model
    self.max_tokens = max_tokens
    self.max_retries = max_retries
    self.use_cache = use_cache
    self.log_repairs = log_repairs

    if builder is None:
      builder = ClaudeA2uiPromptBuilder(version="0.9")
    self.builder = builder
    self.catalog = builder.get_catalog(
        allowed_components=allowed_components,
        allowed_messages=allowed_messages,
    )
    self.tool = cast(ToolParam, create_a2ui_tool(self.catalog))
    system_prompt = builder.build(
        role_description=role_description,
        allowed_components=allowed_components,
        allowed_messages=allowed_messages,
        include_schema=True,
        include_examples=True,
    )
    self.system_blocks = _build_system_block(system_prompt, use_cache=use_cache)

    self.messages: list[MessageParam] = []
    self.turns: list[ConversationTurn] = []
    self.last_a2ui_json: Optional[list[dict[str, Any]]] = None

  async def send(self, prompt: str) -> ConversationTurn:
    """Envia un mensaje y devuelve el turno (async)."""
    self.messages.append({"role": "user", "content": prompt})
    turn = ConversationTurn(user_prompt=prompt)
    text_parts: list[str] = []

    for attempt in range(1, self.max_retries + 2):
      turn.attempts = attempt
      attempt_result = await _run_attempt_async(
          self.client,
          self.model,
          self.system_blocks,
          self.tool,
          self.max_tokens,
          self.messages,
          self.catalog,
          self.log_repairs,
      )
      if attempt_result.text:
        text_parts.append(attempt_result.text)
      turn.repairs.extend(attempt_result.repairs)

      if attempt_result.error is None and attempt_result.a2ui_json is not None:
        turn.a2ui_json = attempt_result.a2ui_json
        turn.text = "\n".join(text_parts)
        turn.success = True
        self.last_a2ui_json = attempt_result.a2ui_json
        tool_use_id = attempt_result.tool_use_id or (
            f"toolu_turn_{len(self.turns)}_{attempt}"
        )
        self.messages.append(
            _tool_use_message(
                tool_use_id,
                attempt_result.a2ui_json,
                text=attempt_result.text,
            )
        )
        self.messages.append(_tool_result_message(tool_use_id))
        self.turns.append(turn)
        return turn

      has_more_attempts = attempt <= self.max_retries and attempt_result.retryable
      if has_more_attempts:
        self.messages.extend(
            _retry_feedback_messages(
                attempt_result,
                fallback_id=f"toolu_turn_{len(self.turns)}_{attempt}",
            )
        )
        continue

      if attempt_result.tool_used:
        tool_use_id = attempt_result.tool_use_id or (
            f"toolu_turn_{len(self.turns)}_{attempt}"
        )
        self.messages.append(
            _tool_use_message(
                tool_use_id,
                attempt_result.a2ui_json,
                tool_input=attempt_result.tool_input,
                text=attempt_result.text,
            )
        )
        self.messages.append(
            _tool_error_result_message(tool_use_id, attempt_result.error)
        )
      elif attempt_result.text:
        self.messages.append(_assistant_text_message(attempt_result.text))

      turn.error = attempt_result.error
      turn.text = "\n".join(text_parts)
      self.turns.append(turn)
      return turn

    turn.error = "No se ejecuto ningun intento de generacion"
    turn.text = "\n".join(text_parts)
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
    allowed_messages: Optional[list[str]] = None,
) -> dict[str, Any]:
  """Crea el formato JSON para ``output_config.format`` de Anthropic.

  Anthropic soporta structured outputs con ``output_config.format`` y
  ``type: "json_schema"`` para garantizar un sobre JSON parseable sin
  necesidad de tools ni tags. Este modo es util cuando se quiere UI pura
  sin texto conversacional.

  El schema completo de A2UI contiene ``oneOf``, que Anthropic no admite en
  JSON outputs. Por eso el sobre fuerza ``a2ui_json`` como una cadena que
  contiene el array A2UI serializado. ``parse_json_response`` lo deserializa
  y aplica despues la validacion estricta del catalogo activo. Si se usan
  restricciones, pasarlas tambien a ``parse_json_response`` para imponerlas
  localmente.

  Args:
    catalog: ``A2uiCatalog`` que se usara al validar la respuesta.
    allowed_components: Subconjunto de componentes indicado al modelo. Para
      imponerlo, repetirlo al llamar a ``parse_json_response``.
    allowed_messages: Subconjunto de tipos de mensaje indicado al modelo. Para
      imponerlo, repetirlo al llamar a ``parse_json_response``.

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
    # response.content[0].text contiene
    # {"a2ui_json": "[{... mensajes A2UI serializados ...}]"}
    ```
  """
  from .prompt_builder import _prune_catalog

  pruned_catalog = _prune_catalog(
      catalog,
      allowed_components=allowed_components,
      allowed_messages=allowed_messages,
  )
  component_names = sorted(pruned_catalog.catalog_schema.get("components", {}))
  description = (
      "A JSON-serialized array of complete A2UI messages. "
      "Do not use Markdown or code fences."
  )
  if allowed_components is not None:
    description += " Allowed components: " + ", ".join(component_names) + "."
  return {
      "type": "json_schema",
      "schema": {
          "type": "object",
          "properties": {
              "a2ui_json": {
                  "type": "string",
                  "description": description,
              },
          },
          "required": ["a2ui_json"],
          "additionalProperties": False,
      },
  }


def create_a2ui_output_config(
    catalog: Any,
    *,
    allowed_components: Optional[list[str]] = None,
    allowed_messages: Optional[list[str]] = None,
) -> dict[str, Any]:
  """Crea ``output_config`` completo para structured outputs de Anthropic."""
  return {
      "format": create_a2ui_response_format(
          catalog,
          allowed_components=allowed_components,
          allowed_messages=allowed_messages,
      )
  }


def parse_json_response(
    message: Any,
    catalog: Any,
    *,
    allowed_components: Optional[list[str]] = None,
    allowed_messages: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
  """Extrae y valida el A2UI de una respuesta con structured output.

  Cuando se usa ``output_config.format``, la respuesta de Claude viene como
  un ``TextBlock`` cuyo ``text`` es un JSON string con ``a2ui_json`` como
  array (formato heredado) o como una cadena que serializa el array (formato
  compatible con structured outputs de Anthropic). Esta funcion lo extrae,
  desenvuelve, repara y valida.

  Args:
    message: El mensaje de respuesta de ``client.messages.create``.
    catalog: ``A2uiCatalog`` para validacion.
    allowed_components: Subconjunto de componentes que se permite renderizar.
      Debe coincidir con el usado en ``create_a2ui_output_config``.
    allowed_messages: Subconjunto de tipos de mensaje que se permite
      renderizar. Debe coincidir con el usado en
      ``create_a2ui_output_config``.

  Returns:
    Lista de mensajes A2UI validados y reparados.

  Raises:
    ValueError: Si el JSON no es valido o no contiene ``a2ui_json``.
  """
  import json

  from .prompt_builder import _prune_catalog

  catalog = _prune_catalog(
      catalog,
      allowed_components=allowed_components,
      allowed_messages=allowed_messages,
  )

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
  if isinstance(parsed, dict) and set(parsed) == {"a2ui_json"}:
    payload = parsed["a2ui_json"]
  elif isinstance(parsed, list):
    payload = parsed
  else:
    raise ValueError("La respuesta no contiene a2ui_json")

  if isinstance(payload, str):
    try:
      payload = json.loads(payload)
    except json.JSONDecodeError as exc:
      raise ValueError(f"a2ui_json serializado no es JSON valido: {exc}") from exc

  return validate_tool_input(catalog, payload, repair=True)


def _validate_generation_options(*, max_tokens: int, max_retries: int) -> None:
  """Rechaza parametros que no pueden producir una llamada valida."""
  if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
    raise TypeError("max_tokens debe ser un entero")
  if max_tokens <= 0:
    raise ValueError("max_tokens debe ser mayor que cero")
  if isinstance(max_retries, bool) or not isinstance(max_retries, int):
    raise TypeError("max_retries debe ser un entero")
  if max_retries < 0:
    raise ValueError("max_retries no puede ser negativo")


def _assistant_text_message(text: str) -> MessageParam:
  return cast(
      MessageParam,
      {"role": "assistant", "content": [{"type": "text", "text": text}]},
  )


def _tool_use_message(
    tool_use_id: str,
    a2ui_payload: Optional[list[Any]] = None,
    *,
    tool_input: Any = None,
    text: str = "",
) -> MessageParam:
  """Construye el mensaje assistant que representa la tool A2UI usada."""
  if not isinstance(tool_input, dict):
    tool_input = {"a2ui_json": a2ui_payload or []}
  content: list[dict[str, Any]] = []
  if text:
    content.append({"type": "text", "text": text})
  content.append({
      "type": "tool_use",
      "id": tool_use_id,
      "name": "send_a2ui_json_to_client",
      "input": tool_input,
  })
  return cast(MessageParam, {"role": "assistant", "content": content})


def _tool_result_message(tool_use_id: str) -> MessageParam:
  """Construye el tool_result de exito para cerrar el bucle de Anthropic."""
  return cast(
      MessageParam,
      {
          "role": "user",
          "content": [{
              "type": "tool_result",
              "tool_use_id": tool_use_id,
              "content": "A2UI recibido y renderizado por el cliente.",
          }],
      },
  )


def _tool_error_result_message(tool_use_id: str, error: Optional[str]) -> MessageParam:
  return cast(
      MessageParam,
      {
          "role": "user",
          "content": [{
              "type": "tool_result",
              "tool_use_id": tool_use_id,
              "content": f"El JSON A2UI no es valido: {error or 'error desconocido'}",
              "is_error": True,
          }],
      },
  )


def _retry_feedback_messages(
    attempt: _AttemptResult,
    *,
    fallback_id: str,
) -> list[MessageParam]:
  """Reconstruye la respuesta del modelo antes de pedirle que se corrija."""
  if attempt.tool_used:
    tool_use_id = attempt.tool_use_id or fallback_id
    return [
        _tool_use_message(
            tool_use_id,
            attempt.a2ui_json,
            tool_input=attempt.tool_input,
            text=attempt.text,
        ),
        _tool_error_result_message(tool_use_id, attempt.error),
    ]
  assistant_text = attempt.text or "No se genero contenido A2UI."
  return [
      _assistant_text_message(assistant_text),
      cast(
          MessageParam,
          {
              "role": "user",
              "content": f"{attempt.error} Usa la tool send_a2ui_json_to_client.",
          },
      ),
  ]
