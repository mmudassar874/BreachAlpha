"""Tests for preprocessing pipeline."""

import pytest
import pandas as pd
from pathlib import Path
from breachalpha.preprocessor import (
    normalize_column_name,
    map_columns,
    parse_dates_robust,
    parse_numeric,
    preprocess_dataset,
)


class TestNormalizeColumnName:
    def test_lowercase(self):
        assert normalize_column_name("Company Name") == "company_name"

    def test_spaces_to_underscores(self):
        assert normalize_column_name("Breach Date") == "breach_date"

    def test_special_chars_removed(self):
        assert normalize_column_name("Records #") == "records"

    def test_already_normalized(self):
        assert normalize_column_name("company_name") == "company_name"


class TestMapColumns:
    def test_known_columns(self):
        df = pd.DataFrame({"Company": ["A"], "Date": ["2020-01-01"], "Records": [100]})
        _, mapping, _ = map_columns(df)
        assert mapping["Company"] == "company_name"
        assert mapping["Date"] == "breach_date"
        assert mapping["Records"] == "records_affected"

    def test_unknown_columns(self):
        df = pd.DataFrame({"Foo": ["A"], "Bar": [1]})
        _, _, warnings = map_columns(df)
        assert len(warnings) == 2


class TestParseDatesRobust:
    def test_iso_format(self):
        s = pd.Series(["2020-01-15", "2021-06-30"])
        result = parse_dates_robust(s)
        assert pd.api.types.is_datetime64_any_dtype(result)

    def test_us_format(self):
        s = pd.Series(["01/15/2020", "06/30/2021"])
        result = parse_dates_robust(s)
        assert result.notna().all()


class TestParseNumeric:
    def test_plain_numbers(self):
        s = pd.Series(["100", "200", "300"])
        result = parse_numeric(s)
        assert result.tolist() == [100, 200, 300]

    def test_with_commas(self):
        s = pd.Series(["1,000", "2,500"])
        result = parse_numeric(s)
        assert result.tolist() == [1000, 2500]

    def test_with_currency(self):
        s = pd.Series(["$100", "$200"])
        result = parse_numeric(s)
        assert result.tolist() == [100, 200]


class TestPreprocessDataset:
    def test_valid_csv(self, tmp_path):
        csv = tmp_path / "test.csv"
        pd.DataFrame({
            "Company": ["Equifax", "Capital One"],
            "Date": ["2017-09-07", "2019-07-29"],
            "Records": [147000000, 106000000],
        }).to_csv(csv, index=False)

        result = preprocess_dataset(csv)
        assert result.success
        assert result.original_rows == 2
        assert result.cleaned_rows == 2
        assert "company_name" in result.column_mapping.values()

    def test_missing_required_columns(self, tmp_path):
        csv = tmp_path / "bad.csv"
        pd.DataFrame({"Foo": ["A"], "Bar": [1]}).to_csv(csv, index=False)
        result = preprocess_dataset(csv)
        assert not result.success
        assert len(result.errors) > 0

    def test_unsupported_format(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text("{}")
        result = preprocess_dataset(f)
        assert not result.success
        assert "Unsupported file format" in result.errors[0]

    def test_xlsx(self, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        pd.DataFrame({
            "Company": ["Equifax"],
            "Breach Date": ["2017-09-07"],
            "Individuals Affected": [147000000],
        }).to_excel(xlsx, index=False)

        result = preprocess_dataset(xlsx)
        assert result.success
        assert result.cleaned_rows == 1
