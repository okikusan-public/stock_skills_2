"""Lesson citation enforcement (KIK-736).

Filters lessons by relevance to user input + verifies that improvement
text actually cites the relevant lessons (not just loaded but ignored).

DeepThink Step 1 ロード後に `filter_relevant_lessons()` を呼んで
domain関連 lesson を抽出。Step 3 改善時に `verify_lesson_cited()` で
引用が反映されているかチェックする。
"""

from __future__ import annotations

import re
from typing import Iterable


_MIN_KEYPHRASE_LEN = 4    # citation matching minimum
_MIN_TRIGGER_TOKEN_LEN = 2  # Japanese-friendly trigger matching


def filter_relevant_lessons(
    user_input: str,
    all_lessons: list[dict],
) -> list[dict]:
    """Return lessons whose `trigger` field matches `user_input`.

    Matching strategy:
      1. lesson["trigger"] (free-text) を normalize して空白/句読点区切りトークンに
      2. 各トークン（>=2文字）が user_input に部分一致するなら match。
         日本語トークン（"徹底"、"PF" 等）を拾うため 2 文字許容。
      3. trigger が空 lesson は match から除外（一般 lesson は別途使用）
    """
    user_lower = (user_input or "").lower()
    if not user_lower:
        return []
    matched: list[dict] = []
    for lesson in all_lessons or []:
        trigger = (lesson.get("trigger") or "").strip()
        if not trigger:
            continue
        tokens = [
            t for t in re.split(r"[\s、。/,，。．・]+", trigger)
            if len(t) >= _MIN_TRIGGER_TOKEN_LEN
        ]
        if not tokens:
            continue
        if any(t.lower() in user_lower for t in tokens):
            matched.append(lesson)
    return matched


def _extract_keyphrases(lesson: dict) -> list[str]:
    """Extract keyphrases for citation matching.

    Sources (priority order):
      1. lesson["expected_action"] — what the lesson says to do
      2. lesson["key_kpis"] — measurable thresholds
      3. lesson["content"] の最初の改行までを 1 phrase として
    """
    phrases: list[str] = []
    ea = lesson.get("expected_action")
    if isinstance(ea, str) and len(ea) >= _MIN_KEYPHRASE_LEN:
        phrases.append(ea)
    kpis = lesson.get("key_kpis")
    if isinstance(kpis, list):
        for k in kpis:
            if isinstance(k, str) and len(k) >= _MIN_KEYPHRASE_LEN:
                phrases.append(k)
    content = lesson.get("content")
    if isinstance(content, str) and content.strip():
        lines = [line for line in content.splitlines() if line.strip()]
        if lines:
            first_line = lines[0].strip()
            if len(first_line) >= _MIN_KEYPHRASE_LEN:
                phrases.append(first_line)
    return phrases


_SLIDING_WINDOW_LEN = 8


def _phrase_matches(text: str, phrase: str) -> bool:
    """Loose substring match.

    Strategy (in order):
      1. exact substring
      2. token-level match (token >= 8 chars in text)
      3. sliding window of 8 contiguous chars from phrase appears in text
         （日本語の長い複合語に partial 一致を許容）
    """
    if not phrase:
        return False
    if phrase in text:
        return True
    tokens = re.split(r"[\s\-/,，。．・]+", phrase)
    longer_tokens = [t for t in tokens if len(t) >= _SLIDING_WINDOW_LEN]
    if any(t in text for t in longer_tokens):
        return True
    # Sliding window across the full phrase (after stripping whitespace runs).
    compact = re.sub(r"\s+", "", phrase)
    if len(compact) >= _SLIDING_WINDOW_LEN:
        for i in range(len(compact) - _SLIDING_WINDOW_LEN + 1):
            if compact[i:i + _SLIDING_WINDOW_LEN] in text:
                return True
    return False


def verify_lesson_cited(
    improvement_text: str,
    expected_lessons: Iterable[dict],
) -> tuple[bool, list[str]]:
    """Check that `improvement_text` cites at least each expected lesson.

    Returns
    -------
    (ok, missing_lesson_ids)
        ok=True iff every expected lesson has at least one keyphrase appearing
        in the improvement text. `missing_lesson_ids` lists ids that lacked
        any matching phrase.
    """
    text = improvement_text or ""
    missing: list[str] = []
    for lesson in expected_lessons or []:
        phrases = _extract_keyphrases(lesson)
        if not phrases:
            # No keyphrases extractable: treat as cited (cannot verify).
            continue
        if not any(_phrase_matches(text, p) for p in phrases):
            lesson_id = lesson.get("id") or lesson.get("date") or "unknown"
            missing.append(str(lesson_id))
    return (not missing, missing)


__all__ = [
    "filter_relevant_lessons",
    "verify_lesson_cited",
]
