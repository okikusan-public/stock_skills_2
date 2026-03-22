"""Lesson community classification and query (KIK-571).

Classifies lessons into thematic communities (判断バイアス/売買ルール/マクロ戦略)
using keyword-based rules. Provides Neo4j integration for
LessonCommunity nodes and CATEGORIZED_AS relationships.
"""

from typing import Optional

from src.data.lesson_conflict import tokenize


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

_COMMUNITIES = {
    "判断バイアス": [
        "バイアス", "固定観念", "鵜呑み", "機会損失", "過多", "禁止",
        "慎重", "楽観", "悲観", "思い込み", "先入観", "過信",
        "パニック", "感情", "衝動", "焦り", "保守", "同日",
    ],
    "売買ルール": [
        "損切り", "利確", "カタリスト", "エントリー", "閾値",
        "rsi", "vix", "条件", "ルール", "タイミング", "購入",
        "売却", "ストップ", "トレール", "ポジション", "追加",
        "分割", "ナンピン", "打ち止め", "停止", "出来高",
    ],
    "マクロ戦略": [
        "原油", "金利", "etf", "ローテーション", "マクロ",
        "インフレ", "ヘッジ", "為替", "円安", "円高",
        "債券", "イールド", "セクター", "景気", "リセッション",
        "fomc", "利上げ", "利下げ",
    ],
}


def classify_lesson(content: str = "", trigger: str = "") -> str:
    """Classify a lesson into a thematic community.

    Uses keyword matching on content + trigger text.
    Returns community name or "その他" if no clear match.
    """
    text = f"{trigger} {content}".lower()
    tokens = set(tokenize(text))

    scores: dict[str, int] = {}
    for community, keywords in _COMMUNITIES.items():
        score = 0
        for kw in keywords:
            kw_lower = kw.lower()
            # Token match
            if kw_lower in tokens:
                score += 2
            # Substring match (for compound words)
            elif kw_lower in text:
                score += 1
        if score > 0:
            scores[community] = score

    if not scores:
        return "その他"

    return max(scores, key=scores.get)


# ---------------------------------------------------------------------------
# Neo4j operations
# ---------------------------------------------------------------------------

def merge_lesson_community(note_id: str, community_name: str) -> bool:
    """Create LessonCommunity node and CATEGORIZED_AS relationship."""
    try:
        from src.data.graph_store import _common
        if _common._get_mode() == "off":
            return False
        driver = _common._get_driver()
        if driver is None:
            return False
        with driver.session() as session:
            session.run(
                "MERGE (lc:LessonCommunity {name: $name})",
                name=community_name,
            )
            session.run(
                "MATCH (n:Note {id: $note_id}) "
                "MATCH (lc:LessonCommunity {name: $name}) "
                "MERGE (n)-[:CATEGORIZED_AS]->(lc)",
                note_id=note_id,
                name=community_name,
            )
        return True
    except Exception:
        return False


def get_lessons_by_theme(theme: str, limit: int = 5) -> list[dict]:
    """Get lessons belonging to a specific LessonCommunity.

    Returns list of {id, content, trigger, expected_action, date, symbol}.
    """
    try:
        from src.data.graph_query._common import _get_driver
        driver = _get_driver()
        if driver is None:
            return []
        with driver.session() as session:
            result = session.run(
                "MATCH (n:Note {type: 'lesson'})-[:CATEGORIZED_AS]->"
                "(lc:LessonCommunity {name: $theme}) "
                "RETURN n.id AS id, n.content AS content, "
                "n.trigger AS trigger, n.expected_action AS expected_action, "
                "n.date AS date "
                "ORDER BY n.date DESC LIMIT $limit",
                theme=theme,
                limit=limit,
            )
            return [dict(r) for r in result]
    except Exception:
        return []


def get_all_lesson_communities() -> list[dict]:
    """Get all LessonCommunity nodes with their lesson counts.

    Returns list of {name, count}.
    """
    try:
        from src.data.graph_query._common import _get_driver
        driver = _get_driver()
        if driver is None:
            return []
        with driver.session() as session:
            result = session.run(
                "MATCH (lc:LessonCommunity) "
                "OPTIONAL MATCH (n:Note)-[:CATEGORIZED_AS]->(lc) "
                "RETURN lc.name AS name, count(n) AS count "
                "ORDER BY count DESC"
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Intent → theme mapping (for KIK-569 integration)
# ---------------------------------------------------------------------------

_INTENT_THEME_MAP = {
    "売買": "売買ルール",
    "損切り": "売買ルール",
    "利確": "売買ルール",
    "買い": "売買ルール",
    "売り": "売買ルール",
    "エントリー": "売買ルール",
    "ポジション": "売買ルール",
    "ヘルスチェック": "売買ルール",
    "health": "売買ルール",
    "adjust": "売買ルール",
    "市況": "マクロ戦略",
    "マクロ": "マクロ戦略",
    "金利": "マクロ戦略",
    "vix": "マクロ戦略",
    "為替": "マクロ戦略",
    "相場": "マクロ戦略",
    "バイアス": "判断バイアス",
    "判断": "判断バイアス",
    "分析": "判断バイアス",
}


def infer_theme_from_input(user_input: str) -> Optional[str]:
    """Infer the most relevant LessonCommunity from user input."""
    if not user_input:
        return None
    text = user_input.lower()
    tokens = set(tokenize(text))
    scores: dict[str, int] = {}
    for keyword, theme in _INTENT_THEME_MAP.items():
        if keyword.lower() in tokens or keyword.lower() in text:
            scores[theme] = scores.get(theme, 0) + 1
    if not scores:
        return None
    return max(scores, key=scores.get)
