"""Tests for src/data/embedding_client.py (KIK-420).

All tests mock `requests` so no TEI service is needed.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.data import embedding_client

pytestmark = pytest.mark.no_auto_mock


@pytest.fixture(autouse=True)
def _reset():
    """Reset availability cache before each test."""
    embedding_client.reset_cache()
    yield
    embedding_client.reset_cache()


# ===================================================================
# is_available
# ===================================================================


class TestIsAvailable:
    @patch("src.data.embedding_client.requests")
    def test_available_when_health_ok(self, mock_req):
        mock_req.get.return_value = MagicMock(status_code=200)
        assert embedding_client.is_available() is True
        mock_req.get.assert_called_once()

    @patch("src.data.embedding_client.requests")
    def test_unavailable_when_health_500(self, mock_req):
        mock_req.get.return_value = MagicMock(status_code=500)
        assert embedding_client.is_available() is False

    @patch("src.data.embedding_client.requests")
    def test_unavailable_on_connection_error(self, mock_req):
        mock_req.get.side_effect = ConnectionError("refused")
        assert embedding_client.is_available() is False

    @patch("src.data.embedding_client.requests")
    def test_unavailable_on_timeout(self, mock_req):
        mock_req.get.side_effect = TimeoutError("timeout")
        assert embedding_client.is_available() is False

    @patch("src.data.embedding_client.requests")
    def test_cache_reuses_result(self, mock_req):
        """Second call within TTL should not make another request."""
        mock_req.get.return_value = MagicMock(status_code=200)
        assert embedding_client.is_available() is True
        assert embedding_client.is_available() is True
        assert mock_req.get.call_count == 1  # cached

    @patch("src.data.embedding_client.requests")
    def test_cache_expires(self, mock_req):
        """After TTL expires, should re-check."""
        mock_req.get.return_value = MagicMock(status_code=200)
        embedding_client.is_available()
        # Force cache expiry
        embedding_client._available_checked_at = 0.0
        embedding_client.is_available()
        assert mock_req.get.call_count == 2


# ===================================================================
# get_embedding
# ===================================================================


class TestGetEmbedding:
    @patch("src.data.embedding_client.requests")
    def test_returns_vector_on_success(self, mock_req):
        fake_vec = [0.1] * 384
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = [fake_vec]
        mock_req.post.return_value = mock_resp

        result = embedding_client.get_embedding("test text")
        assert result == fake_vec
        mock_req.post.assert_called_once()

    @patch("src.data.embedding_client.requests")
    def test_returns_none_on_error(self, mock_req):
        mock_req.post.return_value = MagicMock(status_code=500)
        assert embedding_client.get_embedding("test") is None

    @patch("src.data.embedding_client.requests")
    def test_returns_none_on_timeout(self, mock_req):
        mock_req.post.side_effect = TimeoutError("timeout")
        assert embedding_client.get_embedding("test") is None

    @patch("src.data.embedding_client.requests")
    def test_returns_none_on_empty_response(self, mock_req):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = []
        mock_req.post.return_value = mock_resp
        assert embedding_client.get_embedding("test") is None

    def test_returns_none_on_empty_text(self):
        assert embedding_client.get_embedding("") is None


# ===================================================================
# reset_cache
# ===================================================================


class TestResetCache:
    @patch("src.data.embedding_client.requests")
    def test_reset_clears_cache(self, mock_req):
        mock_req.get.return_value = MagicMock(status_code=200)
        embedding_client.is_available()
        embedding_client.reset_cache()
        assert embedding_client._available is None
        assert embedding_client._available_checked_at == 0.0
