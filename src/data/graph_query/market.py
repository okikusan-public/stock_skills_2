"""MarketContext/Indicator/UpcomingEvent/ThemeTrend graph queries.

Extracted from graph_query.py during KIK-508 submodule split.
ThemeTrend queries added in KIK-603.
"""

import json
from typing import Optional

from src.data.graph_query import _common


# ---------------------------------------------------------------------------
# 4. Recent market context
# ---------------------------------------------------------------------------

def get_recent_market_context() -> Optional[dict]:
    """Get the most recent MarketContext node.

    Returns dict with keys: date, indices (parsed from JSON).
    None if not found.
    """
    driver = _common._get_driver()
    if driver is None:
        return None
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (m:MarketContext) "
                "RETURN m.date AS date, m.indices AS indices "
                "ORDER BY m.date DESC LIMIT 1",
            )
            record = result.single()
            if record is None:
                return None
            indices_raw = record["indices"]
            try:
                indices = json.loads(indices_raw) if indices_raw else []
            except (json.JSONDecodeError, TypeError):
                indices = []
            return {"date": record["date"], "indices": indices}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 11. Upcoming events (KIK-413)
# ---------------------------------------------------------------------------

def get_upcoming_events(limit: int = 10, within_days: int = None) -> list[dict]:
    """Get UpcomingEvent nodes from the most recent MarketContext.

    Parameters
    ----------
    limit : int
        Maximum number of events to return.
    within_days : int, optional
        If provided, filter events to those occurring within N days from today.

    Returns list of {date, text}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            if within_days is not None:
                from datetime import date, timedelta
                today = date.today().isoformat()
                until = (date.today() + timedelta(days=within_days)).isoformat()
                result = session.run(
                    "MATCH (m:MarketContext)-[:HAS_EVENT]->(e:UpcomingEvent) "
                    "WHERE e.date >= $today AND e.date <= $until "
                    "RETURN e.date AS date, e.text AS text "
                    "ORDER BY e.date LIMIT $limit",
                    today=today, until=until, limit=limit,
                )
            else:
                result = session.run(
                    "MATCH (m:MarketContext)-[:HAS_EVENT]->(e:UpcomingEvent) "
                    "RETURN e.date AS date, e.text AS text "
                    "ORDER BY m.date DESC, e.id LIMIT $limit",
                    limit=limit,
                )
            return [dict(r) for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 15. Theme trend history (KIK-603)
# ---------------------------------------------------------------------------

def get_theme_trends(limit: int = 20, region: str = "") -> list[dict]:
    """Get recent theme trend history.

    Parameters
    ----------
    limit : int
        Maximum number of records to return.
    region : str
        If provided, filter by region.

    Returns list of {date, theme, confidence, reason, rank, region}.
    """
    driver = _common._get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            if region:
                result = session.run(
                    "MATCH (tt:ThemeTrend) "
                    "WHERE tt.region = $region "
                    "RETURN tt.date AS date, tt.theme AS theme, "
                    "       tt.confidence AS confidence, tt.reason AS reason, "
                    "       tt.rank AS rank, tt.region AS region "
                    "ORDER BY tt.date DESC, tt.rank ASC "
                    "LIMIT $limit",
                    region=region, limit=limit,
                )
            else:
                result = session.run(
                    "MATCH (tt:ThemeTrend) "
                    "RETURN tt.date AS date, tt.theme AS theme, "
                    "       tt.confidence AS confidence, tt.reason AS reason, "
                    "       tt.rank AS rank, tt.region AS region "
                    "ORDER BY tt.date DESC, tt.rank ASC "
                    "LIMIT $limit",
                    limit=limit,
                )
            return [dict(r) for r in result]
    except Exception:
        return []


def get_theme_trend_diff() -> dict:
    """Compare the latest two theme detections to find rising/falling themes.

    Returns dict with keys:
        latest_date: str, previous_date: str,
        rising: list[str] (themes in latest but not previous),
        falling: list[str] (themes in previous but not latest),
        stable: list[str] (themes in both).
    Empty dict if fewer than 2 detection dates.
    """
    driver = _common._get_driver()
    if driver is None:
        return {}
    try:
        with driver.session() as session:
            # Get the two most recent distinct dates
            date_result = session.run(
                "MATCH (tt:ThemeTrend) "
                "RETURN DISTINCT tt.date AS date "
                "ORDER BY tt.date DESC LIMIT 2"
            )
            dates = [r["date"] for r in date_result]
            if len(dates) < 2:
                return {}

            latest_date, previous_date = dates[0], dates[1]

            # Get themes for each date
            latest_result = session.run(
                "MATCH (tt:ThemeTrend {date: $date}) "
                "RETURN tt.theme AS theme",
                date=latest_date,
            )
            latest_themes = {r["theme"] for r in latest_result}

            previous_result = session.run(
                "MATCH (tt:ThemeTrend {date: $date}) "
                "RETURN tt.theme AS theme",
                date=previous_date,
            )
            previous_themes = {r["theme"] for r in previous_result}

            return {
                "latest_date": latest_date,
                "previous_date": previous_date,
                "rising": sorted(latest_themes - previous_themes),
                "falling": sorted(previous_themes - latest_themes),
                "stable": sorted(latest_themes & previous_themes),
            }
    except Exception:
        return {}
