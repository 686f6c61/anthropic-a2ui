"""Fixtures compartidas para los tests de anthropic-a2ui."""

import os

import pytest

from a2ui.schema.catalog import CatalogConfig
from a2ui.schema.catalog_provider import FileSystemCatalogProvider
from a2ui.schema.manager import A2uiSchemaManager

from anthropic_a2ui import ClaudeA2uiPromptBuilder


@pytest.fixture(scope="session")
def catalog_v09():
  """Catálogo básico A2UI v0.9 cargado desde a2ui-agent-sdk."""
  builder = ClaudeA2uiPromptBuilder(version="0.9")
  return builder.get_catalog()


@pytest.fixture(scope="session")
def builder_v09():
  """Builder para v0.9 con catálogo básico."""
  return ClaudeA2uiPromptBuilder(version="0.9")


@pytest.fixture(scope="session")
def validator_v09(catalog_v09):
  """Validador A2UI v0.9."""
  return catalog_v09.validator


@pytest.fixture
def sample_a2ui_json():
  """Payload A2UI mínimo válido: una superficie con un Text.

  La estructura sigue el schema v0.9: cada componente es un objeto con ``id``
  y los campos del tipo (``component`` es una string constante, no un
  objeto anidado).
  """
  return [
      {
          "version": "v0.9",
          "createSurface": {
              "surfaceId": "test-surface",
              "catalogId": (
                  "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
              ),
          },
      },
      {
          "version": "v0.9",
          "updateComponents": {
              "surfaceId": "test-surface",
              "components": [{
                  "id": "root",
                  "component": "Text",
                  "text": "Hola mundo",
              }],
          },
      },
  ]


@pytest.fixture(scope="session")
def catalog_v08():
  """Catálogo standard A2UI v0.8 (legacy, con MultipleChoice)."""
  builder = ClaudeA2uiPromptBuilder(version="0.8")
  return builder.get_catalog()


@pytest.fixture(scope="session")
def validator_v08(catalog_v08):
  """Validador A2UI v0.8."""
  return catalog_v08.validator


@pytest.fixture(scope="session")
def catalog_minimal():
  """Catálogo minimal A2UI v0.9 (5 componentes, 1 función capitalize).

  Se carga desde ``tests/assets/minimal_catalog.json`` vía
  ``FileSystemCatalogProvider`` para verificar que el paquete funciona con
  cualquier ``CatalogConfig``, no solo con ``BasicCatalog``.
  """
  assets_dir = os.path.join(os.path.dirname(__file__), "assets")
  catalog_path = os.path.join(assets_dir, "minimal_catalog.json")
  provider = FileSystemCatalogProvider(path=catalog_path)
  config = CatalogConfig(name="minimal", provider=provider)
  manager = A2uiSchemaManager(version="0.9", catalogs=[config])
  return manager.get_selected_catalog()


@pytest.fixture(scope="session")
def validator_minimal(catalog_minimal):
  """Validador del catálogo minimal v0.9."""
  return catalog_minimal.validator
