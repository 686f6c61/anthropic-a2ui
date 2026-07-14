"""Regresiones de contrato cerradas en la version 0.1.2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from anthropic_a2ui import ClaudeStreamParser, generate_a2ui, repair_payload


@dataclass
class _Block:
  type: str
  name: str = "send_a2ui_json_to_client"
  id: str = "toolu_real"


@dataclass
class _Start:
  type: str
  index: int
  content_block: Any


@dataclass
class _Delta:
  partial_json: str
  type: str = "input_json_delta"


@dataclass
class _DeltaEvent:
  type: str
  delta: Any
  index: int


@dataclass
class _Stop:
  type: str
  index: int


class _Stream:

  def __init__(self, events: list[Any]):
    self.events = events

  def __enter__(self) -> list[Any]:
    return self.events

  def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
    return False


class _Messages:

  def __init__(self, batches: list[list[Any]]):
    self.batches = batches
    self.calls: list[dict[str, Any]] = []

  def stream(self, **kwargs: Any) -> _Stream:
    self.calls.append(kwargs)
    return _Stream(self.batches.pop(0))


class _Client:

  def __init__(self, batches: list[list[Any]]):
    self.messages = _Messages(batches)


def _tool_events(payload: Any, *, tool_id: str = "toolu_real") -> list[Any]:
  return [
      _Start("content_block_start", 0, _Block("tool_use", id=tool_id)),
      _DeltaEvent(
          "content_block_delta",
          _Delta(json.dumps({"a2ui_json": payload})),
          0,
      ),
      _Stop("content_block_stop", 0),
  ]


class TestRetryContract:

  def test_retry_uses_the_actual_tool_id_and_raw_input(self, sample_a2ui_json):
    invalid = [{"version": "v0.9", "createSurface": {"surfaceId": "s"}}]
    client = _Client([
        _tool_events(invalid, tool_id="toolu_original"),
        _tool_events(sample_a2ui_json),
    ])

    result = generate_a2ui(client, "make a form", max_retries=1)

    assert result.success is True
    assert result.attempts == 2
    assert len(result.all_payloads) == 2
    retry_messages = client.messages.calls[1]["messages"]
    tool_use = retry_messages[-2]["content"][0]
    tool_result = retry_messages[-1]["content"][0]
    assert tool_use["id"] == "toolu_original"
    assert tool_use["input"] == {"a2ui_json": invalid}
    assert tool_result["tool_use_id"] == "toolu_original"
    assert tool_result["is_error"] is True

  def test_transport_error_does_not_retry_as_model_feedback(self):
    class FailingMessages:

      def __init__(self) -> None:
        self.calls = 0

      def stream(self, **kwargs: Any) -> Any:
        self.calls += 1
        raise RuntimeError("network unavailable")

    class FailingClient:

      def __init__(self) -> None:
        self.messages = FailingMessages()

    client = FailingClient()
    result = generate_a2ui(client, "make a form", max_retries=2)

    assert result.success is False
    assert result.attempts == 1
    assert client.messages.calls == 1

  @pytest.mark.parametrize("max_retries", [-1, True, "1"])
  def test_invalid_retry_count_fails_before_call(self, max_retries: Any):
    with pytest.raises((TypeError, ValueError)):
      generate_a2ui(object(), "make a form", max_retries=max_retries)


class TestRepairContract:

  def test_valid_info_icon_is_not_logged_as_a_repair(self, catalog_v09):
    payload = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": catalog_v09.catalog_id},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{"id": "root", "component": "Icon", "name": "info"}],
            },
        },
    ]
    repairs: list[str] = []

    repaired = repair_payload(payload, catalog=catalog_v09, repair_log=repairs)

    assert repaired == payload
    assert repairs == []

  def test_custom_catalog_function_is_preserved(self, catalog_minimal):
    payload = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "s",
                "catalogId": catalog_minimal.catalog_id,
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s",
                "components": [{
                    "id": "root",
                    "component": "Text",
                    "text": {
                        "call": "capitalize",
                        "args": {"value": "hola"},
                        "returnType": "string",
                    },
                }],
            },
        },
    ]

    repaired = repair_payload(payload, catalog=catalog_minimal)

    assert (
        repaired[1]["updateComponents"]["components"][0]["text"]["call"] == "capitalize"
    )

  def test_parser_ignores_non_a2ui_tools(self, catalog_v09, sample_a2ui_json):
    parser = ClaudeStreamParser(catalog=catalog_v09, strict_tool_validation=False)
    events = _tool_events(sample_a2ui_json)
    events[0].content_block.name = "web_search"

    assert [part for event in events for part in parser.process_event(event)] == []
