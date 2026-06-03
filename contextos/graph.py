"""
ContextOS graph.py — NetworkX knowledge graph builder and query engine.
Builds graph from document relationships (tags, references, supersedes).
Persisted as JSON in .contextos/graph/
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import networkx as nx

from contextos.schema import Document, GraphNode, GraphEdge, EdgeType, DocumentType

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Build and query the ContextOS knowledge graph."""

    def __init__(self):
        self.graph: nx.DiGraph = nx.DiGraph()

    def build(self, documents: list[Document]) -> nx.DiGraph:
        """
        Build a directed graph from documents.
        Nodes: one per document (GraphNode)
        Edges: derived from tags, ADR supersedes, domain relationships
        """
        self.graph.clear()

        # Build document lookup
        doc_by_id = {doc.id: doc for doc in documents}
        doc_by_title = {doc.title.lower(): doc for doc in documents}

        # Add all nodes
        for doc in documents:
            node = GraphNode(
                id=doc.id,
                type=doc.type,
                title=doc.title,
                domain=doc.domain,
            )
            self.graph.add_node(node.id, **node.model_dump())

        # Add edges based on relationships
        for doc in documents:
            # 1. Tag-based references
            for tag in doc.tags:
                # If a tag matches another document's title, create a 'references' edge
                tag_lower = tag.lower()
                if tag_lower in doc_by_title:
                    target_doc = doc_by_title[tag_lower]
                    if target_doc.id != doc.id:
                        self._add_edge(doc.id, target_doc.id, EdgeType.references)

            # 2. Domain relationships
            if doc.domain:
                # Connect documents in the same domain
                for other in documents:
                    if other.id != doc.id and other.domain == doc.domain:
                        # Architecture -> Domain
                        if doc.type == DocumentType.architecture and other.type == DocumentType.domain:
                            self._add_edge(doc.id, other.id, EdgeType.contains)
                        # Workflow -> Domain
                        elif doc.type == DocumentType.workflow and other.type == DocumentType.domain:
                            self._add_edge(doc.id, other.id, EdgeType.depends_on)

            # 3. ADR supersedes relationship
            if doc.type == DocumentType.adr:
                # Check for 'supersedes' in frontmatter or content
                # For MVP, we'll parse this from tags like 'supersedes:ADR-001'
                for tag in doc.tags:
                    if tag.startswith("supersedes:"):
                        superseded_title = tag.split(":", 1)[1].strip()
                        superseded_lower = superseded_title.lower()
                        if superseded_lower in doc_by_title:
                            target_doc = doc_by_title[superseded_lower]
                            self._add_edge(doc.id, target_doc.id, EdgeType.supersedes)

        logger.info(
            "Graph built: %d nodes, %d edges",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )
        return self.graph

    def _add_edge(self, source: str, target: str, relation: EdgeType):
        """Add an edge if not already present."""
        if not self.graph.has_edge(source, target):
            self.graph.add_edge(source, target, relation=relation.value)

    def expand(self, node_ids: list[str], hops: int = 1) -> list[GraphNode]:
        """
        Get N-hop neighbors of the given nodes.
        Returns list of GraphNode objects.
        """
        if not node_ids or not self.graph:
            return []

        neighbors = set(node_ids)
        for _ in range(hops):
            new_neighbors = set()
            for node in neighbors:
                if node in self.graph:
                    # Add predecessors and successors
                    new_neighbors.update(self.graph.predecessors(node))
                    new_neighbors.update(self.graph.successors(node))
            neighbors.update(new_neighbors)

        # Convert to GraphNode objects
        result = []
        for node_id in neighbors:
            if node_id in self.graph.nodes:
                attrs = self.graph.nodes[node_id]
                result.append(GraphNode(**attrs))

        return result

    def save(self, graph_dir: Path):
        """Persist graph as JSON (nodes + edges)."""
        graph_dir.mkdir(parents=True, exist_ok=True)
        graph_path = graph_dir / "graph.json"

        # Serialize nodes
        nodes = []
        for node_id, attrs in self.graph.nodes(data=True):
            nodes.append({"id": node_id, **attrs})

        # Serialize edges
        edges = []
        for source, target, attrs in self.graph.edges(data=True):
            edges.append({
                "source": source,
                "target": target,
                "relation": attrs.get("relation", "relates_to"),
            })

        data = {"nodes": nodes, "edges": edges}
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info("Graph saved to %s", graph_path)

    def load(self, graph_dir: Path) -> nx.DiGraph:
        """Load graph from JSON."""
        graph_path = graph_dir / "graph.json"
        if not graph_path.exists():
            logger.warning("No graph file found at %s", graph_path)
            return self.graph

        with open(graph_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.graph.clear()

        # Restore nodes
        for node_data in data.get("nodes", []):
            node_id = node_data.pop("id")
            self.graph.add_node(node_id, **node_data)

        # Restore edges
        for edge_data in data.get("edges", []):
            self.graph.add_edge(
                edge_data["source"],
                edge_data["target"],
                relation=edge_data.get("relation", "relates_to"),
            )

        logger.info("Graph loaded: %d nodes, %d edges", self.graph.number_of_nodes(), self.graph.number_of_edges())
        return self.graph

    def get_summary(self) -> dict:
        """Return a summary of the graph for display."""
        if not self.graph:
            return {"nodes": 0, "edges": 0, "types": {}}

        type_counts = {}
        for node_id, attrs in self.graph.nodes(data=True):
            doc_type = attrs.get("type", "unknown")
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

        relation_counts = {}
        for _, _, attrs in self.graph.edges(data=True):
            relation = attrs.get("relation", "unknown")
            relation_counts[relation] = relation_counts.get(relation, 0) + 1

        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "types": type_counts,
            "relations": relation_counts,
        }
