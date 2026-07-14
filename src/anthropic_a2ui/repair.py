"""Reparacion de payloads A2UI antes de la validacion.

A2UI tiene varios problemas conocidos que provocan que payloads correctos
falen la validacion o que los modelos generen JSON invalido:

1. **``DateTimeInput.min/max`` con ``oneOf`` ambiguo**: el schema usa
   ``oneOf`` de tres formatos (``date``, ``time``, ``date-time``) sin
   ``type: string`` en cada rama. ``jsonschema`` rechaza valores validos
   bajo varios formatos a la vez porque ``oneOf`` exige exactamente uno.
   Solucion: parchear el schema cambiando ``oneOf`` por ``anyOf``.

2. **Componentes huerfanos**: los modelos a veces crean componentes que no
   estan referenciados desde el arbol ``root``. ``repair_orphans`` los
   detecta y los reconecta al ``root``.

3. **Iconos invalidos**: los modelos inventan nombres de iconos que no
   estan en el enum del catalogo (``cloud``, ``sunny``, ``rain``...).
   ``repair_icons`` mapea los mas comunes a iconos validos y sustituye
   los desconocidos por ``info``.

4. **Funciones inexistentes**: los modelos a veces usan funciones que no
   existen en el catalogo (``ternary``, ``if``...).
   ``repair_functions`` elimina los ``FunctionCall`` con funciones
   invalidas y los sustituye por un valor literal.

Ambas reparaciones son transparentes: el payload sigue siendo A2UI valido
y renderizable. Se aplican en ``validate_tool_input`` cuando se pasa
``repair=True`` (por defecto).
"""

from __future__ import annotations

import copy
from typing import Any, Optional


def patch_catalog_schema(catalog_schema: dict[str, Any]) -> dict[str, Any]:
  """Parchea el schema del catálogo para corregir el ``oneOf`` ambiguo.

  El ``DateTimeInput`` define ``min`` y ``max`` con un ``oneOf`` de tres
  formatos (``date``, ``time``, ``date-time``) dentro de un ``if/then``.
  Como las tres ramas no declaran ``type: string``, un valor como
  ``"2025-01-01"`` es válido bajo las tres, y ``oneOf`` exige que solo sea
  válido bajo una. Cambiar ``oneOf`` por ``anyOf`` permite que el valor sea
  válido bajo varios formatos.

  Args:
    catalog_schema: El ``catalog_schema`` de un ``A2uiCatalog`` (dict).

  Returns:
    Una copia profunda del schema con ``oneOf`` cambiado a ``anyOf`` en
    ``DateTimeInput.min`` y ``DateTimeInput.max``.
  """
  patched = copy.deepcopy(catalog_schema)
  components = patched.get("components", {})
  dti = components.get("DateTimeInput")
  if not dti:
    return patched
  for sub in dti.get("allOf", []):
    if "properties" not in sub:
      continue
    for prop_name in ("min", "max"):
      prop = sub["properties"].get(prop_name)
      if not prop:
        continue
      for all_of_entry in prop.get("allOf", []):
        then_block = all_of_entry.get("then")
        if not then_block:
          continue
        if "oneOf" in then_block:
          then_block["anyOf"] = then_block.pop("oneOf")
  return patched


def repair_orphans(
    payload: list[dict[str, Any]],
    *,
    surface_id: Optional[str] = None,
    repair_log: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
  """Repara componentes huérfanos en un payload A2UI.

  Un componente huérfano es aquel que está en ``updateComponents`` pero no
  es alcanzable desde ``root`` (no está referenciado por ningún componente
  del árbol). La reparación:

  1. Construye el grafo de referencias desde ``root``.
  2. Identifica componentes no alcanzables.
  3. Si el ``root`` es un contenedor (``Column``, ``Row``, ``List``),
     añade los huérfanos como hijos adicionales.
  4. Si no, envuelve el ``root`` original en un ``Column`` con los
     huérfanos como hijos adicionales.

  Args:
    payload: Lista de mensajes A2UI.
    surface_id: ID de la superficie a reparar. Si es ``None``, se reparan
      todas las superficies.
    repair_log: Lista opcional a la que se anaden descripciones exactas de
      los cambios aplicados.

  Returns:
    El payload reparado (copia profunda). Si no hay huérfanos, devuelve
    el payload sin cambios.
  """
  patched = copy.deepcopy(payload)

  for msg in patched:
    if "updateComponents" not in msg:
      continue
    uc = msg["updateComponents"]
    sid = uc.get("surfaceId", "")
    if surface_id is not None and sid != surface_id:
      continue

    components = uc.get("components", [])
    if not components:
      continue

    # Encontrar root
    root = None
    comp_map: dict[str, dict[str, Any]] = {}
    for c in components:
      if not isinstance(c, dict) or not isinstance(c.get("id"), str):
        continue
      comp_map[c["id"]] = c
      if c["id"] == "root":
        root = c

    if root is None:
      continue

    # Construir conjunto de alcanzables desde root
    reachable: set[str] = set()
    _collect_refs(root, comp_map, reachable)

    # Identificar huérfanos
    all_ids = set(comp_map.keys())
    orphans = all_ids - reachable

    if not orphans:
      continue

    # Reconectar huérfanos
    root_comp = root.get("component", "")
    orphan_list = sorted(orphans)

    if root_comp in ("Column", "Row", "List"):
      children = root.get("children", [])
      if isinstance(children, list):
        for oid in orphan_list:
          if oid not in children:
            children.append(oid)
        root["children"] = children
      else:
        _wrap_root_with_orphans(root, components, comp_map, orphan_list)
    elif root_comp == "Card":
      # Card tiene child (string). Envolver en Column.
      original_child = root.get("child")
      new_col_id = _unique_component_id(comp_map, "repaired-column")
      new_col = {
          "id": new_col_id,
          "component": "Column",
          "children": [original_child] + orphan_list if original_child else orphan_list,
      }
      root["child"] = new_col_id
      components.append(new_col)
    else:
      _wrap_root_with_orphans(root, components, comp_map, orphan_list)

    if repair_log is not None:
      repair_log.append(
          f"Superficie '{sid}': componentes huerfanos reconectados: "
          + ", ".join(orphan_list)
      )

  return patched


def _wrap_root_with_orphans(
    root: dict[str, Any],
    components: list[dict[str, Any]],
    comp_map: dict[str, dict[str, Any]],
    orphan_list: list[str],
) -> None:
  """Conserva un root no estatico dentro de un nuevo ``Column`` raiz."""
  inner_root_id = _unique_component_id(comp_map, "root-inner")
  root["id"] = inner_root_id
  components.append({
      "id": "root",
      "component": "Column",
      "children": [inner_root_id] + orphan_list,
  })


def _unique_component_id(
    comp_map: dict[str, dict[str, Any]],
    base: str,
) -> str:
  """Devuelve un id no usado partiendo de ``base``."""
  if base not in comp_map:
    return base
  idx = 2
  while f"{base}-{idx}" in comp_map:
    idx += 1
  return f"{base}-{idx}"


def _collect_refs(
    component: dict[str, Any],
    comp_map: dict[str, dict[str, Any]],
    reachable: set[str],
) -> None:
  """Recorre el árbol de componentes desde ``component`` y marca alcanzables."""
  cid = component.get("id", "")
  if cid in reachable:
    return
  reachable.add(cid)

  # children (lista de strings)
  children = component.get("children")
  if isinstance(children, list):
    for child_id in children:
      if isinstance(child_id, str) and child_id in comp_map:
        _collect_refs(comp_map[child_id], comp_map, reachable)

  # child (string)
  child = component.get("child")
  if isinstance(child, str) and child in comp_map:
    _collect_refs(comp_map[child], comp_map, reachable)

  # trigger y content (Modal)
  for field in ("trigger", "content"):
    val = component.get(field)
    if isinstance(val, str) and val in comp_map:
      _collect_refs(comp_map[val], comp_map, reachable)

  # tabs (lista de {child: string})
  tabs = component.get("tabs")
  if isinstance(tabs, list):
    for tab in tabs:
      if isinstance(tab, dict):
        child_id = tab.get("child")
        if isinstance(child_id, str) and child_id in comp_map:
          _collect_refs(comp_map[child_id], comp_map, reachable)

  # children como {componentId, path} (List dinámica)
  children_dyn = component.get("children")
  if isinstance(children_dyn, dict):
    cid_dyn = children_dyn.get("componentId")
    if isinstance(cid_dyn, str) and cid_dyn in comp_map:
      _collect_refs(comp_map[cid_dyn], comp_map, reachable)


def find_orphans(payload: list[dict[str, Any]]) -> list[str]:
  """Devuelve los IDs de componentes huérfanos en el payload.

  Útil para diagnóstico y tests. No modifica el payload.

  Args:
    payload: Lista de mensajes A2UI.

  Returns:
    Lista de IDs de componentes no alcanzables desde ``root``.
  """
  found: set[str] = set()
  for msg in payload:
    if "updateComponents" not in msg:
      continue
    components = msg["updateComponents"].get("components", [])
    if not components:
      continue

    comp_map = {
        c["id"]: c
        for c in components
        if isinstance(c, dict) and isinstance(c.get("id"), str)
    }
    root = comp_map.get("root")
    if root is None:
      continue

    reachable: set[str] = set()
    _collect_refs(root, comp_map, reachable)
    all_ids = set(comp_map.keys())
    found.update(all_ids - reachable)
  return sorted(found)


# --- Mapeo de iconos comunes que los modelos inventan --------------

ICON_ALIASES: dict[str, str] = {
    # Clima
    "cloud": "info",
    "cloudy": "info",
    "sunny": "info",
    "rain": "info",
    "snow": "info",
    "storm": "warning",
    "weather": "info",
    "wb_sunny": "info",
    "wb_cloudy": "info",
    "thermostat": "info",
    "temp": "info",
    "temperature": "info",
    # UI comunes
    "menu_bar": "menu",
    "hamburger": "menu",
    "cross": "close",
    "x": "close",
    "plus": "add",
    "minus": "remove",
    "remove": "delete",
    "trash": "delete",
    "bin": "delete",
    "pencil": "edit",
    "pen": "edit",
    "gear": "settings",
    "cog": "settings",
    "configuration": "settings",
    "magnifier": "search",
    "loupe": "search",
    "email": "mail",
    "envelope": "mail",
    "bell": "notifications",
    "notification": "notifications",
    "alert": "warning",
    "exclamation": "warning",
    "question": "help",
    "questionMark": "help",
    "user": "person",
    "profile": "person",
    "account": "accountCircle",
    "calendar": "calendarToday",
    "clock": "event",
    "time": "event",
    "heart": "favorite",
    "upload_file": "upload",
    "download_file": "download",
    "eye": "visibility",
    "eyeOff": "visibilityOff",
    "lockClosed": "lock",
    "key": "lockOpen",
    "cart": "shoppingCart",
    "basket": "shoppingCart",
    "refresh": "refresh",
    "reload": "refresh",
    "sync": "refresh",
    "share": "share",
    "back": "arrowBack",
    "forward": "arrowForward",
    "chevronLeft": "arrowBack",
    "chevronRight": "arrowForward",
    "photo_library": "photo",
    "image": "photo",
    "picture": "photo",
    "camera_alt": "camera",
    "phone": "phone",
    "telephone": "phone",
    "location": "locationOn",
    "pin": "locationOn",
    "place": "locationOn",
    "play_arrow": "play",
    "pause_circle": "pause",
    "stop_circle": "stop",
    "volume": "volumeUp",
    "sound": "volumeUp",
    "mute": "volumeMute",
    "print": "print",
    "send": "send",
    "paper_plane": "send",
    "check_circle": "check",
    "done": "check",
    "tick": "check",
    "error_outline": "error",
    "warning_amber": "warning",
    "info_outline": "info",
    "more": "moreHoriz",
    "dots": "moreHoriz",
    "expand": "moreVert",
    "collapse": "moreVert",
    "folder_open": "folder",
    "file": "attachFile",
    "attachment": "attachFile",
    "paperclip": "attachFile",
    "star_outline": "starOff",
    "star_filled": "star",
    "star_half": "starHalf",
    "favorite_heart": "favorite",
    "heart_outline": "favoriteOff",
}

# Iconos validos del Basic Catalog v0.9 (59)
VALID_ICONS: set[str] = {
    "accountCircle",
    "add",
    "arrowBack",
    "arrowForward",
    "attachFile",
    "calendarToday",
    "call",
    "camera",
    "check",
    "close",
    "delete",
    "download",
    "edit",
    "event",
    "error",
    "fastForward",
    "favorite",
    "favoriteOff",
    "folder",
    "help",
    "home",
    "info",
    "locationOn",
    "lock",
    "lockOpen",
    "mail",
    "menu",
    "moreVert",
    "moreHoriz",
    "notificationsOff",
    "notifications",
    "pause",
    "payment",
    "person",
    "phone",
    "photo",
    "play",
    "print",
    "refresh",
    "rewind",
    "search",
    "send",
    "settings",
    "share",
    "shoppingCart",
    "skipNext",
    "skipPrevious",
    "star",
    "starHalf",
    "starOff",
    "stop",
    "upload",
    "visibility",
    "visibilityOff",
    "volumeDown",
    "volumeMute",
    "volumeOff",
    "volumeUp",
    "warning",
}


def repair_icons(
    payload: list[dict[str, Any]],
    *,
    valid_icons: Optional[set[str]] = None,
    repair_log: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
  """Repara nombres de iconos invalidos en un payload A2UI.

  Los modelos a veces inventan nombres de iconos que no estan en el enum
  del catalogo. Esta funcion:

  1. Si el nombre es un string y esta en ``ICON_ALIASES``, lo mapea al
     icono valido correspondiente.
  2. Si el nombre es un string y no esta en el enum ni en los aliases, lo
     sustituye por ``info`` (icono generico).
  3. Si el nombre es un objeto (FunctionCall o path), lo sustituye por
     ``info`` (el schema no permite objetos en ``Icon.name``).

  Args:
    payload: Lista de mensajes A2UI.
    valid_icons: Conjunto de iconos validos. Si es ``None``, se usa
      ``VALID_ICONS`` (los 59 del Basic Catalog v0.9).
    repair_log: Lista opcional para registrar cada sustitucion aplicada.

  Returns:
    El payload con iconos reparados (copia profunda).
  """
  if valid_icons is None:
    valid_icons = VALID_ICONS
  patched = copy.deepcopy(payload)
  fallback_icon = "info" if "info" in valid_icons else None
  if fallback_icon is None and valid_icons:
    fallback_icon = sorted(valid_icons)[0]

  for msg in patched:
    if "updateComponents" not in msg:
      continue
    for comp in msg["updateComponents"].get("components", []):
      if comp.get("component") != "Icon":
        continue
      name = comp.get("name")
      replacement: Optional[str] = None
      if isinstance(name, str):
        if name in valid_icons:
          continue
        # Probar mapeo
        mapped = ICON_ALIASES.get(name)
        if mapped and mapped in valid_icons:
          replacement = mapped
        elif fallback_icon is not None:
          replacement = fallback_icon
      elif isinstance(name, dict):
        # FunctionCall o path en Icon.name: el schema no lo permite
        # (solo acepta string o {svgPath}). Sustituir por un icono seguro.
        replacement = fallback_icon
      if replacement is not None:
        comp["name"] = replacement
        if repair_log is not None:
          repair_log.append(
              f"Icon '{comp.get('id', '?')}': {name!r} sustituido por {replacement!r}"
          )
  return patched


# --- Funciones inexistentes ----------------------------------------

# Funciones validas del Basic Catalog v0.9 (14)
VALID_FUNCTIONS: set[str] = {
    "required",
    "regex",
    "length",
    "numeric",
    "email",
    "formatString",
    "formatNumber",
    "formatCurrency",
    "formatDate",
    "pluralize",
    "openUrl",
    "and",
    "or",
    "not",
}


def repair_functions(
    payload: list[dict[str, Any]],
    *,
    valid_functions: Optional[set[str]] = None,
    repair_log: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
  """Repara FunctionCalls con funciones inexistentes en un payload A2UI.

  Los modelos a veces inventan funciones que no existen en el catalogo
  (``ternary``, ``if``, ``switch``...). Esta funcion:

  1. Recorre todos los ``FunctionCall`` del payload (en ``checks``,
     ``text``, ``action.functionCall`` y cualquier objeto con ``call``).
  2. Si la funcion no es valida, sustituye el ``FunctionCall`` por un
     valor literal: ``False`` si retorna ``boolean``, string vacio si
     retorna ``string``, o elimina el ``check`` si esta en una lista.

  Args:
    payload: Lista de mensajes A2UI.
    valid_functions: Conjunto de funciones validas. Si es ``None``, se
      usa ``VALID_FUNCTIONS`` (las 14 del Basic Catalog v0.9).
    repair_log: Lista opcional para registrar cada funcion sustituida.

  Returns:
    El payload con funciones reparadas (copia profunda).
  """
  if valid_functions is None:
    valid_functions = VALID_FUNCTIONS
  patched = copy.deepcopy(payload)
  no_fallback = object()

  def _repair_call(
      obj: Any,
      *,
      location: str,
      fallback: Any = no_fallback,
  ) -> Any:
    """Reemplaza un FunctionCall invalido por un valor literal."""
    if isinstance(obj, dict):
      if "call" in obj and isinstance(obj["call"], str):
        if obj["call"] not in valid_functions:
          replacement = fallback
          if replacement is no_fallback:
            ret = obj.get("returnType", "")
            if ret == "boolean":
              replacement = False
            elif ret == "string":
              replacement = ""
            elif ret == "void":
              replacement = None
            else:
              args = obj.get("args", {})
              if isinstance(args, dict) and "value" in args:
                replacement = args["value"]
              else:
                replacement = False
          if repair_log is not None:
            repair_log.append(
                f"{location}: funcion {obj['call']!r} sustituida por {replacement!r}"
            )
          return replacement
      # Recursivamente reparar sub-objetos
      result = {}
      for k, v in obj.items():
        result[k] = _repair_call(v, location=f"{location}.{k}")
      return result
    if isinstance(obj, list):
      return [
          _repair_call(item, location=f"{location}[{index}]")
          for index, item in enumerate(obj)
      ]
    return obj

  for msg in patched:
    if "updateComponents" not in msg:
      continue
    for comp in msg["updateComponents"].get("components", []):
      component_location = f"Componente '{comp.get('id', '?')}'"
      # Reparar text si es FunctionCall
      if isinstance(comp.get("text"), dict):
        comp["text"] = _repair_call(
            comp["text"], location=f"{component_location}.text", fallback=""
        )
      # Reparar checks
      if isinstance(comp.get("checks"), list):
        new_checks = []
        for index, check in enumerate(comp["checks"]):
          if isinstance(check, dict) and isinstance(check.get("condition"), dict):
            repaired_condition = _repair_call(
                check["condition"],
                location=f"{component_location}.checks[{index}].condition",
                fallback=False,
            )
            if repaired_condition is not False:
              check["condition"] = repaired_condition
              new_checks.append(check)
          else:
            new_checks.append(check)
        comp["checks"] = new_checks
      # Reparar action.functionCall
      action = comp.get("action")
      if isinstance(action, dict) and "functionCall" in action:
        repaired = _repair_call(
            action["functionCall"],
            location=f"{component_location}.action.functionCall",
            fallback=None,
        )
        if repaired is None:
          # Eliminar functionCall invalida, dejar event si hay
          action.pop("functionCall", None)
          if "event" not in action:
            action["event"] = {"name": "unknown"}
        else:
          action["functionCall"] = repaired
      # Cubrir FunctionCall en otras propiedades dinamicas del componente.
      for key, value in list(comp.items()):
        if key in {"text", "checks", "action"}:
          continue
        comp[key] = _repair_call(value, location=f"{component_location}.{key}")
  return patched


# --- ChildList dinamico en Row/Column ------------------------------


def repair_childlists(
    payload: list[dict[str, Any]],
    *,
    repair_log: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
  """Repara children dinamicos en Row/Column.

  El Basic Catalog de A2UI permite ``ChildList`` dinamico (``{componentId,
  path}``) solo en ``List``. Los modelos a veces lo usan en ``Row`` o
  ``Column``, que solo aceptan arrays de strings (IDs de componentes).

  Esta funcion convierte un ``children`` dinamico en ``Row``/``Column`` a
  un array estatico con el ``componentId`` referenciado. Si el componente
  referenciado no existe, lo sustituye por una lista vacia (que el
  validador rechazara por ``minItems: 1``, pero al menos el error sera
  claro y el componente se podra reconectar con ``repair_orphans``).

  Args:
    payload: Lista de mensajes A2UI.

  Returns:
    El payload con children dinamicos reparados (copia profunda).
  """
  patched = copy.deepcopy(payload)

  for msg in patched:
    if "updateComponents" not in msg:
      continue
    for comp in msg["updateComponents"].get("components", []):
      comp_type = comp.get("component", "")
      if comp_type not in ("Row", "Column"):
        continue
      children = comp.get("children")
      if not isinstance(children, list):
        continue
      new_children = []
      converted = False
      for child in children:
        if isinstance(child, dict):
          # ChildList dinamico: extraer componentId
          cid = child.get("componentId")
          if isinstance(cid, str):
            new_children.append(cid)
            converted = True
          # Si no hay componentId, ignorar (se perdera la ref)
        elif isinstance(child, str):
          new_children.append(child)
      comp["children"] = new_children
      if converted and repair_log is not None:
        repair_log.append(
            f"{comp_type} '{comp.get('id', '?')}': children dinamicos "
            "envueltos en lista convertidos a referencias estaticas"
        )
  return patched


def _catalog_valid_icons(catalog: Any) -> set[str]:
  """Extrae los iconos validos del catalogo activo."""
  icon_schema = catalog.catalog_schema.get("components", {}).get("Icon")
  if not isinstance(icon_schema, dict):
    return set()

  found: set[str] = set()

  def _walk(node: Any, *, inside_name: bool = False) -> None:
    if isinstance(node, dict):
      if inside_name and isinstance(node.get("enum"), list):
        found.update(value for value in node["enum"] if isinstance(value, str))
      properties = node.get("properties")
      if isinstance(properties, dict) and "name" in properties:
        _walk(properties["name"], inside_name=True)
      for key, value in node.items():
        if key != "properties":
          _walk(value, inside_name=inside_name)
    elif isinstance(node, list):
      for value in node:
        _walk(value, inside_name=inside_name)

  _walk(icon_schema)
  return found


def _catalog_valid_functions(catalog: Any) -> set[str]:
  """Extrae las funciones validas del catalogo activo."""
  functions = catalog.catalog_schema.get("functions", {})
  if not isinstance(functions, dict):
    return set()
  return set(functions)


def _uses_datetime_bounds(payload: list[dict[str, Any]]) -> bool:
  for msg in payload:
    update = msg.get("updateComponents")
    if not isinstance(update, dict):
      continue
    for comp in update.get("components", []):
      if (
          isinstance(comp, dict)
          and comp.get("component") == "DateTimeInput"
          and ("min" in comp or "max" in comp)
      ):
        return True
  return False


def repair_payload(
    payload: list[dict[str, Any]],
    *,
    catalog: Any = None,
    repair_log: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
  """Aplica de forma consistente todas las reparaciones de payload.

  Cuando se proporciona ``catalog``, los iconos y funciones validos se
  extraen de ese catalogo. Esto evita modificar extensiones legitimas de
  catalogos personalizados.
  """
  valid_icons = _catalog_valid_icons(catalog) if catalog is not None else None
  valid_functions = _catalog_valid_functions(catalog) if catalog is not None else None

  repaired = repair_childlists(payload, repair_log=repair_log)
  repaired = repair_orphans(repaired, repair_log=repair_log)
  repaired = repair_icons(
      repaired,
      valid_icons=valid_icons,
      repair_log=repair_log,
  )
  repaired = repair_functions(
      repaired,
      valid_functions=valid_functions,
      repair_log=repair_log,
  )
  if repair_log is not None and _uses_datetime_bounds(repaired):
    repair_log.append("DateTimeInput: schema min/max corregido de oneOf a anyOf")
  return repaired
