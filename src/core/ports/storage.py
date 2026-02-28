"""Storage port interfaces for history_store and note_manager abstraction (KIK-513).

These Protocols match the public API of src.data.history_store and
src.data.note_manager. Existing modules satisfy them structurally.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HistoryStore(Protocol):
    """Persistent storage for screening/report/trade/health/research history.

    Matches the public API of src.data.history_store.
    """

    def save_screening(
        self,
        preset: str,
        region: str,
        results: list[dict],
        sector: str | None = None,
        theme: str | None = None,
        base_dir: str = "data/history",
    ) -> str:
        """Save screening results. Returns absolute path of saved file."""
        ...

    def save_report(
        self,
        symbol: str,
        data: dict,
        score: float,
        verdict: str,
        base_dir: str = "data/history",
    ) -> str:
        """Save a stock report. Returns absolute path of saved file."""
        ...

    def save_research(
        self,
        research_type: str,
        target: str,
        result: dict,
        base_dir: str = "data/history",
    ) -> str:
        """Save research results. Returns absolute path of saved file."""
        ...

    def load_history(
        self,
        category: str,
        days_back: int | None = None,
        base_dir: str = "data/history",
    ) -> list[dict]:
        """Load history files for *category*, sorted newest-first."""
        ...


@runtime_checkable
class NoteStore(Protocol):
    """Storage for investment notes (thesis, concern, lesson, etc.).

    Matches the public API of src.data.note_manager.
    """

    def save_note(
        self,
        symbol: str,
        note_type: str,
        content: str,
        *,
        category: str = "stock",
        base_dir: str = "data/notes",
    ) -> str:
        """Save an investment note. Returns absolute path of saved file."""
        ...

    def list_notes(
        self,
        symbol: str | None = None,
        note_type: str | None = None,
        category: str | None = None,
        base_dir: str = "data/notes",
    ) -> list[dict]:
        """Return notes matching the given filters."""
        ...
