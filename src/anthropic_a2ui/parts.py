"""Helpers de transporte para envolver JSON de A2UI en DataParts.

Esta pieza es la menos acoplada a Anthropic: sirve igual si el JSON viene de
tool use, de tags ``<a2ui-json>`` o de structured output. Produce la
envoltura estándar que los renderers de A2UI esperan (MIME
``application/a2ui+json``), compatible con A2A.

El módulo no depende de ``a2a-sdk`` para evitar arrastrar el transporte al
importar ``anthropic-a2ui``; en su lugar define ``A2uiPart`` como un dataclass
ligero. Si el caller ya usa ``a2a-sdk`` puede convertirlo fácilmente, y se
ofrece ``to_a2a_datapart`` que intenta el bridge si ``a2a`` está instalado.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

MIME_A2UI = "application/a2ui+json"


@dataclass(frozen=True, slots=True)
class A2uiPart:
  """Envoltura estándar de un mensaje A2UI para transporte.

  Attributes:
    mime: Tipo MIME bajo el que se etiqueta el payload. El protocolo A2UI
      define ``application/a2ui+json`` como estándar para los DataParts.
    data: El JSON A2UI ya parseado (lista de mensajes o mensaje único). Se
      conserva como objeto para que el receptor lo use directamente; si hace
      falta serializar, usar ``part.to_json_string()``.
  """

  mime: str = MIME_A2UI
  data: Any = field(default=None)

  def to_json_string(self, **kwargs: Any) -> str:
    """Serializa ``data`` a cadena JSON compacta.

    Args:
      **kwargs: Argumentos extra para ``json.dumps`` (por ejemplo
        ``indent=2`` para pretty-print).
    """
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(self.data, **kwargs)

  def to_dict(self) -> dict[str, Any]:
    """Convierte el part a un dict plano apto para serialización genérica.

    Útil para enviar por JSON-RPC, SSE o cualquier canal que no sea A2A.
    """
    return {"mimeType": self.mime, "data": self.data}


def to_a2ui_part(payload: Any, *, mime: str = MIME_A2UI) -> A2uiPart:
  """Envuelve un payload A2UI (dict o lista) en un ``A2uiPart``.

  Args:
    payload: El JSON A2UI ya parseado. Puede ser un único mensaje (dict) o
      una lista de mensajes; el protocolo admite ambos.
    mime: Tipo MIME a usar. Por defecto el estándar del protocolo.

  Returns:
    Un ``A2uiPart`` listo para entregar al renderer o al transporte.
  """
  return A2uiPart(mime=mime, data=payload)


def to_a2a_datapart(part: A2uiPart) -> Any:
  """Intenta convertir un ``A2uiPart`` a ``a2a.types.DataPart``.

  Esta función es opcional y solo funciona si ``a2a-sdk`` está instalado. Si
  no lo está, devuelve el dict plano (``part.to_dict()``) para que el caller
  lo envuelva como prefiera.

  Returns:
    Un ``DataPart`` de ``a2a`` si está disponible, o un dict con
    ``{"mimeType": ..., "data": ...}`` si no.
  """
  try:
    from a2a.types import DataPart  # type: ignore
  except Exception:
    return part.to_dict()
  dp = DataPart(**part.to_dict())  # type: ignore[call-arg]
  return dp


def parse_a2ui_part_json(raw: str | bytes) -> Any:
  """Parsea una cadena JSON de A2UI y devuelve el objeto.

  Es un atajo sobre ``json.loads`` que acepta ``str`` o ``bytes`` y que lanza
  ``ValueError`` (en vez de ``json.JSONDecodeError``) para que el caller pueda
  capturar de forma agnóstica al framework de serialización.

  Args:
    raw: Cadena o bytes con JSON A2UI.

  Returns:
    El objeto parseado (dict o lista).

  Raises:
    ValueError: Si el contenido no es JSON válido.
  """
  try:
    return json.loads(raw)
  except json.JSONDecodeError as exc:
    raise ValueError(f"JSON A2UI inválido: {exc}") from exc
