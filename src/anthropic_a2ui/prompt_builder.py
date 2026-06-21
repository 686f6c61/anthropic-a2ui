"""Generación del system prompt para que Claude emita respuestas A2UI.

Esta pieza delega en ``A2uiSchemaManager`` de ``a2ui-agent-sdk`` para montar
el esquema del catálogo y los ejemplos few-shot, y expone una API pensada
para el flujo de Anthropic: construir el prompt, pasar a ``system`` de
``client.messages.stream(...)``, y opcionalmente podar componentes para
ahorrar tokens.

El paquete no redefine el formato del prompt; el ``A2uiSchemaManager`` es la
fuente canónica del protocolo. Aquí solo se adapta el punto de entrada y se
ofrece conveniencia (defaults razonables, validación de versiones soportadas).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.catalog import CatalogConfig
from a2ui.schema.manager import A2uiSchemaManager

# Versiones de protocolo que a2ui-agent-sdk 0.2.x soporta. Se mantiene aquí
# para dar errores claros antes de llegar al A2uiSchemaManager (que lanza un
# ValueError genérico).
SUPPORTED_VERSIONS = ("0.8", "0.9", "0.9.1")
DEFAULT_VERSION = "0.9"


class ClaudeA2uiPromptBuilder:
  """Construye el system prompt para que Claude genere respuestas A2UI.

  Envuelve a ``A2uiSchemaManager`` con defaults orientados a Anthropic: el
  rol del asistente, descripción del flujo y activación de esquema +
  ejemplos. Permite reutilizar una instancia para varias llamamas y podar el
  catálogo a un subconjunto de componentes para reducir tokens.

  Attributes:
    version: Versión del protocolo A2UI (``"0.9"`` por defecto).
    catalogs: Lista de ``CatalogConfig`` activos.
    manager: El ``A2uiSchemaManager`` subyacente, expuesto para uso avanzado.

  Example:
    ```python
    builder = ClaudeA2uiPromptBuilder()
    system = builder.build(role_description="Construye formularios de contacto.")
    # system -> string listo para pasar a client.messages.stream(system=system)
    ```
  """

  def __init__(
      self,
      catalogs: Optional[list[CatalogConfig]] = None,
      version: str = DEFAULT_VERSION,
      accepts_inline_catalogs: bool = False,
      schema_modifiers: Optional[
          list[Callable[[dict[str, Any]], dict[str, Any]]]
      ] = None,
  ) -> None:
    """Inicializa el builder.

    Args:
      catalogs: Catálogos de componentes. Si es ``None`` se usa el
        ``BasicCatalog`` (Button, Text, TextField, etc.) bundled en
        ``a2ui-agent-sdk``.
      version: Versión del protocolo. Debe ser una de
        ``SUPPORTED_VERSIONS``.
      accepts_inline_catalogs: Si el cliente acepta catálogos inline.
      schema_modifiers: Funciones para modificar el esquema antes de
        inyectarlo en el prompt (caso avanzado).

    Raises:
      ValueError: Si ``version`` no está en ``SUPPORTED_VERSIONS``.
    """
    if version not in SUPPORTED_VERSIONS:
      raise ValueError(
          f"Versión no soportada: {version!r}. Versiones válidas: {SUPPORTED_VERSIONS}"
      )
    self.version = version
    if catalogs is None:
      catalogs = [BasicCatalog.get_config(version=version)]
    self.catalogs = list(catalogs)
    self.manager = A2uiSchemaManager(
        version=version,
        catalogs=self.catalogs,
        accepts_inline_catalogs=accepts_inline_catalogs,
        schema_modifiers=schema_modifiers,
    )

  def build(
      self,
      role_description: str,
      workflow_description: str = "",
      ui_description: str = "",
      allowed_components: Optional[list[str]] = None,
      allowed_messages: Optional[list[str]] = None,
      include_schema: bool = True,
      include_examples: bool = True,
      validate_examples: bool = False,
      include_icon_list: bool = True,
      include_function_list: bool = True,
  ) -> str:
    """Genera el system prompt listo para pasar a Anthropic.

    Args:
      role_description: Descripcion del rol del agente (inyecta al inicio).
      workflow_description: Descripcion del flujo de trabajo (opcional).
      ui_description: Descripcion extra de la UI (opcional).
      allowed_components: Subconjunto de nombres de componentes que el
        agente puede usar. Si es ``None``, todos los del catalogo.
      allowed_messages: Subconjunto de tipos de mensaje.
      include_schema: Si incluir el JSON Schema en el prompt.
      include_examples: Si incluir ejemplos few-shot.
      validate_examples: Si validar los ejemplos contra el esquema.
      include_icon_list: Si anadir la lista de iconos validos al final del
        prompt. Evita que Claude invente nombres de iconos no permitidos.
        Por defecto ``True``.

    Returns:
      Cadena con el system prompt completo.
    """
    prompt = self.manager.generate_system_prompt(
        role_description=role_description,
        workflow_description=workflow_description,
        ui_description=ui_description,
        client_ui_capabilities=None,
        allowed_components=allowed_components,
        allowed_messages=allowed_messages,
        include_schema=include_schema,
        include_examples=include_examples,
        validate_examples=validate_examples,
    )
    if include_icon_list:
      icons = _extract_valid_icons(self.get_catalog())
      if icons:
        prompt += (
            "\n\n--- ICONOS VALIDOS ---\n"
            "El componente Icon solo acepta estos nombres (no inventes "
            "otros):\n"
            + ", ".join(icons)
            + "\n"
        )
    if include_function_list:
      functions = _extract_valid_functions(self.get_catalog())
      if functions:
        prompt += (
            "\n\n--- FUNCIONES VALIDAS ---\n"
            "Las unicas funciones que puedes usar en FunctionCall son estas "
            "(no inventes otras como ternary, if, switch, etc.):\n"
            + ", ".join(functions)
            + "\n"
        )
    return prompt

  def get_catalog(self) -> Any:
    """Devuelve el ``A2uiCatalog`` seleccionado (con poda aplicada si la hubo).

    Expuesto para que el caller pueda obtener un validador o podar el
    catálogo de forma independiente al prompt.
    """
    return self.manager.get_selected_catalog()

  def get_validator(self) -> Any:
    """Atajo para obtener el ``A2uiValidator`` del catalogo seleccionado."""
    return self.get_catalog().validator


def _extract_valid_icons(catalog: Any) -> list[str]:
  """Extrae la lista de iconos validos del catalogo.

  Recorre el schema del componente ``Icon`` y devuelve los valores del
  ``enum`` en su propiedad ``name``.
  """
  components = catalog.catalog_schema.get("components", {})
  icon_def = components.get("Icon")
  if not icon_def:
    return []
  for sub in icon_def.get("allOf", []):
    if "properties" not in sub:
      continue
    name_prop = sub["properties"].get("name")
    if not name_prop:
      continue
    for branch in name_prop.get("oneOf", []):
      if "enum" in branch:
        return branch["enum"]
    if "enum" in name_prop:
      return name_prop["enum"]
  return []


def _extract_valid_functions(catalog: Any) -> list[str]:
  """Extrae la lista de funciones validas del catalogo.

  Devuelve los nombres de las funciones definidas en el catalogo, que son
  las unicas que se pueden usar en ``FunctionCall``.
  """
  functions = catalog.catalog_schema.get("functions", {})
  return list(functions.keys())
