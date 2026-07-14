"""Definición de la tool ``send_a2ui_json_to_client`` para Anthropic.

Esta pieza expone la tool que Claude puede invocar para entregar UI A2UI.
La definición sigue el formato de Anthropic (``name``, ``description``,
``input_schema``) y se genera a partir del catálogo de A2UI, de modo que el
``input_schema`` es el JSON Schema del protocolo (con los componentes
permitidos si se ha podado el catálogo).

El flujo de uso es:

1. Crear la tool con ``create_a2ui_tool(catalog)``.
2. Pasarla a ``client.messages.stream(..., tools=[tool])``.
3. Cuando Claude la invoque, el ``ClaudeStreamParser`` emite el JSON como
   ``ResponsePart``. Si se quiere validar antes de declarar la llamada como
   éxito, usar ``validate_tool_input(catalog, input_json)``.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from a2ui.schema.catalog import A2uiCatalog

from .prompt_builder import _prune_catalog
from .stream_parser import ClaudeStreamParser

TOOL_NAME = "send_a2ui_json_to_client"
TOOL_DESCRIPTION = (
    "Entrega una respuesta de UI al usuario usando el protocolo A2UI. El "
    "argumento ``a2ui_json`` debe ser una lista de mensajes A2UI válidos "
    "(createSurface, updateComponents, updateDataModel, deleteSurface) que "
    "conformen el esquema del catálogo activo. La respuesta se renderiza "
    "directamente en la superficie del cliente."
)


def create_a2ui_tool(
    catalog: A2uiCatalog,
    *,
    name: str = TOOL_NAME,
    description: str = TOOL_DESCRIPTION,
    allowed_components: Optional[list[str]] = None,
    allowed_messages: Optional[list[str]] = None,
) -> dict[str, Any]:
  """Crea la definición de tool para Anthropic a partir de un catálogo A2UI.

  Args:
    catalog: ``A2uiCatalog`` (por ejemplo ``builder.get_catalog()``). Si se
      quiere poda, usar ``catalog.with_pruning(...)`` antes o pasar
      ``allowed_components``/``allowed_messages`` aquí.
    name: Nombre de la tool. Por defecto ``send_a2ui_json_to_client``.
    description: Descripción de la tool para el prompt de Claude.
    allowed_components: Subconjunto de componentes para podar el esquema. Si
      no es ``None``, se llama a ``catalog.with_pruning``.
    allowed_messages: Subconjunto de tipos de mensaje.

  Returns:
    Dict en el formato de Anthropic:
    ``{"name": ..., "description": ..., "input_schema": {...}}``.

  Raises:
    ValueError: Si el catálogo no tiene esquema ``s2c``.

  Nota sobre el esquema:
    La API de Anthropic no soporta ``oneOf``/``allOf``/``anyOf`` en el nivel
    superior de ``input_schema``. El esquema ``s2c`` de A2UI usa ``oneOf``
    arriba del todo para discriminar entre tipos de mensaje. Por eso se
    envuelve dentro de un objeto ``{"a2ui_json": [mensaje, ...]}`` donde el
    ``oneOf`` queda dentro de ``items``, no en la raíz. El
    ``ClaudeStreamParser`` desenvuelve ``a2ui_json`` automáticamente.
  """
  catalog = _prune_catalog(
      catalog,
      allowed_components=allowed_components,
      allowed_messages=allowed_messages,
  )
  s2c = copy.deepcopy(catalog.s2c_schema)
  if not s2c:
    raise ValueError("El catálogo no tiene esquema server_to_client.")
  _add_catalog_constraints(s2c, catalog)
  # Envolver en un objeto con propiedad a2ui_json (array de mensajes).
  # Esto evita oneOf/allOf/anyOf en el nivel superior, que Anthropic rechaza.
  wrapped_schema = {
      "type": "object",
      "properties": {
          "a2ui_json": {
              "type": "array",
              "minItems": 1,
              "items": s2c,
              "description": (
                  "Lista de mensajes A2UI (createSurface, updateComponents, "
                  "updateDataModel, deleteSurface). Cada mensaje debe "
                  "conformar el esquema del catálogo activo."
              ),
          }
      },
      "required": ["a2ui_json"],
      "additionalProperties": False,
  }
  return {
      "name": name,
      "description": description,
      "input_schema": wrapped_schema,
  }


def _add_catalog_constraints(s2c: dict[str, Any], catalog: A2uiCatalog) -> None:
  """Incluye en la tool los componentes permitidos por el catalogo podado."""
  component_names = sorted(catalog.catalog_schema.get("components", {}))
  if not component_names:
    return

  if catalog.version == "0.8":
    try:
      component_wrapper = s2c["properties"]["surfaceUpdate"]["properties"][
          "components"
      ]["items"]["properties"]["component"]
    except (KeyError, TypeError):
      return
    component_wrapper["propertyNames"] = {"enum": component_names}
    component_wrapper["minProperties"] = 1
    component_wrapper["maxProperties"] = 1
    return

  try:
    items = s2c["$defs"]["UpdateComponentsMessage"]["properties"]["updateComponents"][
        "properties"
    ]["components"]["items"]
  except (KeyError, TypeError):
    return
  constraint = {
      "type": "object",
      "properties": {
          "component": {"type": "string", "enum": component_names},
      },
      "required": ["component"],
  }
  s2c["$defs"]["UpdateComponentsMessage"]["properties"]["updateComponents"][
      "properties"
  ]["components"]["items"] = {"allOf": [items, constraint]}


def validate_tool_input(
    catalog: A2uiCatalog,
    input_json: Any,
    *,
    strict_integrity: bool = True,
    repair: bool = True,
) -> list[dict[str, Any]]:
  """Valida el JSON que Claude pasa como argumento a la tool A2UI.

  Args:
    catalog: ``A2uiCatalog`` con su validador.
    input_json: La lista que Claude devolvio como ``a2ui_json``.
    strict_integrity: Si aplicar comprobaciones de integridad (IDs unicos,
      root alcanzable, sin ciclos).
    repair: Si reparar problemas conocidos antes de validar. Por defecto
      ``True``. Aplica cuatro reparaciones:

      1. **``DateTimeInput.min/max``**: parchea el schema del catalogo
         cambiando ``oneOf`` por ``anyOf`` (bug del schema de A2UI).
      2. **Componentes huerfanos**: reconecta componentes no alcanzables
         desde ``root``.
      3. **Iconos invalidos**: mapea nombres de iconos inventados por el
         modelo a iconos validos del catalogo.
      4. **Funciones inexistentes**: sustituye ``FunctionCall`` con
         funciones que no existen en el catalogo por valores literales.

      Si ``repair=False``, valida contra el schema original sin
      reparaciones (mas estricto).

  Raises:
    Exception: La excepcion que lance ``A2uiValidator.validate``.

  Returns:
    La lista validada. Si ``repair=True``, devuelve la copia reparada que se
    valido, no el payload original.
  """
  if not isinstance(input_json, list):
    raise ValueError("a2ui_json debe ser una lista de mensajes A2UI")
  if not input_json:
    raise ValueError("a2ui_json debe contener al menos un mensaje A2UI")

  payload = input_json
  if repair:
    from .repair import repair_payload

    payload = repair_payload(payload, catalog=catalog)

    # Parchear el schema del catalogo para DateTimeInput
    from .repair import patch_catalog_schema

    patched_schema = patch_catalog_schema(catalog.catalog_schema)
    # Crear un validador con el schema parcheado
    _validate_with_patched_schema(
        catalog, patched_schema, payload, strict_integrity=strict_integrity
    )
  else:
    catalog.validator.validate(payload, strict_integrity=strict_integrity)
  return payload


def _validate_with_patched_schema(
    catalog: A2uiCatalog,
    patched_catalog_schema: dict[str, Any],
    input_json: Any,
    *,
    strict_integrity: bool,
) -> None:
  """Valida usando un schema de catálogo parcheado.

  Construye un ``A2uiValidator`` temporal con el schema parcheado para que
  la validación de componentes use ``anyOf`` en vez de ``oneOf`` en
  ``DateTimeInput.min/max``.
  """
  import dataclasses

  from a2ui.schema.validator import A2uiValidator

  # Crear un catálogo temporal con el schema parcheado.
  # A2uiCatalog es un frozen dataclass, así que usamos dataclasses.replace.
  temp_catalog = dataclasses.replace(catalog, catalog_schema=patched_catalog_schema)
  temp_validator = A2uiValidator(temp_catalog)
  temp_validator.validate(input_json, strict_integrity=strict_integrity)


def make_parser_for_tool(
    catalog: A2uiCatalog,
    *,
    strict: bool = True,
) -> ClaudeStreamParser:
  """Atajo: crea un ``ClaudeStreamParser`` configurado para la tool.

  Útil para evitar repetir la configuración del catálogo/validador cuando
  se usa el modo tool. El parser resultante valida cada tool use contra el
  esquema al cerrar el bloque.

  Args:
    catalog: ``A2uiCatalog``.
    strict: Si validar estrictamente el JSON de tool use.

  Returns:
    ``ClaudeStreamParser`` listo para consumir el stream.
  """
  return ClaudeStreamParser(catalog=catalog, strict_tool_validation=strict)
