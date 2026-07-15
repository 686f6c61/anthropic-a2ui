# Live Verification 0.1.3

Date: 2026-07-15

## Automated verification

- `638` tests passed on Python 3.10, 3.11, 3.12, and 3.13.
- Pyink, Ruff, Mypy, and Bandit completed without findings.
- `pip-audit --strict --local` found no known vulnerable installed packages.
- The wheel and source distribution passed `twine check`.

## Finding

The 0.1.2 structured-output helper sent the full A2UI server-to-client schema
inside `output_config.format`. A live request to Anthropic returned HTTP 400:
`Schema type 'oneOf' is not supported`.

## Fix

The 0.1.3 helper sends a provider-compatible strict JSON envelope with one
required `a2ui_json` string. The string contains the JSON-serialized A2UI
message array. `parse_json_response` decodes that string, applies repairs, and
then performs the existing strict A2UI validation with the active catalog.
When component or message restrictions are used, the caller passes the same
limits to `parse_json_response`; it validates with the correspondingly pruned
catalog.

## Live verification

- The Models API listed `claude-haiku-4-5-20251001` for the configured key.
- `generate_a2ui` created a valid three-message contact form in one attempt.
- A real two-turn `A2uiConversation` completed both turns in one attempt and
  closed two matching `tool_use` / `tool_result` pairs.
- The original full-schema structured-output request failed with the expected
  `oneOf` error.
- The new serialized-envelope request returned a valid three-message A2UI
  payload with `stop_reason="end_turn"` and passed strict local validation.
- The documented restricted structured-output flow returned only `Button`,
  `Column`, `Text`, and `TextField`, then passed validation with its pruned
  catalog.

## Security note

The provider grammar guarantees the outer JSON envelope only. The A2UI payload
remains untrusted model output and must pass `parse_json_response` before it is
rendered. Renderer-side escaping, URL policy, authorization, CSP or sandboxing,
and resource limits remain mandatory.
