"""Tests for breach_loader module."""

import pytest
import pandas as pd
from pathlib import Path
from breachalpha.breach_loader import load_breaches, get_breach_summary

SAMPLE_CSV = Path(__file__).parent.parent / "data" / "sample_breaches.csv"


def _create_sample_csv(tmp_path: Path) -> Path:
    """Create a minimal sample CSV for testing."""
    data = {
        "Name": ["Equifax", "Capital One", "Small Corp", "Spam Corp", "Tiny Corp"],
        "Title": ["Equifax Breach", "Capital One", "Small Breach", "Spam", "Tiny"],
        "Domain": ["equifax.com", "capitalone.com", "small.com", "spam.com", "tiny.com"],
        "BreachDate": ["2017-09-07", "2019-07-29", "2020-01-15", "2021-06-01", "2022-03-10"],
        "PwnCount": [147_000_000, 106_000_000, 500, 10_000, 50],
        "Description": ["Test"] * 5,
        "IsVerified": [True, True, True, True, True],
        "IsFabricated": [False, False, False, True, False],
        "IsSensitive": [False, False, False, False, False],
        "IsRetired": [False, False, False, False, False],
        "IsSpamList": [False, False, False, True, False],
        "IsMalware": [False, False, False, False, False],
        "IsSubscriptionFree": [False, False, False, False, False],
    }
    csv_path = tmp_path / "test_breaches.csv"
    pd.DataFrame(data).to_csv(csv_path, index=False)
    return csv_path


class TestLoadBreaches:
    def test_loads_valid_csv(self, tmp_path):
        csv_path = _create_sample_csv(tmp_path)
        df = load_breaches(csv_path)
        assert len(df) == 2  # Equifax + Capital One (others filtered by PwnCount or fabricated/spam)

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_breaches("/nonexistent/path.csv")

    def test_raises_on_missing_columns(self, tmp_path):
        csv_path = tmp_path / "bad.csv"
        pd.DataFrame({"Foo": ["A"], "Bar": ["2020-01-01"]}).to_csv(csv_path, index=False)
        with pytest.raises(ValueError, match="Missing required columns"):
            load_breaches(csv_path)

    def test_filters_fabricated(self, tmp_path):
        csv_path = _create_sample_csv(tmp_path)
        df = load_breaches(csv_path)
        assert "Spam Corp" not in df["Name"].values

    def test_filters_small_breaches(self, tmp_path):
        csv_path = _create_sample_csv(tmp_path)
        df = load_breaches(csv_path)
        assert "Small Corp" not in df["Name"].values  # 500 < 1000 threshold
        assert "Tiny Corp" not in df["Name"].values   # 50 < 1000 threshold

    def test_deduplicates(self, tmp_path):
        data = {
            "Name": ["Equifax", "Equifax", "Capital One"],
            "BreachDate": ["2017-09-07", "2016-01-01", "2019-07-29"],
            "PwnCount": [147_000_000, 10_000_000, 106_000_000],
        }
        csv_path = tmp_path / "dup.csv"
        pd.DataFrame(data).to_csv(csv_path, index=False)
        df = load_breaches(csv_path)
        assert len(df[df["Name"] == "Equifax"]) == 1

    def test_breach_date_parsed(self, tmp_path):
        csv_path = _create_sample_csv(tmp_path)
        df = load_breaches(csv_path)
        assert pd.api.types.is_datetime64_any_dtype(df["BreachDate"])


class TestBreachSummary:
    def test_summary_stats(self, tmp_path):
        csv_path = _create_sample_csv(tmp_path)
        df = load_breaches(csv_path)
        summary = get_breach_summary(df)
        assert summary["total_breaches"] == 2
        assert summary["unique_companies"] == 2
        assert summary["total_records_affected"] > 0
