"""Graph port interfaces for Neo4j graph store abstraction (KIK-513).

GraphReader: read-only queries against the knowledge graph.
GraphWriter: write operations to persist investment data in the graph.

These Protocols match the function signatures in src.data.graph_query and
src.data.graph_store. Existing modules satisfy them structurally.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GraphReader(Protocol):
    """Read-only access to the investment knowledge graph.

    Matches the public API of src.data.graph_query.
    """

    def get_last_health_check_date(self) -> str | None:
        """Return the ISO date string of the most recent health check, or None."""
        ...

    def get_old_thesis_notes(self, older_than_days: int = 90) -> list[dict]:
        """Return thesis notes older than *older_than_days* days."""
        ...

    def get_upcoming_events(self, within_days: int = 7) -> list[dict]:
        """Return upcoming events within *within_days* days."""
        ...

    def get_recurring_picks(self, min_count: int = 3) -> list[dict]:
        """Return stocks that appear in screenings >= *min_count* times."""
        ...

    def get_concern_notes(self, limit: int = 5) -> list[dict]:
        """Return the most recent concern-type investment notes."""
        ...

    def get_current_holdings(self) -> list[dict]:
        """Return current portfolio holdings from the graph."""
        ...

    def get_industry_research_for_linking(
        self,
        sector: str,
        days: int = 14,
        limit: int = 1,
    ) -> list[dict]:
        """Return recent industry research nodes matching *sector*."""
        ...

    def get_open_action_items(self) -> list[dict]:
        """Return open/pending action items from the graph."""
        ...


@runtime_checkable
class GraphWriter(Protocol):
    """Write operations for the investment knowledge graph.

    Matches the public API of src.data.graph_store for action-item operations.
    """

    def merge_action_item(
        self,
        *,
        action_id: str,
        action_date: str,
        trigger_type: str,
        title: str,
        symbol: str,
        urgency: str,
        source_node_id: str | None = None,
    ) -> bool:
        """Create or update an ActionItem node. Returns True on success."""
        ...

    def update_action_item_linear(
        self,
        *,
        action_id: str,
        linear_issue_id: str,
        linear_issue_url: str,
        linear_identifier: str,
    ) -> None:
        """Link an ActionItem node to its Linear issue."""
        ...
