"""Provenance Model: the full lineage chain, queryable.

Source → Evidence → Hypothesis → Dataset → Feature → Strategy → Experiment
→ Evaluation → Risk Decision → Promotion → Execution → Outcome → PostMortem
"""

from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(StrEnum):
    SOURCE = "SOURCE"
    EVIDENCE = "EVIDENCE"
    HYPOTHESIS = "HYPOTHESIS"
    DATASET_VERSION = "DATASET_VERSION"
    FEATURE_VERSION = "FEATURE_VERSION"
    STRATEGY_VERSION = "STRATEGY_VERSION"
    MODEL_VERSION = "MODEL_VERSION"
    EXPERIMENT = "EXPERIMENT"
    EVALUATION = "EVALUATION"
    RISK_DECISION = "RISK_DECISION"
    PROMOTION = "PROMOTION"
    EXECUTION = "EXECUTION"
    OUTCOME = "OUTCOME"
    POST_MORTEM = "POST_MORTEM"


class ProvenanceNode(BaseModel):
    node_id: str
    node_type: NodeType
    label: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    data: dict[str, Any] = Field(default_factory=dict)


class ProvenanceEdge(BaseModel):
    from_id: str
    to_id: str
    relationship: str  # "supports", "contradicts", "tested_by", "produces", etc.
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ProvenanceGraph:
    """In-memory provenance graph. Swap for PostgreSQL+CTE or Neo4j at scale."""

    def __init__(self) -> None:
        self._nodes: dict[str, ProvenanceNode] = {}
        self._edges: list[ProvenanceEdge] = []
        self._children: dict[str, list[str]] = defaultdict(list)
        self._parents: dict[str, list[str]] = defaultdict(list)

    def add_node(
        self, node_id: str, node_type: NodeType, label: str = "", **data: Any
    ) -> ProvenanceNode:
        if node_id in self._nodes:
            raise ValueError(f"node already exists: {node_id!r}")
        node = ProvenanceNode(node_id=node_id, node_type=node_type, label=label, data=data)
        self._nodes[node_id] = node
        return node

    def add_edge(self, from_id: str, to_id: str, relationship: str) -> ProvenanceEdge:
        if from_id not in self._nodes:
            raise KeyError(f"source node not found: {from_id!r}")
        if to_id not in self._nodes:
            raise KeyError(f"target node not found: {to_id!r}")
        edge = ProvenanceEdge(from_id=from_id, to_id=to_id, relationship=relationship)
        self._edges.append(edge)
        self._children[from_id].append(to_id)
        self._parents[to_id].append(from_id)
        return edge

    def get_node(self, node_id: str) -> ProvenanceNode:
        node = self._nodes.get(node_id)
        if node is None:
            raise KeyError(f"node not found: {node_id!r}")
        return node

    def lineage_forward(self, node_id: str, max_depth: int = 20) -> list[ProvenanceNode]:
        """All nodes downstream from this node (what it led to)."""
        visited: set[str] = set()
        out: list[ProvenanceNode] = []
        self._traverse(node_id, self._children, visited, out, max_depth)
        return out

    def lineage_backward(self, node_id: str, max_depth: int = 20) -> list[ProvenanceNode]:
        """All nodes upstream from this node (what led to it)."""
        visited: set[str] = set()
        out: list[ProvenanceNode] = []
        self._traverse(node_id, self._parents, visited, out, max_depth)
        return out

    def full_chain(self, execution_id: str) -> dict[str, Any]:
        """Full lineage: backward (why) + node + forward (what it led to)."""
        return {
            "node": self.get_node(execution_id).model_dump(),
            "upstream": [n.model_dump() for n in self.lineage_backward(execution_id)],
            "downstream": [n.model_dump() for n in self.lineage_forward(execution_id)],
        }

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return len(self._edges)

    def _traverse(
        self,
        node_id: str,
        adjacency: dict[str, list[str]],
        visited: set[str],
        out: list[ProvenanceNode],
        depth: int,
    ) -> None:
        if depth <= 0 or node_id in visited:
            return
        visited.add(node_id)
        for child_id in adjacency.get(node_id, []):
            child = self._nodes.get(child_id)
            if child:
                out.append(child)
                self._traverse(child_id, adjacency, visited, out, depth - 1)
