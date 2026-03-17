"""Tests for KIK-550 hidden theme discovery.

Tests label_community, _extract_news_keyword, and discover_hidden_themes.
"""

import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.no_auto_mock


@pytest.fixture(autouse=True)
def reset_driver():
    import src.data.graph_store as gs
    gs._driver = None
    yield
    gs._driver = None


# ===================================================================
# label_community
# ===================================================================


class TestLabelCommunity:
    def test_sector_and_theme(self):
        from src.data.graph_query.community import label_community

        session = MagicMock()
        call_num = [0]

        def mock_run(query, **kwargs):
            call_num[0] += 1
            result = MagicMock()
            if call_num[0] == 1:  # sector
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "Technology", "cnt": 3}[k]
                result.single.return_value = rec
            else:  # theme
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "AI", "cnt": 2}[k]
                result.single.return_value = rec
            return result

        session.run.side_effect = mock_run
        label = label_community(["A", "B", "C"], session, fallback_id=0)
        assert label["name"] == "Technology x AI"
        assert label["source"] == "sector+theme"
        assert label["confidence"] > 0

    def test_sector_only(self):
        from src.data.graph_query.community import label_community

        session = MagicMock()
        call_num = [0]

        def mock_run(query, **kwargs):
            call_num[0] += 1
            result = MagicMock()
            if call_num[0] == 1:
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "Healthcare", "cnt": 2}[k]
                result.single.return_value = rec
            else:
                result.single.return_value = None
            return result

        session.run.side_effect = mock_run
        label = label_community(["A", "B"], session, fallback_id=1)
        assert label["name"] == "Healthcare"
        assert label["source"] == "sector"
        assert label["confidence"] > 0

    def test_theme_only(self):
        from src.data.graph_query.community import label_community

        session = MagicMock()
        call_num = [0]

        def mock_run(query, **kwargs):
            call_num[0] += 1
            result = MagicMock()
            if call_num[0] == 1:
                result.single.return_value = None
            else:
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "EV", "cnt": 2}[k]
                result.single.return_value = rec
            return result

        session.run.side_effect = mock_run
        label = label_community(["A", "B"], session, fallback_id=2)
        assert label["name"] == "EV"
        assert label["source"] == "theme"

    def test_news_keyword_fallback(self):
        from src.data.graph_query.community import label_community

        session = MagicMock()
        call_num = [0]

        def mock_run(query, **kwargs):
            call_num[0] += 1
            result = MagicMock()
            if call_num[0] <= 2:  # sector + theme queries
                result.single.return_value = None
                return result
            # news keyword query
            r1 = MagicMock()
            r1.__getitem__ = lambda s, k: {"title": "semiconductor demand rising fast"}[k]
            r2 = MagicMock()
            r2.__getitem__ = lambda s, k: {"title": "semiconductor chip shortage continues"}[k]
            return iter([r1, r2])

        session.run.side_effect = mock_run
        label = label_community(["A", "B"], session, fallback_id=3)
        assert label["source"] == "news_keyword"
        assert label["confidence"] == 0.3
        assert "semiconductor" in label["name"]

    def test_ultimate_fallback(self):
        from src.data.graph_query.community import label_community

        session = MagicMock()
        result = MagicMock()
        result.single.return_value = None
        session.run.return_value = result

        # Override for news query to return empty
        call_num = [0]

        def mock_run(query, **kwargs):
            call_num[0] += 1
            r = MagicMock()
            if call_num[0] <= 2:
                r.single.return_value = None
                return r
            return iter([])  # no news

        session.run.side_effect = mock_run
        label = label_community(["A"], session, fallback_id=7)
        assert label["name"] == "Community_7"
        assert label["confidence"] == 0.0
        assert label["source"] == "fallback"

    def test_empty_members(self):
        from src.data.graph_query.community import label_community

        session = MagicMock()
        label = label_community([], session, fallback_id=0)
        assert label["name"] == "Community_0"
        assert label["confidence"] == 0.0

    def test_confidence_calculation(self):
        from src.data.graph_query.community import label_community

        session = MagicMock()
        call_num = [0]

        def mock_run(query, **kwargs):
            call_num[0] += 1
            result = MagicMock()
            if call_num[0] == 1:  # all 4 members in same sector
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "Tech", "cnt": 4}[k]
                result.single.return_value = rec
            else:  # all 4 have same theme
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "AI", "cnt": 4}[k]
                result.single.return_value = rec
            return result

        session.run.side_effect = mock_run
        label = label_community(["A", "B", "C", "D"], session)
        # (4+4)/(2*4) = 1.0
        assert label["confidence"] == 1.0


# ===================================================================
# _extract_news_keyword
# ===================================================================


class TestExtractNewsKeyword:
    def test_extracts_common_word(self):
        from src.data.graph_query.community import _extract_news_keyword

        session = MagicMock()
        r1 = MagicMock()
        r1.__getitem__ = lambda s, k: {"title": "AI revolution drives growth"}[k]
        r2 = MagicMock()
        r2.__getitem__ = lambda s, k: {"title": "AI chips demand surges"}[k]
        session.run.return_value = iter([r1, r2])

        keyword = _extract_news_keyword(["A", "B"], session)
        # "AI" appears twice, should be extracted (case-insensitive → "ai")
        assert keyword is not None

    def test_returns_none_no_news(self):
        from src.data.graph_query.community import _extract_news_keyword

        session = MagicMock()
        session.run.return_value = iter([])
        assert _extract_news_keyword(["A"], session) is None

    def test_filters_stop_words(self):
        from src.data.graph_query.community import _extract_news_keyword

        session = MagicMock()
        r1 = MagicMock()
        r1.__getitem__ = lambda s, k: {"title": "the the the in on at"}[k]
        r2 = MagicMock()
        r2.__getitem__ = lambda s, k: {"title": "the the the in on at"}[k]
        session.run.return_value = iter([r1, r2])

        keyword = _extract_news_keyword(["A", "B"], session)
        assert keyword is None  # all stop words

    def test_japanese_stop_words_filtered(self):
        from src.data.graph_query.community import _extract_news_keyword

        session = MagicMock()
        r1 = MagicMock()
        r1.__getitem__ = lambda s, k: {"title": "半導体 の 需要 が 半導体 に"}[k]
        r2 = MagicMock()
        r2.__getitem__ = lambda s, k: {"title": "半導体 需要 拡大"}[k]
        session.run.return_value = iter([r1, r2])

        keyword = _extract_news_keyword(["A", "B"], session)
        # "半導体" appears 3 times (most frequent non-stop-word)
        assert keyword == "半導体"


# ===================================================================
# discover_hidden_themes
# ===================================================================


class TestDiscoverHiddenThemes:
    def test_returns_empty_no_driver(self):
        from src.data.graph_query.community import discover_hidden_themes

        with patch("src.data.graph_store._get_driver", return_value=None):
            assert discover_hidden_themes() == []

    def test_returns_empty_no_communities(self):
        from src.data.graph_query.community import discover_hidden_themes

        with patch("src.data.graph_query.community.get_communities", return_value=[]):
            with patch("src.data.graph_store._get_driver", return_value=MagicMock()):
                assert discover_hidden_themes() == []

    def test_discovers_news_keyword_themes(self):
        from src.data.graph_query.community import discover_hidden_themes

        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)

        communities = [
            {"id": "c0", "name": "?", "size": 3, "level": 0,
             "created_at": "", "members": ["A", "B", "C"]},
        ]

        call_num = [0]

        def mock_run(query, **kwargs):
            call_num[0] += 1
            result = MagicMock()
            if call_num[0] <= 2:  # sector + theme → None
                result.single.return_value = None
                return result
            # news → shared keyword
            r1 = MagicMock()
            r1.__getitem__ = lambda s, k: {"title": "yen weak yen depreciation"}[k]
            r2 = MagicMock()
            r2.__getitem__ = lambda s, k: {"title": "yen impact on exports"}[k]
            return iter([r1, r2])

        session.run.side_effect = mock_run

        import src.data.graph_store as gs
        gs._driver = driver
        with patch("src.data.graph_query.community.get_communities", return_value=communities):
            discoveries = discover_hidden_themes()

        assert len(discoveries) == 1
        assert discoveries[0]["source"] == "news_keyword"
        assert discoveries[0]["size"] == 3
        gs._driver = None


# ===================================================================
# _auto_name_community backward compatibility
# ===================================================================


class TestAutoNameBackwardCompat:
    def test_returns_string(self):
        """_auto_name_community should still return a plain string."""
        from src.data.graph_query.community import _auto_name_community

        session = MagicMock()
        call_num = [0]

        def mock_run(query, **kwargs):
            call_num[0] += 1
            result = MagicMock()
            if call_num[0] == 1:
                rec = MagicMock()
                rec.__getitem__ = lambda s, k: {"name": "Tech", "cnt": 2}[k]
                result.single.return_value = rec
            else:
                result.single.return_value = None
            return result

        session.run.side_effect = mock_run
        name = _auto_name_community(["A", "B"], session, fallback_id=0)
        assert isinstance(name, str)
        assert name == "Tech"
