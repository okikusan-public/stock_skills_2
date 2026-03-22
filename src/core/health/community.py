"""Community concentration analysis for portfolio health checks (KIK-549, KIK-576).

Computes community-level portfolio concentration using Neo4j graph data.
"""


def _compute_community_concentration(
    results: list[dict],
    eval_by_symbol: dict[str, float],
    total_value: float,
) -> dict | None:
    """Compute community-level portfolio concentration (KIK-549).

    Returns dict with hhi, community_weights, community_members, warnings.
    None if graph unavailable or no community data.
    """
    try:
        from src.data.graph_query.community import get_stock_community
    except ImportError:
        return None

    community_weights: dict[str, float] = {}
    community_members: dict[str, list[str]] = {}

    for r in results:
        sym = r["symbol"]
        try:
            comm = get_stock_community(sym)
        except Exception:
            continue
        if comm is None:
            continue
        name = comm["name"]
        weight = eval_by_symbol.get(sym, 0) / total_value if total_value > 0 else 0
        community_weights[name] = community_weights.get(name, 0) + weight
        community_members.setdefault(name, []).append(sym)

    if not community_weights:
        return None

    # Community HHI
    weights = list(community_weights.values())
    hhi = sum(w * w for w in weights)

    # Concentration warnings
    warnings = []
    for name, weight in community_weights.items():
        members = community_members[name]
        if len(members) < 2:
            continue
        if weight > 0.5:
            warnings.append({
                "community": name,
                "weight": round(weight, 3),
                "count": len(members),
                "members": members,
                "message": "実質的に分散できていない可能性",
            })
        elif weight > 0.3:
            warnings.append({
                "community": name,
                "weight": round(weight, 3),
                "count": len(members),
                "members": members,
                "message": "コミュニティ集中やや高め",
            })

    return {
        "hhi": round(hhi, 4),
        "community_weights": {
            k: round(v, 3)
            for k, v in sorted(community_weights.items(), key=lambda x: -x[1])
        },
        "community_members": community_members,
        "warnings": warnings,
    }
