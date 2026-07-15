```
             ___    _    _   _____ 
     /\     |__ \  | |  | | |_   _|
    /  \       ) | | |  | |   | |  
   / /\ \     / /  | |  | |   | |  
  / ____ \   / /_  | |__| |  _| |_ 
 /_/    \_\ |____|  \____/  |_____|
```

# anthropic-a2ui

> Let Claude generate user interfaces with A2UI in its responses.

`anthropic-a2ui` bridges the A2UI protocol with the Anthropic SDK, enabling
Claude to emit declarative, interactive user interfaces as part of its
natural responses. Instead of returning plain text, Claude can now build
forms, dashboards, product cards, surveys, calendars, configuration panels,
modals, and any other UI composed from the A2UI component catalog. Payloads
are repaired when possible and checked against the active catalog before they
are handed to an A2UI-compatible renderer (Lit, React, Angular, Flutter,
SwiftUI, and more).

The package does not wrap or replace the Anthropic SDK. It composes with
it: you use `anthropic` directly and plug in the A2UI pieces where they add
value. The system prompt, the tool definition, the stream parser, the
validator, the automatic repair layer, and the retry-with-feedback loop are
all designed to be transparent and composable.

---

## How it works

When a user asks Claude for an interface — "make me a contact form", "show
me a shopping cart", "build me a weather panel" — the following happens
behind the scenes:

1. **Prompt injection**: `ClaudeA2uiPromptBuilder` constructs a system
   prompt containing the A2UI JSON Schema, few-shot examples, the list of
   59 valid icon names, and the 14 catalog functions. Claude receives this
   as its system context and knows how to speak A2UI.

2. **Tool definition**: `create_a2ui_tool` produces a tool definition
   (`send_a2ui_json_to_client`) that Claude can invoke to deliver UI. The
   schema is wrapped to comply with Anthropic's constraint against
   `oneOf`/`allOf`/`anyOf` at the top level of `input_schema`.

3. **Streaming parse**: As Claude streams its response, `ClaudeStreamParser`
   intercepts tool-use events (or `<a2ui-json>` text blocks) and emits
   `ResponsePart` objects containing either conversational text or a
   complete A2UI payload.

4. **Automatic repair**: Before validation, the payload passes through five
   repair functions that fix known issues silently — invalid icon names,
   non-existent catalog functions, orphaned components, ambiguous
   DateTimeInput formats, and dynamic child lists in Row/Column.

5. **Validation**: The repaired payload is checked against the A2UI schema
   and its topology. If a tool call fails that validation, the error is fed
   back to Claude using the original tool-use ID, and Claude can correct
   itself on the next attempt (up to `max_retries`).

6. **Delivery**: The validated payload is wrapped in an `A2uiPart` with
   MIME `application/a2ui+json`, ready to be sent to any A2UI renderer.

The user never mentions A2UI, components, functions, or schemas. They just
talk naturally, and Claude responds with a working interface.

---

## Installation

```bash
uv add anthropic-a2ui
# or
pip install anthropic-a2ui
```

Requires `ANTHROPIC_API_KEY` in the environment.

---

## Security boundary

An A2UI payload is model output and must be treated as untrusted input. This
package validates protocol structure and performs narrowly defined repairs;
it does not sanitize strings, authorize actions, fetch URLs, or make a
renderer safe.

The application that renders the payload must escape text, reject raw HTML
and executable expressions, apply URL protocol and host allowlists, constrain
resource and render sizes, and use an appropriate CSP or sandbox for web
views. Do not grant actions from an A2UI payload access to credentials or
privileged server operations without application-side authorization.

---

## Quick start

The simplest way to use the package is `generate_a2ui`. One function call
handles everything: prompt construction, Claude invocation, streaming,
parsing, repair, validation, and retry-on-failure.

```python
import anthropic
from anthropic_a2ui import generate_a2ui

client = anthropic.Anthropic()

result = generate_a2ui(
    client,
    "make me a registration form with name, email, and a submit button",
    model="claude-haiku-4-5-20251001",
    log_repairs=True,
)

if result.success:
    # result.a2ui_json passed structural validation for the active catalog.
    # Apply your renderer's own content and action security policy.
    render(result.a2ui_json)
    for repair in result.repairs:
        print(f"Repaired: {repair}")
else:
    print(f"Failed after {result.attempts} attempts: {result.error}")
```

An async version is also available for integration with async web
frameworks like FastAPI or Starlette:

```python
import anthropic
from anthropic_a2ui import generate_a2ui_async

client = anthropic.AsyncAnthropic()
result = await generate_a2ui_async(
    client,
    "make me a registration form",
    model="claude-haiku-4-5-20251001",
)
```

---

## Usage modes

The package offers four complementary ways to generate A2UI, depending on
the level of control and the use case.

### Mode 1: Single call with `generate_a2ui`

Best for one-shot UI generation. The user asks for something, Claude
responds with a complete A2UI payload. If the payload is invalid, the
package automatically feeds the validation error back to Claude and
retries (up to `max_retries` times, default 2). Claude corrects itself
and resubmits.

```python
result = generate_a2ui(
    client,
    "make me a contact form with name, email, subject, and message",
    model="claude-opus-4-8",
    max_retries=3,
)

if result.success:
    render(result.a2ui_json)
```

Key parameters:

- `builder`: custom `ClaudeA2uiPromptBuilder` (defaults to v0.9 Basic
  Catalog).
- `model`: any Claude model that supports tool use.
- `max_tokens`: per-attempt token budget (default 8192).
- `max_retries`: how many times to retry on validation failure (default 2).
- `use_cache`: enable prompt caching to reduce cost ~80% on repeated calls
  (default `True`).
- `log_repairs`: record what was repaired for debugging (default `False`).

### Mode 2: Multi-turn conversation with `A2uiConversation`

Best for iterative UI design. The user starts with a request, then refines
it across multiple turns: "make me a form" -> "add a phone field" ->
"change the button color to blue". Claude maintains the full conversation
context and generates a new A2UI payload with all changes applied in each
turn.

```python
import anthropic
from anthropic_a2ui import A2uiConversation

client = anthropic.Anthropic()
conv = A2uiConversation(client, model="claude-haiku-4-5-20251001")

# Turn 1: create the initial form
r1 = conv.send("make me a contact form")
# r1.a2ui_json contains the form
# r1.success is True

# Turn 2: add a field
r2 = conv.send("add a phone number field")
# r2.a2ui_json contains the form + phone field

# Turn 3: change the styling
r3 = conv.send("make the submit button red")
# r3.a2ui_json contains the form + phone field + red button

# Access the full conversation history
print(f"Turns: {len(conv.turns)}")
print(f"Last valid A2UI: {conv.last_a2ui_json is not None}")

# Reset to start a new conversation
conv.reset()
```

The async version works identically:

```python
import anthropic
from anthropic_a2ui import A2uiConversationAsync

client = anthropic.AsyncAnthropic()
conv = A2uiConversationAsync(client)

r1 = await conv.send("make me a form")
r2 = await conv.send("add an email field")
```

### Mode 3: Forced JSON with structured outputs

Best when you want pure UI output with no conversational text. This mode
uses Anthropic's `output_config.format` structured output parameter with
`json_schema` to request a parseable JSON envelope. No tools and no tags: just
a structured payload. Anthropic JSON outputs do not accept A2UI's `oneOf`
schema, so the envelope contains `a2ui_json` as a JSON-serialized string;
`parse_json_response` deserializes it and applies strict local A2UI validation.

```python
import anthropic
from anthropic_a2ui import (
    ClaudeA2uiPromptBuilder,
    create_a2ui_output_config,
    parse_json_response,
)

builder = ClaudeA2uiPromptBuilder()
allowed_components = ["Text", "TextField", "Button", "Column"]
catalog = builder.get_catalog(allowed_components=allowed_components)
output_config = create_a2ui_output_config(
    catalog,
    allowed_components=allowed_components,
)

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-6",
    system=builder.build(
        role_description=(
            "You create user interfaces. Serialize the complete A2UI message "
            "array as JSON inside a2ui_json."
        ),
        allowed_components=allowed_components,
    ),
    output_config=output_config,
    max_tokens=8192,
    messages=[{"role": "user", "content": "make me a form"}],
)

# Extract, unwrap, validate, and repair the A2UI payload
a2ui_json = parse_json_response(
    response,
    catalog,
    allowed_components=allowed_components,
)
render(a2ui_json)
```

With `allowed_components` or `allowed_messages`, pass the same restrictions
to `parse_json_response`. Anthropic's schema constrains the outer envelope;
the package enforces the A2UI subset during its local validation step.

### Mode 4: Manual streaming

Best when you need full control over the stream, token by token. You
construct the system prompt, define the tool, and process the stream
yourself. The parser handles unwrapping, repair, and validation.

```python
import anthropic
from anthropic_a2ui import (
    ClaudeA2uiPromptBuilder,
    create_a2ui_tool,
    ClaudeStreamParser,
)

builder = ClaudeA2uiPromptBuilder()
tool = create_a2ui_tool(builder.get_catalog())
parser = ClaudeStreamParser(catalog=builder.get_catalog())

client = anthropic.Anthropic()
with client.messages.stream(
    model="claude-sonnet-4-6",
    system=builder.build(role_description="You create user interfaces."),
    tools=[tool],
    max_tokens=8192,
    messages=[{"role": "user", "content": "make me a form"}],
) as stream:
    for event in stream:
        for part in parser.process_event(event):
            if part.a2ui_json:
                # A complete payload checked against the active catalog
                render(part.a2ui_json)
            if part.text:
                # Conversational text from Claude
                print(part.text, end="")
```

The parser also supports the `<a2ui-json>` tag mode (no tool use), where
Claude embeds the JSON directly in its text response between
`<a2ui-json>` and `</a2ui-json>` tags.

---

## Automatic repairs

Claude is remarkably good at generating valid A2UI, but it occasionally
makes mistakes — especially the smaller models. The package includes five
repair functions that fix these issues transparently before validation, so
the caller never sees a false rejection:

| Repair | What it fixes | Example |
|---|---|---|
| `patch_catalog_schema` | `DateTimeInput.min/max` uses `oneOf` of three date formats, which `jsonschema` rejects as ambiguous | Changes `oneOf` to `anyOf` in the schema |
| `repair_orphans` | Components created by Claude but not connected to the `root` tree | Reconnects orphans as children of the root container |
| `repair_icons` | Icon names that don't exist in the active catalog enum (`cloud`, `sunny`, `trash`, ...) | Maps known aliases to a valid catalog icon; otherwise uses `info` when available |
| `repair_functions` | `FunctionCall` with functions that don't exist in the active catalog (`ternary`, `if`, `switch`) | Replaces with a contextual literal or removes an invalid check without altering valid custom functions |
| `repair_childlists` | Dynamic child lists (`{componentId, path}`) used in `Row` or `Column`, which only accept static string arrays | Converts to a static array of component IDs |

All repairs are enabled by default in `generate_a2ui`, `A2uiConversation`,
and `ClaudeStreamParser`. They can be disabled with `repair=False` for
strict validation.

When `log_repairs=True`, the `RetryResult.repairs` list contains
human-readable descriptions of what was repaired:

```python
result = generate_a2ui(client, "make me a weather panel", log_repairs=True)
for r in result.repairs:
    print(f"Repaired: {r}")
# Repaired: Icon 'sun_icon' substituted with 'info'
# Repaired: Text 'star1' emptied (possible function removed)
```

---

## Prompt caching

The A2UI system prompt is large: it includes the full JSON Schema, few-shot
examples, the list of 59 valid icon names, and the 14 catalog functions.
Sending this on every call would be expensive and slow.

`generate_a2ui` and `A2uiConversation` enable prompt caching by default
(`use_cache=True`). This adds `cache_control: {type: "ephemeral"}` to the
system prompt block, allowing Anthropic to cache it and reduce the cost by
approximately 80% on subsequent calls within the cache window.

To disable caching (for debugging or testing):

```python
result = generate_a2ui(client, "make me a form", use_cache=False)
```

---

## Type safety

The package ships with a `py.typed` marker for typed-editor integrations.
Its own source is checked with Mypy in CI; downstream applications should
still type-check their renderer and action adapters.

---

## Supported versions

A2UI is an evolving protocol. The package supports three versions:

| Version | Catalog | Components | Functions |
|---|---|---|---|
| v0.8 | standard (legacy) | 18 (includes `MultipleChoice`) | 0 |
| v0.9 | basic | 18 (includes `ChoicePicker`) | 14 |
| v0.9 | minimal | 5 (Text, Row, Column, Button, TextField) | 1 (`capitalize`) |
| v0.9.1 | basic | 18 | 14 |

The default is v0.9 with the Basic Catalog. To use a different version or
catalog:

```python
from anthropic_a2ui import ClaudeA2uiPromptBuilder

# v0.8 legacy
builder = ClaudeA2uiPromptBuilder(version="0.8")

# Pruned to specific components (saves tokens)
builder = ClaudeA2uiPromptBuilder()
prompt = builder.build(
    role_description="You create simple forms.",
    allowed_components=["Text", "TextField", "Button"],
)
```

---

## Model verification

The automated suite uses local stream doubles. Release 0.1.3 also verifies
tool use, two-turn conversation state, and structured-output parsing against
`claude-haiku-4-5-20251001`. Model names and capabilities evolve, so run a
credentialed smoke test with the exact model and catalog before production use.

---

## API reference

### High-level functions

- **`generate_a2ui(client, prompt, **kwargs) -> RetryResult`**: one-shot
  generation with retries and caching.
- **`generate_a2ui_async(client, prompt, **kwargs) -> RetryResult`**:
  async version.
- **`A2uiConversation(client, **kwargs)`**: multi-turn conversation.
  `.send(prompt) -> ConversationTurn`, `.reset()`.
- **`A2uiConversationAsync(client, **kwargs)`**: async version.
- **`create_a2ui_output_config(catalog) -> dict`**: `output_config` for
  forced JSON mode. Pair with `parse_json_response(message, catalog)`.
- **`create_a2ui_response_format(catalog) -> dict`**: low-level
  `output_config.format` object for forced JSON mode.

### Building blocks

- **`ClaudeA2uiPromptBuilder(version, catalogs)`**: constructs the system
  prompt. `.build(role_description, ...)` returns the prompt string.
  `.get_catalog()` returns the `A2uiCatalog`.
- **`create_a2ui_tool(catalog, **kwargs) -> dict`**: tool definition for
  Anthropic.
- **`ClaudeStreamParser(catalog, **kwargs)`**: stream parser.
  `.process_event(event) -> list[ResponsePart]`. `.parse_stream(stream)`
  is an iterator shortcut.
- **`validate_tool_input(catalog, input_json, *, repair, strict_integrity)`**:
  validates a payload against the schema and returns the repaired payload.
- **`to_a2ui_part(payload) -> A2uiPart`**: wraps a payload for transport
  with MIME `application/a2ui+json`.
- **`to_a2a_datapart(part)`**: returns the compatible legacy A2A `DataPart`
  when that API is installed, otherwise returns the portable dictionary.

### Repair functions

- **`repair_orphans(payload)`**: reconnects orphaned components.
- **`repair_icons(payload)`**: fixes invalid icon names.
- **`repair_functions(payload)`**: fixes non-existent function calls.
- **`repair_childlists(payload)`**: fixes dynamic child lists in
  Row/Column.
- **`repair_payload(payload, catalog=...)`**: applies the full repair chain
  using the active catalog's icons and functions.
- **`patch_catalog_schema(schema)`**: patches the DateTimeInput schema.
- **`find_orphans(payload) -> list[str]`**: diagnostic, returns orphan IDs.

---

## License

Apache-2.0.
