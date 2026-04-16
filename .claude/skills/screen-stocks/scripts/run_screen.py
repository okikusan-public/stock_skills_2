#!/usr/bin/env python3
"""Entry point for the screen-stocks skill (KIK-514: Registry pattern).

Supports two modes:
  --mode query  (default): Uses yfinance EquityQuery -- no symbol list needed.
  --mode legacy          : Uses the original ValueScreener
                           with predefined symbol lists per market.
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from scripts.common import try_import, HAS_HISTORY_STORE, HAS_GRAPH_QUERY as _HAS_GQ, HAS_GRAPH_STORE as _HAS_GS, print_context, print_suggestions
from src.data import yahoo_client
from src.core.screening.screener import ValueScreener
from src.core.screening.screener_registry import (
    build_default_registry, RegionConfig, run_screener_with_spec,
)
from src.output.formatter import format_markdown, format_auto_theme_header
from src.markets.japan import JapanMarket
from src.markets.us import USMarket
from src.markets.asean import ASEANMarket

# Module availability from common.py (KIK-448); import specific functions when available
HAS_HISTORY = HAS_HISTORY_STORE
if HAS_HISTORY:
    from src.data.history import save_screening

HAS_GRAPH_QUERY = _HAS_GQ
if HAS_GRAPH_QUERY:
    from src.data.graph_query import get_screening_frequency

HAS_GRAPH_STORE = _HAS_GS
if HAS_GRAPH_STORE:
    from src.data.graph_store import merge_theme_trend

HAS_ANNOTATOR, _an = try_import("src.data.context.screen_annotator", "annotate_results")
if HAS_ANNOTATOR: annotate_results = _an["annotate_results"]

HAS_SCREENING_CTX, _sctx = try_import(
    "src.data.context.screening_context", "get_screening_graph_context"
)
if HAS_SCREENING_CTX:
    get_screening_graph_context = _sctx["get_screening_graph_context"]

HAS_SCREENING_SUMMARY, _ssum = try_import(
    "src.output.screening_summary_formatter", "format_screening_summary"
)
if HAS_SCREENING_SUMMARY:
    format_screening_summary = _ssum["format_screening_summary"]


# --- Registry & RegionConfig (KIK-514) ---
_registry = build_default_registry()
_region_config = RegionConfig()

# Legacy market classes (only used by run_legacy_mode)
MARKETS = {
    "japan": JapanMarket,
    "us": USMarket,
    "asean": ASEANMarket,
}

VALID_SECTORS = [
    "Technology",
    "Financial Services",
    "Healthcare",
    "Consumer Cyclical",
    "Industrials",
    "Communication Services",
    "Consumer Defensive",
    "Energy",
    "Basic Materials",
    "Real Estate",
    "Utilities",
]


def _annotate(results):
    """Apply screen annotations (KIK-418/419). Returns (results, excluded_count)."""
    if not HAS_ANNOTATOR or not results:
        return results, 0
    try:
        return annotate_results(results)
    except Exception:
        return results, 0


def _print_recurring_picks(results):
    """Print recurring picks highlight if graph data available (KIK-406)."""
    if not HAS_GRAPH_QUERY or not results:
        return
    try:
        symbols = [r.get("symbol") for r in results if r.get("symbol")]
        if not symbols:
            return
        freq = get_screening_frequency(symbols)
        # Only show symbols that appeared 2+ times (current run counts as new)
        recurring = {s: c for s, c in freq.items() if c >= 2}
        if recurring:
            print("**再出現銘柄** (過去のスクリーニングにも登場):")
            for sym, cnt in sorted(recurring.items(), key=lambda x: -x[1]):
                print(f"  - {sym}: 過去{cnt}回出現")
            print()
    except Exception:
        pass


def _print_graphrag_context(results):
    """Print GraphRAG context from knowledge graph (KIK-452, KIK-532).

    Outputs structured Neo4j data for Claude Code to interpret.
    Grok API call removed in KIK-532 — Claude Code LLM synthesizes context.
    """
    if not HAS_SCREENING_CTX or not HAS_SCREENING_SUMMARY or not results:
        return
    try:
        symbols = [r.get("symbol") for r in results if r.get("symbol")]
        sectors = list({r.get("sector") for r in results if r.get("sector")})
        context = get_screening_graph_context(symbols, sectors)
        if not context.get("has_data"):
            return
        summary = format_screening_summary(context)
        if summary:
            print(summary)
    except Exception:
        pass


def _save_history(preset, region_code, results, sector=None, theme=None):
    """Save screening history (KIK-406)."""
    if HAS_HISTORY and results:
        try:
            save_screening(preset=preset, region=region_code, results=results, sector=sector, theme=theme)
        except Exception as e:
            print(f"Warning: 履歴保存失敗: {e}", file=sys.stderr)


def _run_single_region(spec, region_code, args):
    """Run screening for a single region using ScreenerSpec (KIK-514).

    Handles: header printing, screener execution, annotation, formatting,
    recurring picks, GraphRAG context, and history saving.
    """
    region_name = _region_config.display_name(region_code)
    sector_label = f" [{args.sector}]" if args.sector else ""
    theme_label = f" [{args.theme}]" if args.theme else ""

    # Momentum has special display name with submode
    if spec.preset == "momentum":
        submode = getattr(args, "submode", None) or "surge"
        submode_labels = {"stable": "安定上昇", "surge": "急騰ブレイクアウト"}
        label = submode_labels.get(submode, submode)
        display = f"モメンタム（{label}）"
    else:
        display = spec.display_name

    print(f"\n## {region_name} - {display}{sector_label}{theme_label} スクリーニング結果\n")

    # Step messages
    step1, step2_tmpl = spec.step_messages
    if step1:
        print(step1)

    # Execute screening via registry
    results = run_screener_with_spec(
        spec, yahoo_client, region_code, _region_config,
        top_n=args.top, sector=args.sector, theme=args.theme,
        args=args,
    )
    results, excluded = _annotate(results)

    if step2_tmpl:
        print(f"{step2_tmpl.format(n=len(results))}\n")
    if excluded:
        print(f"※ 直近売却済み {excluded}銘柄を除外\n")

    # Extra warnings (e.g. small-cap liquidity)
    for warning in spec.extra_warnings:
        print(f"{warning}\n")

    # Format and print results
    print(spec.formatter(results))
    _print_recurring_picks(results)
    _print_graphrag_context(results)
    _save_history(spec.preset, region_code, results, sector=args.sector, theme=args.theme)
    print()


def run_trending_mode(args):
    """Run trending stock screening using Grok X search."""
    from src.output.formatter import format_trending_markdown

    try:
        from src.data import grok_client as gc
        if not gc.is_available():
            print("Error: trending preset requires XAI_API_KEY environment variable.")
            print("Set: export XAI_API_KEY=your-api-key")
            sys.exit(1)
    except ImportError:
        print("Error: grok_client module not available.")
        sys.exit(1)

    region_key = args.region.lower()
    first_region = _region_config.expand(region_key)[0]
    region_name = _region_config.display_name(first_region)
    theme_label = f" [{args.theme}]" if args.theme else ""

    print(f"\n## {region_name} - Xトレンド銘柄{theme_label} スクリーニング結果\n")
    print("Step 1: X (Twitter) でトレンド銘柄を検索中...")

    from src.core.screening.screener import TrendingScreener
    screener = TrendingScreener(yahoo_client, gc)
    results, market_context = screener.screen(
        region=region_key, theme=args.theme, top_n=args.top,
    )

    results, excluded = _annotate(results)
    print(f"Step 2: {len(results)}銘柄のファンダメンタルズを取得・スコアリング完了\n")
    if excluded:
        print(f"※ 直近売却済み {excluded}銘柄を除外\n")
    print(format_trending_markdown(results, market_context))

    _print_recurring_picks(results)
    _print_graphrag_context(results)
    _save_history("trending", region_key, results, theme=args.theme)
    print()


def run_auto_theme_mode(args):
    """Run auto-theme mode: detect trending themes via Grok, then screen each (KIK-440)."""
    try:
        from src.data import grok_client as gc
        if not gc.is_available():
            print("Error: --auto-theme requires XAI_API_KEY environment variable.")
            print("Set: export XAI_API_KEY=your-api-key")
            sys.exit(1)
    except ImportError:
        print("Error: grok_client module not available.")
        sys.exit(1)

    region_key = args.region.lower()
    regions = _region_config.expand(region_key)
    first_region = regions[0]
    region_name = _region_config.display_name(first_region)

    print(f"\n## {region_name} - トレンドテーマ自動検出 + スクリーニング\n")
    print("Step 1: Grok でトレンドテーマを検出中...")

    grok_result = gc.get_trending_themes(region=region_key, timeout=60)
    all_themes = grok_result.get("themes", [])

    if not all_themes:
        print("トレンドテーマを検出できませんでした。")
        return

    # Validate against themes.yaml
    try:
        from src.core.screening.query_builder import load_themes
        valid_theme_keys = set(load_themes().keys())
    except Exception:
        valid_theme_keys = set()

    if valid_theme_keys:
        active_themes = [t for t in all_themes if t["theme"] in valid_theme_keys]
        skipped_themes = [t for t in all_themes if t["theme"] not in valid_theme_keys]
    else:
        active_themes = all_themes
        skipped_themes = []

    print(format_auto_theme_header(active_themes, skipped_themes))

    if not active_themes:
        print("有効なテーマが見つかりませんでした（すべて未対応テーマ）。")
        return

    # Save theme trends to Neo4j (KIK-603)
    if HAS_GRAPH_STORE:
        try:
            from datetime import date as _date
            today = _date.today().isoformat()
            for i, t in enumerate(active_themes):
                merge_theme_trend(
                    theme=t["theme"],
                    date=today,
                    confidence=t.get("confidence", 0.0),
                    reason=t.get("reason", ""),
                    rank=i + 1,
                    region=region_key,
                )
        except Exception:
            pass  # graceful degradation

    # Screen each theme using registry (KIK-514)
    spec = _registry.get(args.preset)

    for theme_info in active_themes:
        theme_key = theme_info["theme"]
        print(f"\n### テーマ: {theme_key}\n")

        for region_code in regions:
            rname = _region_config.display_name(region_code)

            results = run_screener_with_spec(
                spec, yahoo_client, region_code, _region_config,
                top_n=args.top, sector=args.sector, theme=theme_key,
                args=args,
            )
            results, excluded = _annotate(results)
            print(f"{rname}: {len(results)}銘柄")
            if excluded:
                print(f"※ 直近売却済み {excluded}銘柄を除外")
            if results:
                print(spec.formatter(results))

            _print_recurring_picks(results)
            _print_graphrag_context(results)
            _save_history(args.preset, region_code, results, sector=args.sector, theme=theme_key)

    print()


def run_query_mode(args):
    """Run screening using EquityQuery (default mode)."""
    # auto-theme dispatch (KIK-440)
    if getattr(args, "auto_theme", False):
        run_auto_theme_mode(args)
        return

    region_key = args.region.lower()
    regions = _region_config.expand(region_key)

    spec = _registry.get(args.preset)

    # trending preset uses TrendingScreener (Grok-based) — special flow
    if spec.category == "special":
        run_trending_mode(args)
        return

    # with-pullback is a special mode for QueryScreener presets
    if args.with_pullback and spec.category == "query":
        from src.output.formatter import format_pullback_markdown
        from src.core.screening.screener import QueryScreener

        screener = QueryScreener(yahoo_client)
        for region_code in regions:
            region_name = _region_config.display_name(region_code)
            sector_label = f" [{args.sector}]" if args.sector else ""
            theme_label = f" [{args.theme}]" if args.theme else ""
            results = screener.screen(
                region=region_code,
                preset=args.preset,
                sector=args.sector,
                theme=args.theme,
                top_n=args.top,
                with_pullback=True,
            )
            results, excluded = _annotate(results)
            pullback_label = " + 押し目フィルタ"
            print(f"\n## {region_name} - {args.preset}{sector_label}{theme_label}{pullback_label} スクリーニング結果 (EquityQuery)\n")
            if excluded:
                print(f"※ 直近売却済み {excluded}銘柄を除外\n")
            print(format_pullback_markdown(results))
            _print_recurring_picks(results)
            _print_graphrag_context(results)
            _save_history(args.preset, region_code, results, sector=args.sector, theme=args.theme)
            print()
        return

    # Standard flow: use ScreenerSpec for all presets (KIK-514)
    for region_code in regions:
        _run_single_region(spec, region_code, args)


def run_legacy_mode(args):
    """Run screening using the original ValueScreener."""
    print(
        "⚠️  [DEPRECATED] --mode legacy は非推奨です。"
        " QueryScreener (デフォルト) を使用してください。"
        " --mode legacy は将来削除予定です。"
    )
    # Map region to legacy market names
    region_to_market = {
        "japan": "japan",
        "jp": "japan",
        "us": "us",
        "asean": "asean",
        "all": "all",
    }
    market_key = region_to_market.get(args.region.lower())
    if market_key is None:
        print(f"Error: Legacy mode only supports japan/us/asean/all. Got: {args.region}")
        print("Use --mode query for other regions.")
        sys.exit(1)

    if market_key == "all":
        markets_to_run = list(MARKETS.items())
    else:
        if market_key not in MARKETS:
            print(f"Error: Unknown market '{market_key}'")
            sys.exit(1)
        markets_to_run = [(market_key, MARKETS[market_key])]

    client = yahoo_client

    for market_name, market_cls in markets_to_run:
        market = market_cls()

        screener = ValueScreener(client, market)
        results = screener.screen(preset=args.preset, top_n=args.top)
        results, excluded = _annotate(results)
        print(f"\n## {market.name} - {args.preset} スクリーニング結果\n")
        if excluded:
            print(f"※ 直近売却済み {excluded}銘柄を除外\n")
        print(format_markdown(results))
        _save_history(args.preset, market_name, results)
        print()


def main():
    parser = argparse.ArgumentParser(description="割安株スクリーニング")

    # --region is the primary argument; --market is kept for backward compatibility
    parser.add_argument(
        "--region",
        default=None,
        help="Region/market to screen (e.g. japan, us, asean, sg, hk, kr, tw, cn)",
    )
    parser.add_argument(
        "--market",
        default=None,
        help="(Legacy) Alias for --region. Kept for backward compatibility.",
    )
    parser.add_argument(
        "--preset",
        default="value",
        choices=_registry.list_presets(),
    )
    parser.add_argument(
        "--submode",
        default=None,
        choices=["stable", "surge"],
        help="Sub-mode for momentum preset: 'stable' (steady uptrend) or 'surge' (breakout). Default: surge.",
    )
    parser.add_argument(
        "--sector",
        default=None,
        help=f"Sector filter. Options: {', '.join(VALID_SECTORS)}",
    )
    parser.add_argument(
        "--theme",
        default=None,
        help="Theme filter (e.g., ai, ev, defense, cloud-saas). Supported by all presets except trending/pullback/alpha.",
    )
    parser.add_argument(
        "--auto-theme",
        action="store_true",
        default=False,
        help="Grok APIでトレンドテーマを自動検出し、各テーマでスクリーニングを実行。XAI_API_KEY必須。",
    )
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument(
        "--with-pullback",
        action="store_true",
        default=False,
        help="任意プリセットにテクニカル押し目フィルタを追加適用",
    )
    parser.add_argument(
        "--mode",
        default="query",
        choices=["query", "legacy"],
        help="Screening mode: 'query' (EquityQuery, default) or 'legacy' (symbol list based)",
    )

    args = parser.parse_args()

    # Resolve --region from --market if --region not given
    if args.region is None:
        args.region = args.market if args.market else "japan"

    # Normalize region
    args.region = args.region.lower()

    # Validate sector
    if args.sector is not None:
        # Allow case-insensitive matching
        matched = None
        for s in VALID_SECTORS:
            if s.lower() == args.sector.lower():
                matched = s
                break
        if matched is None:
            print(f"Warning: Unknown sector '{args.sector}'. Valid sectors:")
            for s in VALID_SECTORS:
                print(f"  - {s}")
            sys.exit(1)
        args.sector = matched

    # Validate theme (KIK-439) — use registry for theme support check
    if args.theme is not None:
        spec = _registry.get(args.preset)
        if not spec.supports_theme:
            print(f"Warning: --theme is not supported with --preset {args.preset}. Ignoring --theme.")
            args.theme = None
        else:
            try:
                from src.core.screening.query_builder import load_themes
                valid_themes = load_themes()
                if args.theme not in valid_themes:
                    print(f"Warning: Unknown theme '{args.theme}'. Valid themes:")
                    for key, td in sorted(valid_themes.items()):
                        print(f"  - {key}: {td.get('description', '')}")
                    sys.exit(1)
            except Exception:
                pass  # Graceful degradation if themes.yaml is unavailable

    # Validate --auto-theme (KIK-440)
    if args.auto_theme and args.theme:
        print("Error: --auto-theme と --theme は同時に使用できません。")
        sys.exit(1)
    if args.auto_theme:
        spec = _registry.get(args.preset)
        if not spec.supports_theme:
            print(f"Warning: --auto-theme は --preset {args.preset} と併用できません。--auto-theme を無視します。")
            args.auto_theme = False

    # Legacy mode check — use registry (KIK-514)
    if args.mode == "legacy":
        spec = _registry.get(args.preset)
        if not spec.supports_legacy:
            print(f"Note: {args.preset} preset requires query mode. Switching to --mode query.")
            args.mode = "query"

    # Context retrieval (KIK-465)
    print_context(f"screen {args.region} {args.preset}")

    if args.mode == "query":
        run_query_mode(args)
    else:
        run_legacy_mode(args)

    # Proactive suggestions (KIK-465)
    print_suggestions(context_summary=f"スクリーニング完了: {args.preset} {args.region}")


if __name__ == "__main__":
    main()
