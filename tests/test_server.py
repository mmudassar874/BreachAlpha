"""Tests for the FastAPI backend."""

import pytest
from fastapi.testclient import TestClient

from breachalpha.server import app

client = TestClient(app)


class TestHealth:
    def test_health_check(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "model_loaded" in data
        assert data["version"] == "0.1.0"


class TestScore:
    def test_score_unknown_company(self):
        response = client.post("/api/score", json={
            "company": "FakeCompany12345",
            "breach_type": "data_leak",
            "records_affected": 1000000,
            "breach_date": "2024-01-01",
        })
        assert response.status_code == 404

    def test_score_missing_company(self):
        response = client.post("/api/score", json={
            "breach_type": "data_leak",
        })
        assert response.status_code == 422  # Validation error


class TestDemo:
    def test_demo_returns_cases(self):
        response = client.get("/api/demo")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3
        assert data[0]["company"] == "Equifax"
        assert data[1]["company"] == "Capital One"
        assert data[2]["company"] == "Marriott"


class TestTrain:
    def test_train_missing_file(self):
        response = client.post("/api/train", json={
            "data_path": "/nonexistent/file.csv",
        })
        assert response.status_code in (403, 404)  # 403=path outside allowed dirs, 404=file not found


class TestUpload:
    def test_upload_csv(self, tmp_path):
        import pandas as pd
        csv = tmp_path / "test.csv"
        pd.DataFrame({
            "Company": ["Equifax", "Capital One"],
            "Date": ["2017-09-07", "2019-07-29"],
            "Records": [147000000, 106000000],
        }).to_csv(csv, index=False)

        with open(csv, "rb") as f:
            response = client.post("/api/upload", files={"file": ("test.csv", f, "text/csv")})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["original_rows"] == 2

    def test_upload_unsupported_type(self):
        response = client.post("/api/upload", files={"file": ("test.json", b"{}", "application/json")})
        assert response.status_code == 400


class TestExplain:
    def test_explain_unknown_company(self):
        response = client.post("/api/explain", json={
            "company": "FakeCompany12345",
            "breach_date": "2024-01-01",
        })
        assert response.status_code == 404

    def test_explain_missing_fields(self):
        response = client.post("/api/explain", json={})
        assert response.status_code == 422
