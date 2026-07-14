"""anthropic-a2ui: integración de A2UI con el SDK de Anthropic.

Paquete que compone ``a2ui-agent-sdk`` con ``anthropic`` para que Claude
genere respuestas conformes al protocolo A2UI. No envuelve el SDK de
Anthropic: se usa ``anthropic`` directamente y se plugan las piezas de A2UI.

API pública:

- ``ClaudeA2uiPromptBuilder``: genera el system prompt con esquema + ejemplos.
- ``create_a2ui_tool``: define la tool ``send_a2ui_json_to_client``.
- ``ClaudeStreamParser``: parsea el stream de Anthropic y emite
  ``ResponsePart`` de A2UI.
- ``to_a2ui_part``, ``A2uiPart``, ``MIME_A2UI``: helpers de transporte.
- ``SUPPORTED_VERSIONS``, ``DEFAULT_VERSION``: constantes del protocolo.
"""

from __future__ import annotations

from .parts import (
    A2uiPart,
    MIME_A2UI,
    parse_a2ui_part_json,
    to_a2a_datapart,
    to_a2ui_part,
)
from .prompt_builder import (
    DEFAULT_VERSION,
    SUPPORTED_VERSIONS,
    ClaudeA2uiPromptBuilder,
)
from .repair import (
    find_orphans,
    patch_catalog_schema,
    repair_childlists,
    repair_functions,
    repair_icons,
    repair_orphans,
    repair_payload,
)
from .retry import (
    A2uiConversation,
    A2uiConversationAsync,
    ConversationTurn,
    RetryResult,
    create_a2ui_output_config,
    create_a2ui_response_format,
    generate_a2ui,
    generate_a2ui_async,
    parse_json_response,
)
from .stream_parser import ClaudeStreamParser
from .tool import (
    TOOL_DESCRIPTION,
    TOOL_NAME,
    create_a2ui_tool,
    make_parser_for_tool,
    validate_tool_input,
)
from .version import __version__

__all__ = [
    "A2uiConversation",
    "A2uiConversationAsync",
    "A2uiPart",
    "ConversationTurn",
    "MIME_A2UI",
    "RetryResult",
    "SUPPORTED_VERSIONS",
    "DEFAULT_VERSION",
    "TOOL_NAME",
    "TOOL_DESCRIPTION",
    "ClaudeA2uiPromptBuilder",
    "ClaudeStreamParser",
    "create_a2ui_response_format",
    "create_a2ui_output_config",
    "create_a2ui_tool",
    "find_orphans",
    "generate_a2ui",
    "generate_a2ui_async",
    "make_parser_for_tool",
    "parse_a2ui_part_json",
    "parse_json_response",
    "patch_catalog_schema",
    "repair_childlists",
    "repair_functions",
    "repair_icons",
    "repair_orphans",
    "repair_payload",
    "to_a2a_datapart",
    "to_a2ui_part",
    "validate_tool_input",
    "__version__",
]
