# Changelog

All notable changes to `anthropic-a2ui` are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the versioning follows [SemVer](https://semver.org/).

## [0.1.3] - 2026-07-15

### Fixed

- Replaced the structured-output schema that Anthropic rejected because it
  contained A2UI's unsupported `oneOf` branches. The provider now receives a
  strict JSON envelope with a serialized A2UI array, which
  `parse_json_response` deserializes and validates locally.
- Made structured-output component and message restrictions enforceable during
  the final local validation by passing the same limits to
  `parse_json_response`.

### Changed

- Verified live tool use, two-turn conversation history, and structured output
  with `claude-haiku-4-5-20251001`.

## [0.1.2] - 2026-07-14

### Fixed

- Made retry feedback reproduce the actual Anthropic tool-use ID and raw tool
  input, so a validation failure can be corrected by the model instead of
  silently falling back to prose.
- Do not retry transport and SDK failures as model-correction prompts.
- Made `allowed_components` constrain the generated tool and structured-output
  schemas, not only the prompt. Public A2UI message names now normalize to the
  schema definitions expected by `a2ui-agent-sdk`.
- Reject empty A2UI payloads and invalid retry settings early.
- Ignore non-A2UI tool calls in `ClaudeStreamParser` and cap buffered tool JSON
  at 2 MB.
- Made all repair paths use the active catalog, preserving valid custom icons
  and functions. Repair logs now record only real changes.
- Made orphan repair safe for multiple surfaces, non-container roots, and
  pre-existing generated component IDs.
- Narrowed the optional `a2a-sdk` import fallback to `ImportError` so runtime
  faults in an installed SDK are not hidden.

### Changed

- Added regression tests for retry tool-result identity, custom catalogs,
  payload bounds, and ignored tools.
- Added Ruff, Mypy, and Bandit checks to CI and to the PyPI publication gate.
- Documented the renderer security boundary and the live-verification limits
  of structured-output mode.

## [0.1.1] - 2026-06-21

### Fixed

- Removed the accidental `pyink` console entry point from the published
  wheel.
- Updated structured output helpers and documentation to use Anthropic's
  `output_config.format` shape.
- Fixed `repair_orphans` for leaf `root` components so repairs keep a valid
  `id="root"` component.
- Made `parse_json_response` return the repaired A2UI payload instead of
  validating a repaired copy while returning the original.
- Closed successful `A2uiConversation` tool-use turns with a matching
  `tool_result` message in sync and async conversations.
- Switched the default Sonnet model in high-level helpers to
  `claude-sonnet-4-6`.

### Changed

- Added PyPI project URLs, classifiers, and maintainer metadata.
- Hardened the PyPI publish workflow with tests, format check, and
  `twine check` before upload.

## [0.1.0] - 2026-06-21

### Added

- **`generate_a2ui`**: high-level function that calls Claude, validates,
  repairs, and retries on failure. Returns a `RetryResult` with the
  validated A2UI payload.
- **`generate_a2ui_async`**: async version of `generate_a2ui` for
  integration with async servers (FastAPI, Starlette, etc.).
- **`A2uiConversation`**: multi-turn conversation that maintains message
  history across turns so the user can iterate ("make me a form" ->
  "add a field" -> "change the color"). Claude generates a new A2UI
  payload with all changes applied in each turn.
- **`A2uiConversationAsync`**: async version of `A2uiConversation`.
- **Prompt caching**: `use_cache=True` by default in `generate_a2ui` and
  `A2uiConversation`. Adds `cache_control` to the system prompt to
  reduce cost by ~80% on repeated calls.
- **Third mode `response_format`**: `create_a2ui_response_format` and
  `parse_json_response` for forced JSON output without tools or tags.
- **Repair logging**: `log_repairs=True` records what was repaired
  ("Icon 'cloud' substituted with 'info'", etc.).
- **`py.typed`**: type marker for IDE support (autocompletion, type
  checking).
- **`ClaudeA2uiPromptBuilder`**: constructs the system prompt with schema
  + few-shot examples + list of 59 valid icon names + list of 14 valid
  catalog functions.
- **`create_a2ui_tool`**: defines the `send_a2ui_json_to_client` tool
  with schema wrapped in `{"a2ui_json": [...]}` to avoid `oneOf` at the
  root level (which the Anthropic API rejects).
- **`ClaudeStreamParser`**: parses the Anthropic stream and emits
  `ResponsePart` objects (text + `<a2ui-json>` blocks and tool use).
  Repairs and validates automatically.
- **`to_a2ui_part` / `A2uiPart`**: transport helpers with MIME
  `application/a2ui+json`.
- **`validate_tool_input`**: validates A2UI payloads against the schema
  with automatic repair.
- **Five automatic repairs**:
  1. `patch_catalog_schema`: fixes `DateTimeInput.min/max` ambiguous
     `oneOf` by changing it to `anyOf`.
  2. `repair_orphans`: reconnects orphaned components to the `root`
     tree.
  3. `repair_icons`: maps 100+ common icon aliases to the 59 valid
     catalog icons; unknown names become `info`.
  4. `repair_functions`: replaces non-existent function calls
     (`ternary`, `if`, `switch`) with literal values.
  5. `repair_childlists`: converts dynamic child lists
     (`{componentId, path}`) in `Row`/`Column` to static string arrays.
- **620 tests** covering: 19 cross-catalog components, 15 functions,
  4 message types, optional properties, multi-catalog, multi-version,
  5 repairs, multi-turn, async, caching, response_format.
- **Fire test**: 30 natural prompts x 3 models = 30/30 OK (Haiku 4.5,
  Opus 4.7, Opus 4.8).
- **CI** with GitHub Actions (pytest + pyink on Python 3.10-3.13).
