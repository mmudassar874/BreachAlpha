"""Tests for model module — training, prediction, persistence."""

import numpy as np
import pandas as pd
import pytest

from breachalpha.model import (
    train_model,
    save_model,
    load_model,
    predict_severity,
    prepare_training_data,
    FEATURE_COLS,
)


def _make_synthetic_features(n: int = 100) -> pd.DataFrame:
    """Create synthetic feature data for testing."""
    np.random.seed(42)
    return pd.DataFrame({
        "abnormal_return_day0": np.random.normal(-0.02, 0.05, n),
        "abnormal_return_day1": np.random.normal(-0.01, 0.04, n),
        "abnormal_return_day5": np.random.normal(-0.005, 0.03, n),
        "abnormal_return_day30": np.random.normal(0.001, 0.02, n),
        "car_minus1_plus1": np.random.normal(-0.03, 0.08, n),
        "car_minus5_plus30": np.random.normal(-0.05, 0.12, n),
        "volatility_spike": np.random.uniform(0.8, 3.0, n),
        "volume_change": np.random.uniform(0.5, 5.0, n),
        "time_to_recovery": np.random.choice([5, 10, 20, 30, 60, None], n),
        "pwn_count": np.random.lognormal(15, 2, n).astype(int),
    })


class TestPrepareData:
    def test_shapes_match(self):
        df = _make_synthetic_features(50)
        X, y = prepare_training_data(df)
        assert len(X) == len(y)
        assert len(X) == 50

    def test_feature_columns(self):
        df = _make_synthetic_features(50)
        X, y = prepare_training_data(df)
        assert all(col in X.columns for col in FEATURE_COLS)

    def test_no_nan_in_features(self):
        df = _make_synthetic_features(50)
        X, y = prepare_training_data(df)
        assert not X.isna().any().any()

    def test_labels_are_integers(self):
        df = _make_synthetic_features(50)
        X, y = prepare_training_data(df)
        assert y.dtype in [int, np.int32, np.int64]


class TestTrainModel:
    def test_basic_training(self):
        df = _make_synthetic_features(50)
        result = train_model(df)
        assert "model" in result
        assert "metrics" in result
        assert result["metrics"]["n_samples"] == 50
        assert 0 <= result["metrics"]["cv_accuracy_mean"] <= 1

    def test_insufficient_data_raises(self):
        df = _make_synthetic_features(5)
        with pytest.raises(ValueError, match="Insufficient"):
            train_model(df)

    def test_feature_importance_exists(self):
        df = _make_synthetic_features(50)
        result = train_model(df)
        assert "feature_importance" in result["metrics"]
        assert len(result["metrics"]["feature_importance"]) > 0


class TestPredictSeverity:
    def test_prediction_format(self):
        df = _make_synthetic_features(50)
        result = train_model(df)
        model = result["model"]

        sample = _make_synthetic_features(1)
        pred = predict_severity(model, sample)

        assert "prediction" in pred
        assert "probabilities" in pred
        assert "risk_score" in pred
        assert "confidence" in pred
        assert pred["prediction"] in ["low", "medium", "high", "critical"]
        assert 0 <= pred["risk_score"] <= 100
        assert 0 <= pred["confidence"] <= 1

    def test_probabilities_sum_to_one(self):
        df = _make_synthetic_features(50)
        result = train_model(df)
        model = result["model"]

        sample = _make_synthetic_features(1)
        pred = predict_severity(model, sample)
        total = sum(pred["probabilities"].values())
        assert abs(total - 1.0) < 0.01


class TestModelPersistence:
    def test_save_and_load(self, tmp_path):
        import breachalpha.model as model_mod
        original_dir = model_mod.MODEL_DIR
        model_mod.MODEL_DIR = tmp_path

        try:
            df = _make_synthetic_features(50)
            result = train_model(df)
            save_model(result["model"], result["metrics"], "test_model")

            loaded = load_model("test_model")
            assert loaded is not None

            # Predictions should match
            sample = _make_synthetic_features(1)
            pred1 = predict_severity(result["model"], sample)
            pred2 = predict_severity(loaded, sample)
            assert pred1["prediction"] == pred2["prediction"]
        finally:
            model_mod.MODEL_DIR = original_dir

    def test_load_nonexistent_returns_none(self, tmp_path):
        import breachalpha.model as model_mod
        original_dir = model_mod.MODEL_DIR
        model_mod.MODEL_DIR = tmp_path
        try:
            assert load_model("nonexistent") is None
        finally:
            model_mod.MODEL_DIR = original_dir
