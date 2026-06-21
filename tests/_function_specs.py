"""Especificaciones de payloads A2UI válidos por cada función del catálogo.

A2UI define 15 funciones únicas en total: 14 del Basic Catalog v0.9
(``required``, ``regex``, ``length``, ``numeric``, ``email``,
``formatString``, ``formatNumber``, ``formatCurrency``, ``formatDate``,
``pluralize``, ``openUrl``, ``and``, ``or``, ``not``) y ``capitalize`` del
catálogo minimal v0.9.

Las funciones se usan en tres contextos:

1. **Checks de validación** (``checks`` en TextField, CheckBox, etc.):
   ``required``, ``regex``, ``length``, ``numeric``, ``email``, ``and``,
   ``or``, ``not``. Retornan boolean.
2. **Texto dinámico** (``text`` de Text con FunctionCall):
   ``formatString``, ``formatNumber``, ``formatCurrency``, ``formatDate``,
   ``pluralize``, ``capitalize``. Retornan string.
3. **Acción de botón** (``action.functionCall``): ``openUrl``. Retorna void.

Cada spec define un payload mínimo que usa la función en su contexto natural.
"""

from __future__ import annotations

from typing import Any

from ._a2ui_specs import CATALOG_ID, MINIMAL_CATALOG_ID

# --- Funciones del Basic Catalog v0.9 (14) ------------------------
#
# Cada entrada: (name, context, payload_builder)
# context indica dónde se usa: "check", "text" o "action"

BASIC_FUNCTION_SPECS: list[tuple[str, str, list[dict[str, Any]]]] = [
    # --- Funciones de validación (checks) ---
    (
        "required",
        "check",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "TextField",
                        "label": "Email",
                        "value": {"path": "/email"},
                        "checks": [{
                            "condition": {
                                "call": "required",
                                "args": {"value": {"path": "/email"}},
                                "returnType": "boolean",
                            },
                            "message": "Campo obligatorio",
                        }],
                    }],
                },
            },
        ],
    ),
    (
        "regex",
        "check",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "TextField",
                        "label": "Código",
                        "value": {"path": "/code"},
                        "checks": [{
                            "condition": {
                                "call": "regex",
                                "args": {
                                    "value": {"path": "/code"},
                                    "pattern": "^[0-9]+$",
                                },
                                "returnType": "boolean",
                            },
                            "message": "Solo dígitos",
                        }],
                    }],
                },
            },
        ],
    ),
    (
        "length",
        "check",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "TextField",
                        "label": "Nombre",
                        "value": {"path": "/name"},
                        "checks": [{
                            "condition": {
                                "call": "length",
                                "args": {"value": {"path": "/name"}, "min": 2},
                                "returnType": "boolean",
                            },
                            "message": "Mínimo 2 caracteres",
                        }],
                    }],
                },
            },
        ],
    ),
    (
        "numeric",
        "check",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "TextField",
                        "label": "Edad",
                        "value": {"path": "/age"},
                        "variant": "number",
                        "checks": [{
                            "condition": {
                                "call": "numeric",
                                "args": {
                                    "value": {"path": "/age"},
                                    "min": 0,
                                    "max": 120,
                                },
                                "returnType": "boolean",
                            },
                            "message": "Edad inválida",
                        }],
                    }],
                },
            },
        ],
    ),
    (
        "email",
        "check",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "TextField",
                        "label": "Email",
                        "value": {"path": "/email"},
                        "checks": [{
                            "condition": {
                                "call": "email",
                                "args": {"value": {"path": "/email"}},
                                "returnType": "boolean",
                            },
                            "message": "Email inválido",
                        }],
                    }],
                },
            },
        ],
    ),
    # --- Funciones de formato (text dinámico) ---
    (
        "formatString",
        "text",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "Text",
                        "text": {
                            "call": "formatString",
                            "args": {"value": "Hola ${/name}"},
                            "returnType": "string",
                        },
                    }],
                },
            },
        ],
    ),
    (
        "formatNumber",
        "text",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "Text",
                        "text": {
                            "call": "formatNumber",
                            "args": {"value": 1234.5, "decimals": 2},
                            "returnType": "string",
                        },
                    }],
                },
            },
        ],
    ),
    (
        "formatCurrency",
        "text",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "Text",
                        "text": {
                            "call": "formatCurrency",
                            "args": {"value": 99.99, "currency": "EUR"},
                            "returnType": "string",
                        },
                    }],
                },
            },
        ],
    ),
    (
        "formatDate",
        "text",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "Text",
                        "text": {
                            "call": "formatDate",
                            "args": {"value": "2026-01-01", "format": "yyyy-MM-dd"},
                            "returnType": "string",
                        },
                    }],
                },
            },
        ],
    ),
    (
        "pluralize",
        "text",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "Text",
                        "text": {
                            "call": "pluralize",
                            "args": {"value": 1, "one": "item", "other": "items"},
                            "returnType": "string",
                        },
                    }],
                },
            },
        ],
    ),
    # --- Función de acción (openUrl en Button) ---
    (
        "openUrl",
        "action",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [
                        {
                            "id": "root",
                            "component": "Button",
                            "child": "btn-label",
                            "action": {
                                "functionCall": {
                                    "call": "openUrl",
                                    "args": {"url": "https://example.com"},
                                    "returnType": "void",
                                }
                            },
                        },
                        {"id": "btn-label", "component": "Text", "text": "Abrir"},
                    ],
                },
            },
        ],
    ),
    # --- Funciones lógicas (checks anidados) ---
    (
        "and",
        "check",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "TextField",
                        "label": "Campo",
                        "value": {"path": "/val"},
                        "checks": [{
                            "condition": {
                                "call": "and",
                                "args": {"values": [{"path": "/a"}, {"path": "/b"}]},
                                "returnType": "boolean",
                            },
                            "message": "Ambos deben ser true",
                        }],
                    }],
                },
            },
        ],
    ),
    (
        "or",
        "check",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "TextField",
                        "label": "Campo",
                        "value": {"path": "/val"},
                        "checks": [{
                            "condition": {
                                "call": "or",
                                "args": {"values": [{"path": "/a"}, {"path": "/b"}]},
                                "returnType": "boolean",
                            },
                            "message": "Al menos uno debe ser true",
                        }],
                    }],
                },
            },
        ],
    ),
    (
        "not",
        "check",
        [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s", "catalogId": CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s",
                    "components": [{
                        "id": "root",
                        "component": "TextField",
                        "label": "Campo",
                        "value": {"path": "/val"},
                        "checks": [{
                            "condition": {
                                "call": "not",
                                "args": {"value": {"path": "/a"}},
                                "returnType": "boolean",
                            },
                            "message": "Debe ser false",
                        }],
                    }],
                },
            },
        ],
    ),
]


# --- capitalize (función exclusiva del minimal v0.9) ---------------

CAPITALIZE_SPEC: tuple[str, str, list[dict[str, Any]]] = (
    "capitalize",
    "text",
    [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "s", "catalogId": MINIMAL_CATALOG_ID},
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
    ],
)


def all_function_payloads() -> list[tuple[str, str, list[dict[str, Any]]]]:
  """Devuelve ``[(name, context, payload), ...]`` para las 15 funciones.

  Las 14 del Basic v0.9 se validan contra el catálogo basic; ``capitalize``
  se valida contra el minimal.
  """
  return [(name, ctx, payload) for name, ctx, payload in BASIC_FUNCTION_SPECS] + [
      (CAPITALIZE_SPEC[0], CAPITALIZE_SPEC[1], CAPITALIZE_SPEC[2])
  ]


def basic_function_payloads() -> list[tuple[str, str, list[dict[str, Any]]]]:
  """Solo las 14 funciones del Basic v0.9."""
  return [(name, ctx, payload) for name, ctx, payload in BASIC_FUNCTION_SPECS]
