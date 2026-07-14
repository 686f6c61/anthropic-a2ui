# Audit 0.1.2

Date: 2026-07-14

## Scope and conclusion

This audit reviewed the public Python API, stream and retry contract, A2UI
schema validation, repair logic, package metadata, CI, and release workflow.
The 0.1.2 changes close the defects that could make the advertised high-level
generation path return prose after a failed tool payload, accept an empty UI,
or make component restrictions ineffective.

## Fixed in 0.1.2

- Retry feedback now preserves the real Anthropic tool-use ID and its raw
  input. A validation failure is sent back as a matching `tool_result`.
- Network and SDK failures stop locally instead of being presented to Claude
  as repair instructions.
- `allowed_components` and `allowed_messages` constrain prompt, catalog, tool
  schema, structured-output schema, parser, and validator consistently.
- The parser ignores unrelated tools, enforces a bounded input buffer, and
  rejects empty payloads.
- Automatic repairs read valid icons and functions from the active catalog;
  custom catalogs are not rewritten with Basic Catalog assumptions.
- Orphan repair avoids generated-ID collisions and can make a non-container
  root reachable without discarding components.
- Optional A2A import handling no longer masks runtime failures from an
  installed dependency.

## Verification performed

- 635 unit and regression tests on Python 3.10, 3.11, 3.12, and 3.13.
- Formatting with Pyink, linting with Ruff, and type checking with Mypy.
- Package build and Twine metadata validation.
- Dependency vulnerability scan with `pip-audit`.
- Fresh installation of the PyPI artifact after publication.

## Remaining operational risks

- The development-only formatter Pyink 25.12.0 pins Black 25.12.0.
  `pip-audit` reports PYSEC-2026-2120 and PYSEC-2026-2121 for that transitive
  formatter dependency; the fixes begin at Black 26.3.0, but no compatible
  Pyink release is available. It is not included in the published runtime
  dependencies, but CI runs it on pull-request source and should apply CPU
  limits until Pyink publishes an update.
- Validation proves protocol shape and selected topology rules. It is not a
  renderer security control. Renderers must escape content, sandbox web views,
  restrict URLs and actions, and enforce resource limits.
- Structured output mode is not live-tested in CI because it needs a provider
  credential. A full A2UI schema can exceed a model/API structured-schema
  limit; verify the selected model before enabling that mode in production.
- The release does not claim a live model success rate. The repository suite
  is deterministic and tests client behavior with Anthropic stream doubles.
- `a2ui-agent-sdk` is intentionally constrained below 0.3 because the newer
  line requires Python 3.14, while this package supports Python 3.10 through
  3.13.
