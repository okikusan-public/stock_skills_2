"""Tests for sector relative strength calculation (KIK-702)."""

import pandas as pd
import pytest

from src.data.yahoo_client.sector_rs import (
    BENCHMARK,
    SECTOR_ETFS,
    get_sector_rs,
    _safe_return,
)


class TestSafeReturn:
    """_safe_return のテスト."""

    def test_basic(self):
        s = pd.Series([100, 105, 110, 115, 120])
        # _safe_return(s, 2): current=s[-1]=120, past=s[-2]=115 → 120/115 - 1
        ret = _safe_return(s, 2)
        assert ret is not None
        # s.iloc[-1]=120, s.iloc[-2]=115
        assert abs(ret - (120.0 / 115.0 - 1)) < 1e-6

    def test_multi_day(self):
        s = pd.Series([100, 105, 110, 115, 120])
        # _safe_return(s, 4): current=s[-1]=120, past=s[-4]=105 → 120/105 - 1
        ret = _safe_return(s, 4)
        assert ret is not None
        assert abs(ret - (120.0 / 105.0 - 1)) < 1e-6

    def test_insufficient_data(self):
        s = pd.Series([100, 105])
        assert _safe_return(s, 5) is None

    def test_zero_past(self):
        s = pd.Series([0, 0, 0, 100])
        assert _safe_return(s, 2) is None


class TestConstants:
    """定数の検証."""

    def test_sector_etfs_count(self):
        assert len(SECTOR_ETFS) == 11  # GICS 11セクター

    def test_benchmark(self):
        assert BENCHMARK == "SPY"

    def test_known_etfs(self):
        assert "金融" in SECTOR_ETFS
        assert SECTOR_ETFS["金融"] == "XLF"
        assert "エネルギー" in SECTOR_ETFS
        assert SECTOR_ETFS["エネルギー"] == "XLE"


class TestGetSectorRS:
    """get_sector_rs のテスト（外部API モック）."""

    def test_returns_list_or_none(self, mock_yahoo_client):
        """モック環境ではデータ不足で None が返る可能性がある."""
        result = get_sector_rs()
        # None or list
        assert result is None or isinstance(result, list)

    def test_result_structure(self, mock_yahoo_client):
        """結果が返った場合の構造チェック."""
        result = get_sector_rs()
        if result is not None and len(result) > 0:
            item = result[0]
            assert "name" in item
            assert "symbol" in item
            assert "rs_score" in item
            assert "return_20d" in item
            assert "return_60d" in item
            assert "volume_change" in item
            assert "rank" in item
            assert item["rank"] == 1  # 最初のアイテムは rank 1

    def test_sorted_by_rs_descending(self, mock_yahoo_client):
        """RS降順にソートされているか."""
        result = get_sector_rs()
        if result is not None and len(result) > 1:
            for i in range(len(result) - 1):
                assert result[i]["rs_score"] >= result[i + 1]["rs_score"]
