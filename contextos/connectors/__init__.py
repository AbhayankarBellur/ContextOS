"""
ContextOS connectors — pluggable external data source adapters.

Each connector pulls structured data from an external source and converts
it to YAML-frontmattered Markdown files ready for vault indexing.

All connectors:
  - Are idempotent (content-hash dedup prevents re-writing unchanged docs)
  - Store output in .contextos/pulled/<connector>/<project>/ by default
  - Require zero network calls at runtime EXCEPT during the explicit pull
  - Never modify existing vault documents

Registry:
  CONNECTORS maps connector name -> class for CLI dispatch.
"""
from contextos.connectors.base import BaseConnector, ConnectorResult
from contextos.connectors.github import GitHubConnector
from contextos.connectors.openapi import OpenAPIConnector
from contextos.connectors.json_source import JSONConnector

CONNECTORS: dict[str, type[BaseConnector]] = {
    "github":  GitHubConnector,
    "openapi": OpenAPIConnector,
    "json":    JSONConnector,
}

__all__ = ["BaseConnector", "ConnectorResult", "CONNECTORS",
           "GitHubConnector", "OpenAPIConnector", "JSONConnector"]
