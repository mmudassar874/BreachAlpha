"""XGBoost model for predicting breach impact severity."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import cross_val_score, StratifiedKFold

from .feature_engine import classify_severity
from .core.constants import FEATURE_COLS, SEVERITY_LABELS, SEVERITY_MAP, RISK_WEIGHTS

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent / "models"


def prepare_training_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Prepare feature matrix and target labels from computed features.

    Args:
        df: DataFrame with feature columns + 'car_minus5_plus30' for label generation.

    Returns:
        Tuple of (X, y) where X is feature matrix and y is severity labels.
    """
    # Generate target labels from CAR
    y = df["car_minus5_plus30"].apply(classify_severity)
    y = y.map(SEVERITY_MAP)

    # Select feature columns
    available_cols = [col for col in FEATURE_COLS if col in df.columns]
    X = df[available_cols].copy()

    # Handle NaN/inf
    X = X.replace([np.inf, -np.inf], np.nan)
    # Convert Optional[int] column (time_to_recovery) to float, None -> NaN
    if "time_to_recovery" in X.columns:
        X["time_to_recovery"] = pd.to_numeric(X["time_to_recovery"], errors="coerce")
    X = X.fillna(0)

    return X, y


def train_model(
    df: pd.DataFrame,
    n_estimators: int = 100,
    max_depth: int = 4,
    learning_rate: float = 0.1,
    min_child_weight: int = 3,
    subsample: float = 0.8,
    colsample_bytree: float = 0.8,
    random_state: int = 42,
) -> dict:
    """Train XGBoost classifier on breach features.

    Args:
        df: DataFrame with feature columns and car_minus5_plus30 for labels.
        n_estimators: Number of boosting rounds.
        max_depth: Maximum tree depth (conservative for small data).
        learning_rate: Boosting learning rate.
        min_child_weight: Minimum sum of instance weight in a child.
        subsample: Fraction of samples used per tree.
        colsample_bytree: Fraction of features used per tree.
        random_state: Random seed for reproducibility.

    Returns:
        Dict with trained model, metrics, and metadata.
    """
    X, y = prepare_training_data(df)

    if len(X) < 20:
        raise ValueError(f"Insufficient training data: {len(X)} samples (need >= 20)")

    logger.info("Training XGBoost on %d samples, %d features", len(X), len(X.columns))

    # Train model
    model = xgb.XGBClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        min_child_weight=min_child_weight,
        subsample=subsample,
        colsample_bytree=colsample_bytree,
        random_state=random_state,
        objective="multi:softprob",
        num_class=len(SEVERITY_LABELS),
        eval_metric="mlogloss",
    )

    # Cross-validation
    cv = StratifiedKFold(n_splits=min(5, len(X) // 5), shuffle=True, random_state=random_state)
    cv_scores = cross_val_score(model, X, y, cv=cv, scoring="accuracy")

    # Train on full data
    model.fit(X, y)

    # Feature importance
    importance = dict(zip(FEATURE_COLS[:len(model.feature_importances_)], model.feature_importances_))
    importance_sorted = {k: float(v) for k, v in sorted(importance.items(), key=lambda x: x[1], reverse=True)}

    metrics = {
        "cv_accuracy_mean": float(cv_scores.mean()),
        "cv_accuracy_std": float(cv_scores.std()),
        "n_samples": len(X),
        "n_features": len(X.columns),
        "feature_importance": importance_sorted,
    }

    logger.info("Model trained — CV accuracy: %.3f (+/- %.3f)", cv_scores.mean(), cv_scores.std())

    return {
        "model": model,
        "metrics": metrics,
        "feature_cols": FEATURE_COLS[:len(model.feature_importances_)],
    }


def save_model(model: xgb.XGBClassifier, metrics: dict, name: str = "breachalpha_model") -> Path:
    """Save trained model and metrics to disk."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODEL_DIR / f"{name}.json"
    model.save_model(str(model_path))

    metrics_path = MODEL_DIR / f"{name}_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    logger.info("Saved model to %s", model_path)
    return model_path


@lru_cache(maxsize=1)
def load_model(name: str = "breachalpha_model") -> Optional[xgb.XGBClassifier]:
    """Load a trained model from disk. Cached — loaded once per process."""
    model_path = MODEL_DIR / f"{name}.json"
    if not model_path.exists():
        logger.warning("Model not found: %s", model_path)
        return None

    model = xgb.XGBClassifier()
    model.load_model(str(model_path))
    logger.info("Loaded model from %s", model_path)
    return model


def predict_severity(model: xgb.XGBClassifier, features: pd.DataFrame) -> dict:
    """Predict impact severity for a breach event.

    Args:
        model: Trained XGBoost model.
        features: DataFrame with feature columns (single row).

    Returns:
        Dict with prediction, probabilities, and risk score.
    """
    available_cols = [col for col in FEATURE_COLS if col in features.columns]
    X = features[available_cols].replace([np.inf, -np.inf], np.nan)
    if "time_to_recovery" in X.columns:
        X["time_to_recovery"] = pd.to_numeric(X["time_to_recovery"], errors="coerce")
    X = X.fillna(0)

    # Predict class and probabilities
    pred_idx = int(model.predict(X)[0])
    probas = model.predict_proba(X)[0]

    prediction = SEVERITY_LABELS[pred_idx]
    probabilities = {label: float(proba) for label, proba in zip(SEVERITY_LABELS, probas)}

    # Risk score: weighted sum (0-100)
    risk_score = sum(probabilities[label] * RISK_WEIGHTS[label] for label in SEVERITY_LABELS)

    return {
        "prediction": prediction,
        "probabilities": probabilities,
        "risk_score": round(risk_score, 1),
        "confidence": round(float(max(probas)), 3),
    }
