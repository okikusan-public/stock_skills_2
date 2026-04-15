"""Context modules -- graph context injection and screening enrichment (KIK-517).

Sub-modules:
  auto_context.py: Auto graph context injection (KIK-411/420/427)
  grok_context.py: Grok API prompt context (KIK-488)
  screening_context.py: GraphRAG context for screening output (KIK-452)
  screen_annotator.py: Screen result enrichment with sell/note context (KIK-418/419)
  summary_builder.py: Semantic summary builders for Neo4j vector search (KIK-420)
  constraint_extractor.py: Lesson constraint extraction for plan-check flow (KIK-596)
"""

# Key public functions re-exported for convenience
from src.data.context.auto_context import get_context  # noqa: F401
from src.data.context.grok_context import (  # noqa: F401
    get_stock_context,
    get_industry_context,
    get_market_context,
    get_business_context,
)
from src.data.context.screening_context import get_screening_graph_context  # noqa: F401
from src.data.context.screen_annotator import annotate_results  # noqa: F401
from src.data.context.constraint_extractor import (  # noqa: F401
    extract_constraints,
    format_constraints_markdown,
)
from src.data.context.summary_builder import (  # noqa: F401
    build_screen_summary,
    build_report_summary,
    build_trade_summary,
    build_health_summary,
    build_research_summary,
    build_market_context_summary,
    build_note_summary,
    build_watchlist_summary,
    build_stress_test_summary,
    build_forecast_summary,
)
