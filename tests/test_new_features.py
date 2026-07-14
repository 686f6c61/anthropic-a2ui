"""Tests de las mejoras nuevas: multi-turno, async, caching, structured output."""

from __future__ import annotations

import inspect
import pytest

from anthropic_a2ui import (
    A2uiConversation,
    A2uiConversationAsync,
    ConversationTurn,
    RetryResult,
    create_a2ui_output_config,
    create_a2ui_response_format,
    generate_a2ui,
    generate_a2ui_async,
    parse_json_response,
    validate_tool_input,
)


class TestGenerateA2ui:
  """generate_a2ui: funcion de alto nivel con reintentos y caching."""

  def test_es_importable(self):
    assert callable(generate_a2ui)

  def test_signatura_tiene_use_cache(self):
    sig = inspect.signature(generate_a2ui)
    assert "use_cache" in sig.parameters
    assert sig.parameters["use_cache"].default is True

  def test_signatura_tiene_log_repairs(self):
    sig = inspect.signature(generate_a2ui)
    assert "log_repairs" in sig.parameters
    assert sig.parameters["log_repairs"].default is False

  def test_signatura_tiene_max_retries(self):
    sig = inspect.signature(generate_a2ui)
    assert sig.parameters["max_retries"].default == 2

  def test_retry_result_tiene_repairs(self):
    r = RetryResult()
    assert r.repairs == []


class TestGenerateA2uiAsync:
  """generate_a2ui_async: version async."""

  def test_es_importable(self):
    assert callable(generate_a2ui_async)

  def test_es_corutina(self):
    assert inspect.iscoroutinefunction(generate_a2ui_async)

  def test_signatura_tiene_use_cache(self):
    sig = inspect.signature(generate_a2ui_async)
    assert "use_cache" in sig.parameters


class TestA2uiConversation:
  """A2uiConversation: conversacion multi-turno."""

  def test_es_importable(self):
    assert A2uiConversation is not None

  def test_tiene_metodo_send(self):
    assert hasattr(A2uiConversation, "send")
    assert callable(getattr(A2uiConversation, "send"))

  def test_tiene_metodo_reset(self):
    assert hasattr(A2uiConversation, "reset")
    assert callable(getattr(A2uiConversation, "reset"))

  def test_tiene_turns_y_messages(self):
    # Verificar que la clase define los atributos
    init_sig = inspect.signature(A2uiConversation.__init__)
    params = list(init_sig.parameters.keys())
    assert "client" in params
    assert "model" in params
    assert "max_retries" in params
    assert "use_cache" in params
    assert "log_repairs" in params

  def test_conversation_turn_es_dataclass(self):
    t = ConversationTurn(user_prompt="test")
    assert t.user_prompt == "test"
    assert t.a2ui_json is None
    assert t.text == ""
    assert t.success is False
    assert t.error is None

  def test_success_cierra_tool_use_con_tool_result(self, monkeypatch, sample_a2ui_json):
    import anthropic_a2ui.retry as retry_mod

    def fake_run_attempt(*args, **kwargs):
      return retry_mod._AttemptResult(
          a2ui_json=sample_a2ui_json,
          tool_used=True,
      )

    monkeypatch.setattr(retry_mod, "_run_attempt", fake_run_attempt)
    conv = A2uiConversation(object(), max_retries=0)
    turn = conv.send("make me a form")

    assert turn.success is True
    tool_use = conv.messages[-2]["content"][0]
    tool_result = conv.messages[-1]["content"][0]
    assert tool_use["type"] == "tool_use"
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == tool_use["id"]


class TestA2uiConversationAsync:
  """A2uiConversationAsync: version async de la conversacion."""

  def test_es_importable(self):
    assert A2uiConversationAsync is not None

  def test_send_es_corutina(self):
    assert inspect.iscoroutinefunction(A2uiConversationAsync.send)

  @pytest.mark.asyncio
  async def test_success_cierra_tool_use_con_tool_result_async(
      self, monkeypatch, sample_a2ui_json
  ):
    import anthropic_a2ui.retry as retry_mod

    async def fake_run_attempt_async(*args, **kwargs):
      return retry_mod._AttemptResult(
          a2ui_json=sample_a2ui_json,
          tool_used=True,
      )

    monkeypatch.setattr(retry_mod, "_run_attempt_async", fake_run_attempt_async)
    conv = A2uiConversationAsync(object(), max_retries=0)
    turn = await conv.send("make me a form")

    assert turn.success is True
    tool_use = conv.messages[-2]["content"][0]
    tool_result = conv.messages[-1]["content"][0]
    assert tool_use["type"] == "tool_use"
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == tool_use["id"]


class TestCreateA2uiResponseFormat:
  """create_a2ui_response_format: tercer modo de generacion."""

  def test_es_importable(self):
    assert callable(create_a2ui_response_format)

  def test_devuelve_formato_anthropic(self, catalog_v09):
    rf = create_a2ui_response_format(catalog_v09)
    assert rf["type"] == "json_schema"
    assert "schema" in rf
    assert "json_schema" not in rf

  def test_schema_envuelve_a2ui_json(self, catalog_v09):
    rf = create_a2ui_response_format(catalog_v09)
    schema = rf["schema"]
    assert schema["type"] == "object"
    assert "a2ui_json" in schema["properties"]
    assert schema["properties"]["a2ui_json"]["type"] == "array"

  def test_con_poda(self, catalog_v09):
    rf = create_a2ui_response_format(catalog_v09, allowed_components=["Text"])
    schema = rf["schema"]
    assert "a2ui_json" in schema["properties"]

  def test_output_config_envuelve_format(self, catalog_v09):
    output_config = create_a2ui_output_config(catalog_v09)
    assert output_config["format"]["type"] == "json_schema"
    assert "schema" in output_config["format"]


class TestParseJsonResponse:
  """parse_json_response: extrae A2UI de una respuesta structured output."""

  def test_es_importable(self):
    assert callable(parse_json_response)

  def test_extrae_de_text_block(self, catalog_v09):
    import json
    from dataclasses import dataclass

    @dataclass
    class FakeTextBlock:
      text: str

    @dataclass
    class FakeMessage:
      content: list

    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{"id": "root", "component": "Text", "text": "Hola"}],
            },
        },
    ]
    msg = FakeMessage(content=[FakeTextBlock(text=json.dumps({"a2ui_json": payload}))])
    result = parse_json_response(msg, catalog_v09)
    assert len(result) == 2
    assert result[1]["updateComponents"]["components"][0]["text"] == "Hola"

  def test_devuelve_payload_reparado(self, catalog_v09):
    import json
    from dataclasses import dataclass

    @dataclass
    class FakeTextBlock:
      text: str

    @dataclass
    class FakeMessage:
      content: list

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
                    {"id": "root", "component": "Column", "children": ["icon"]},
                    {"id": "icon", "component": "Icon", "name": "cloud"},
                ],
            },
        },
    ]
    msg = FakeMessage(content=[FakeTextBlock(text=json.dumps({"a2ui_json": payload}))])
    result = parse_json_response(msg, catalog_v09)
    icon = result[1]["updateComponents"]["components"][1]

    assert icon["name"] == "info"
    validate_tool_input(catalog_v09, result, repair=False)

  def test_lanza_si_no_hay_texto(self, catalog_v09):
    from dataclasses import dataclass

    @dataclass
    class FakeMessage:
      content: list

    msg = FakeMessage(content=[])
    with pytest.raises(ValueError, match="no contiene texto"):
      parse_json_response(msg, catalog_v09)

  def test_lanza_si_no_es_json(self, catalog_v09):
    from dataclasses import dataclass

    @dataclass
    class FakeTextBlock:
      text: str

    @dataclass
    class FakeMessage:
      content: list

    msg = FakeMessage(content=[FakeTextBlock(text="no es json")])
    with pytest.raises(ValueError, match="no es JSON"):
      parse_json_response(msg, catalog_v09)

  def test_lanza_si_no_tiene_a2ui_json(self, catalog_v09):
    import json
    from dataclasses import dataclass

    @dataclass
    class FakeTextBlock:
      text: str

    @dataclass
    class FakeMessage:
      content: list

    msg = FakeMessage(content=[FakeTextBlock(text=json.dumps({"otra_cosa": 1}))])
    with pytest.raises(ValueError, match="no contiene a2ui_json"):
      parse_json_response(msg, catalog_v09)


class TestPyTyped:
  """Verifica que py.typed existe para soporte de IDE."""

  def test_py_typed_existe(self):
    from pathlib import Path
    import anthropic_a2ui

    pkg_dir = Path(anthropic_a2ui.__file__).parent
    assert (pkg_dir / "py.typed").exists()


class TestPromptCaching:
  """Verifica que el system prompt se construye con cache_control."""

  def test_build_system_block_con_cache(self):
    from anthropic_a2ui.retry import _build_system_block

    blocks = _build_system_block("test prompt", use_cache=True)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "text"
    assert blocks[0]["text"] == "test prompt"
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}

  def test_build_system_block_sin_cache(self):
    from anthropic_a2ui.retry import _build_system_block

    blocks = _build_system_block("test prompt", use_cache=False)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "text"
    assert "cache_control" not in blocks[0]
