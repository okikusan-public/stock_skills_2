"""Unified lesson conflict detection engine (KIK-570).

Extracted from note_manager.py and auto_context.py to ensure
consistent conflict detection across save-time and display-time.

Handles:
- CJK tokenization (Japanese text without spaces)
- Content-based trigger/action parsing (legacy data compatibility)
- Keyword + optional TEI embedding similarity
"""

import re
from typing import Optional


# ---------------------------------------------------------------------------
# CJK-aware tokenizer
# ---------------------------------------------------------------------------

_CJK_RANGES = (
    r"\u3040-\u309f"  # Hiragana
    r"\u30a0-\u30ff"  # Katakana
    r"\u4e00-\u9fff"  # CJK Unified Ideographs
    r"\uff66-\uff9f"  # Half-width Katakana
)

_TOKEN_RE = re.compile(
    rf"[A-Za-z0-9]+|[{_CJK_RANGES}]+",
    re.UNICODE,
)


def tokenize(text: str) -> list[str]:
    """Tokenize text into words, handling CJK characters.

    For CJK text, splits into individual characters/character runs.
    For Latin text, splits on word boundaries.
    """
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text) if len(t) >= 1]


def keyword_similarity(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity using CJK-aware tokenization."""
    tokens_a = set(tokenize(text_a))
    tokens_b = set(tokenize(text_b))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union) if union else 0.0


# ---------------------------------------------------------------------------
# Content-based trigger/action parsing (legacy data)
# ---------------------------------------------------------------------------

_TRIGGER_PATTERNS = [
    re.compile(r"■trigger[:：]\s*(.+?)(?:\n|■|$)", re.IGNORECASE),
    re.compile(r"トリガー[:：]\s*(.+?)(?:\n|■|$)"),
    re.compile(r"trigger[:：]\s*(.+?)(?:\n|■|$)", re.IGNORECASE),
]

_ACTION_PATTERNS = [
    re.compile(r"■expected_action[:：]\s*(.+?)(?:\n|■|$)", re.IGNORECASE),
    re.compile(r"次回アクション[:：]\s*(.+?)(?:\n|■|$)"),
    re.compile(r"expected_action[:：]\s*(.+?)(?:\n|■|$)", re.IGNORECASE),
]


def extract_trigger(lesson: dict) -> str:
    """Extract trigger from lesson, falling back to content parsing."""
    trigger = (lesson.get("trigger") or "").strip()
    if trigger:
        return trigger
    content = lesson.get("content", "")
    if not content:
        return ""
    for pat in _TRIGGER_PATTERNS:
        m = pat.search(content)
        if m:
            return m.group(1).strip()
    return ""


def extract_action(lesson: dict) -> str:
    """Extract expected_action from lesson, falling back to content parsing."""
    action = (lesson.get("expected_action") or "").strip()
    if action:
        return action
    content = lesson.get("content", "")
    if not content:
        return ""
    for pat in _ACTION_PATTERNS:
        m = pat.search(content)
        if m:
            return m.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# Embedding similarity (optional TEI)
# ---------------------------------------------------------------------------

def embedding_similarity(text_a: str, text_b: str) -> Optional[float]:
    """Compute cosine similarity via TEI embeddings. Returns None if unavailable."""
    try:
        from src.data import embedding_client
        if not embedding_client.is_available():
            return None
        emb_a = embedding_client.get_embedding(text_a)
        emb_b = embedding_client.get_embedding(text_b)
        if emb_a is None or emb_b is None:
            return None
        dot = sum(a * b for a, b in zip(emb_a, emb_b))
        norm_a = sum(a * a for a in emb_a) ** 0.5
        norm_b = sum(b * b for b in emb_b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Unified conflict detection
# ---------------------------------------------------------------------------

def find_conflicts(
    new_lesson: dict,
    existing_lessons: list[dict],
    similarity_threshold: float = 0.5,
    max_results: int = 5,
) -> list[dict]:
    """Detect conflicts between a new lesson and existing lessons.

    Uses CJK-aware tokenization, content-based trigger/action parsing,
    and optional TEI embedding similarity.

    Returns list of {existing_lesson, similarity, conflict_type, conflict_detail}.
    """
    new_trigger = extract_trigger(new_lesson)
    new_action = extract_action(new_lesson)
    new_content = (new_lesson.get("content") or "").strip()
    new_text = f"{new_trigger} {new_action} {new_content}".strip()

    if not new_text:
        return []

    conflicts = []
    for ex in existing_lessons:
        if ex.get("id") == new_lesson.get("id"):
            continue

        ex_trigger = extract_trigger(ex)
        ex_action = extract_action(ex)
        ex_content = (ex.get("content") or "").strip()
        ex_text = f"{ex_trigger} {ex_action} {ex_content}".strip()

        if not ex_text:
            continue

        # Trigger-focused similarity
        trigger_sim = keyword_similarity(new_trigger, ex_trigger) if new_trigger and ex_trigger else 0.0
        text_sim = keyword_similarity(new_text, ex_text)
        sim = trigger_sim * 0.6 + text_sim * 0.4 if trigger_sim > 0 else text_sim

        # TEI embedding fallback
        if 0.2 < sim < similarity_threshold:
            emb_sim = embedding_similarity(new_text, ex_text)
            if emb_sim is not None:
                sim = max(sim, emb_sim)

        if sim < similarity_threshold:
            continue

        # Conflict type
        conflict_type = "similar"
        conflict_detail = ""
        if trigger_sim > 0.3 and new_action != ex_action and new_action and ex_action:
            conflict_type = "contradicting_action"
            conflict_detail = f"{ex_trigger} → {ex_action}"

        conflicts.append({
            "existing_lesson": ex,
            "similarity": round(sim, 3),
            "conflict_type": conflict_type,
            "conflict_detail": conflict_detail,
        })

    conflicts.sort(key=lambda c: c["similarity"], reverse=True)
    return conflicts[:max_results]


def find_conflict_pairs(lessons: list[dict]) -> dict[str, str]:
    """Find lesson IDs with potential contradictions.

    Returns {lesson_id: conflict_detail} for annotated display.
    """
    conflict_map: dict[str, str] = {}
    if len(lessons) < 2:
        return conflict_map

    for i, a in enumerate(lessons):
        for b in lessons[i + 1:]:
            a_trigger = extract_trigger(a)
            b_trigger = extract_trigger(b)
            if not a_trigger or not b_trigger:
                continue
            a_action = extract_action(a)
            b_action = extract_action(b)
            trigger_sim = keyword_similarity(a_trigger, b_trigger)
            if trigger_sim > 0.3 and a_action != b_action and a_action and b_action:
                a_id = a.get("id", "")
                b_id = b.get("id", "")
                if a_id:
                    conflict_map[a_id] = f"vs {b_trigger} → {b_action}"
                if b_id:
                    conflict_map[b_id] = f"vs {a_trigger} → {a_action}"

    return conflict_map
