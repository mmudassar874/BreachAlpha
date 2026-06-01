"""FastAPI backend for BreachAlpha.

Run with:
    uvicorn breachalpha.server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import time
from typing import Optional

import numpy as np
import pandas as pd
from cachetools import TTLCache
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

# Bounded TTL cache for network search results (prevents memory DoS)
_search_cache: TTLCache = TTLCache(maxsize=1000, ttl=300)

# ── Security Constants ───────────────────────────────────────────────────
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
_TICKER_RE = re.compile(r"^[A-Z0-9.^]{1,15}$")
_ADMIN_KEY = os.environ.get("BREACHALPHA_ADMIN_KEY", "")

from .feature_engine import BreachEvent, compute_features, compute_features_batch, classify_severity, AnalysisConfig as FeatureConfig
from .model import load_model, predict_severity, train_model, save_model, SEVERITY_LABELS
from .stock_loader import (
    fetch_stock_data, fetch_market_data, fetch_stock_batch,
    get_cache_info, clear_cache, get_data_sources_status,
)
from .ticker_resolver import resolve_ticker, detect_benchmark
from .preprocessor import preprocess_dataset, PreprocessingResult, AnalysisConfig as PreprocessConfig
from .explainability import generate_explanation, ExplainabilityReport
from .data_sources import DataFetcher, FetcherConfig

logger = logging.getLogger(__name__)

app = FastAPI(
    title="BreachAlpha API",
    description="Quantify the financial impact of cybersecurity incidents",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)


# ── Security Middleware ───────────────────────────────────────────────────


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """Protect admin endpoints with X-Admin-Key header validation."""

    ADMIN_PREFIXES = ("/api/train", "/api/data-sources/configure")
    ADMIN_EXACT = {"/api/cache"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_admin = (
            any(path.startswith(p) for p in self.ADMIN_PREFIXES)
            or path in self.ADMIN_EXACT
            or (path == "/api/cache" and request.method == "DELETE")
        )
        if is_admin and _ADMIN_KEY:
            key = request.headers.get("X-Admin-Key", "")
            if key != _ADMIN_KEY:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing X-Admin-Key header"},
                )
        return await call_next(request)


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AdminAuthMiddleware)


def _validate_ticker(ticker: str) -> str:
    """Validate and normalize a ticker symbol. Raises HTTPException on invalid input."""
    cleaned = ticker.strip().upper()
    if not _TICKER_RE.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker format: '{ticker}'. Tickers must be 1-15 alphanumeric characters.",
        )
    return cleaned


def _validate_breach_search_query(q: str) -> str:
    """Validate breach search query to prevent injection/SSRF."""
    q = q.strip()
    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters.")
    if len(q) > 100:
        raise HTTPException(status_code=400, detail="Query too long (max 100 characters).")
    return q


# ── Request / Response Models ─────────────────────────────────────────────


class ScoreRequest(BaseModel):
    company: str = Field(..., description="Company name (e.g., 'Equifax')")
    breach_type: str = Field(default="data_leak", description="Breach type: data_leak, ransomware, hack, etc.")
    records_affected: int = Field(default=1_000_000, description="Number of records affected")
    breach_date: str = Field(default="2024-01-01", description="Breach date (YYYY-MM-DD)")


class FeatureDetail(BaseModel):
    abnormal_return_day0: float
    abnormal_return_day1: float
    abnormal_return_day5: float
    abnormal_return_day30: float
    car_minus1_plus1: float
    car_minus5_plus30: float
    volatility_spike: float
    volume_change: float
    time_to_recovery: Optional[int]
    severity: str


class ScoreResponse(BaseModel):
    company: str
    ticker: str
    risk_score: float
    prediction: str
    confidence: float
    probabilities: dict[str, float]
    features: FeatureDetail


class AutoScoreResponse(ScoreResponse):
    breach_found: bool
    breach_date_used: str
    records_used: int
    breach_type_used: str
    breach_confidence: float
    incident_count: int


class DemoCase(BaseModel):
    company: str
    ticker: str
    breach_date: str
    pwn_count: int
    breach_type: str
    description: str
    risk_score: Optional[float] = None
    prediction: Optional[str] = None
    confidence: Optional[float] = None


class TrainRequest(BaseModel):
    data_path: str = Field(..., description="Path to breach CSV file (must be in data/ directory)")


class TrainResponse(BaseModel):
    status: str
    n_samples: int
    cv_accuracy: float
    cv_std: float
    feature_importance: dict[str, float]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    version: str


class UploadResponse(BaseModel):
    success: bool
    original_rows: int
    cleaned_rows: int
    columns_detected: list[str]
    column_mapping: dict[str, str]
    ticker_resolution_rate: float
    preview: list[dict]
    errors: list[str]
    warnings: list[str]


class BatchResult(BaseModel):
    company: str
    ticker: str
    breach_date: str
    records_affected: int
    breach_type: str
    risk_score: float
    prediction: str
    confidence: float
    probabilities: dict[str, float]
    status: str
    error: Optional[str] = None


class BatchResponse(BaseModel):
    total: int
    analyzed: int
    failed: int
    results: list[BatchResult]


class ExplainRequest(BaseModel):
    company: str
    breach_type: str = "data_leak"
    records_affected: int = 1_000_000
    breach_date: str = "2024-01-01"


class CalculationStepModel(BaseModel):
    step_number: int
    name: str
    description: str
    formula: str
    inputs: dict
    output: float | str | dict
    interpretation: str


class ExplainResponse(BaseModel):
    company: str
    ticker: str
    breach_date: str
    steps: list[CalculationStepModel]
    final_score: float
    final_prediction: str
    confidence: float
    probabilities: dict[str, float]
    feature_contributions: dict[str, float]
    methodology: str
    limitations: list[str]


class AnalysisConfigRequest(BaseModel):
    """User-configurable analysis parameters."""
    estimation_window: int = Field(default=250, ge=50, le=500, description="Days for market model estimation")
    pre_event_window: int = Field(default=30, ge=5, le=100, description="Days before event to analyze")
    post_event_window: int = Field(default=60, ge=10, le=200, description="Days after event to analyze")
    recovery_max_days: int = Field(default=90, ge=10, le=365, description="Max days to search for recovery")
    threshold_critical: float = Field(default=-0.15, ge=-1.0, le=0.0, description="CAR threshold for critical severity")
    threshold_high: float = Field(default=-0.07, ge=-1.0, le=0.0, description="CAR threshold for high severity")
    threshold_medium: float = Field(default=-0.02, ge=-1.0, le=0.0, description="CAR threshold for medium severity")
    car_short_start: int = Field(default=-1, description="CAR short window start (days relative to event)")
    car_short_end: int = Field(default=1, description="CAR short window end")
    car_long_start: int = Field(default=-5, description="CAR long window start")
    car_long_end: int = Field(default=30, description="CAR long window end")
    benchmark: str = Field(default="^GSPC", description="Market benchmark ticker (^GSPC for S&P 500)")
    start_date: str = Field(default="2010-01-01", description="Start date for stock data")
    min_records: int = Field(default=1000, ge=0, description="Minimum records affected filter")


class UploadConfigRequest(BaseModel):
    """User-configurable preprocessing options."""
    column_mapping: dict[str, str] = Field(default_factory=dict, description="Custom column name mapping")
    date_format: Optional[str] = Field(default=None, description="Preferred date format (e.g., %Y-%m-%d)")
    records_threshold: int = Field(default=1000, ge=0, description="Minimum records affected filter")
    start_date: Optional[str] = Field(default=None, description="Filter breaches after this date")
    end_date: Optional[str] = Field(default=None, description="Filter breaches before this date")
    ticker_overrides: dict[str, str] = Field(default_factory=dict, description="Custom company→ticker mappings")
    skip_ticker_resolution: bool = Field(default=False, description="Skip automatic ticker resolution")
    max_rows: Optional[int] = Field(default=None, ge=1, description="Max rows to read from file")


class CacheInfoResponse(BaseModel):
    cached_files: int
    total_size_kb: float
    tickers: list[str]


class ConfigPreset(BaseModel):
    name: str
    description: str
    config: AnalysisConfigRequest


class DataSourceStatus(BaseModel):
    name: str
    available: bool
    priority: int
    reason: Optional[str] = None


class DataSourceConfigRequest(BaseModel):
    """Configure data source preferences."""
    primary_source: str = Field(default="yfinance", description="Primary data source")
    alpha_vantage_key: str = Field(default="", description="Alpha Vantage API key")
    enable_fallback: bool = Field(default=True, description="Enable fallback sources")
    cache_ttl_hours: int = Field(default=24, ge=1, le=168, description="Cache TTL in hours")


class DataSourceConfigResponse(BaseModel):
    primary_source: str
    alpha_vantage_key_set: bool
    enable_fallback: bool
    cache_ttl_hours: int
    sources: dict[str, DataSourceStatus]


# ── Endpoints ─────────────────────────────────────────────────────────────


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    model = load_model()
    return HealthResponse(
        status="ok",
        model_loaded=model is not None,
        version="0.1.0",
    )


@app.post("/api/score", response_model=ScoreResponse)
async def score_company(req: ScoreRequest):
    """Score a company for breach impact."""
    ticker = resolve_ticker(req.company)
    if ticker is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not resolve ticker for '{req.company}'. Add mapping to data/ticker_overrides.json.",
        )

    ticker = _validate_ticker(ticker)
    benchmark = detect_benchmark(ticker)

    stock_data, market_data = await asyncio.gather(
        asyncio.to_thread(fetch_stock_data, ticker, "2015-01-01"),
        asyncio.to_thread(fetch_market_data, "2015-01-01", benchmark),
    )
    if stock_data.empty:
        raise HTTPException(status_code=404, detail=f"No stock data available for {ticker}")

    event = BreachEvent(
        company_name=req.company,
        ticker=ticker,
        breach_date=pd.Timestamp(req.breach_date),
        pwn_count=req.records_affected,
        breach_type=req.breach_type,
        stock_data=stock_data,
        market_data=market_data,
        benchmark=benchmark,
    )

    features = compute_features(event)
    if features is None:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data around breach date for {req.company}. Try a different date.",
        )

    model = load_model()
    if model is None:
        # Train on synthetic data as fallback
        result = _train_synthetic()
        model = result["model"]

    features_df = pd.DataFrame([features.to_dict()])
    prediction = predict_severity(model, features_df)

    return ScoreResponse(
        company=req.company,
        ticker=ticker,
        risk_score=prediction["risk_score"],
        prediction=prediction["prediction"],
        confidence=prediction["confidence"],
        probabilities=prediction["probabilities"],
        features=FeatureDetail(
            abnormal_return_day0=features.abnormal_return_day0,
            abnormal_return_day1=features.abnormal_return_day1,
            abnormal_return_day5=features.abnormal_return_day5,
            abnormal_return_day30=features.abnormal_return_day30,
            car_minus1_plus1=features.car_minus1_plus1,
            car_minus5_plus30=features.car_minus5_plus30,
            volatility_spike=features.volatility_spike,
            volume_change=features.volume_change,
            time_to_recovery=features.time_to_recovery,
            severity=classify_severity(features.car_minus5_plus30),
        ),
    )


@app.post("/api/score/auto", response_model=AutoScoreResponse)
async def score_auto(req: ScoreRequest):
    """Search for real breach data and score using the most significant incident."""
    import re
    from .breach_search import search_breach_incidents

    ticker = resolve_ticker(req.company)
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"Could not resolve ticker for '{req.company}'")

    ticker = _validate_ticker(ticker)

    # Resolve company name from ticker for better search
    company_name = req.company
    try:
        from .ticker_resolver import KNOWN_TICKERS
        rev = {v.upper(): k for k, v in KNOWN_TICKERS.items() if v}
        bare = re.sub(r"\.(NS|BO|NSE|BSE|L|DE|TO|HK|SS|SZ)$", "", ticker.upper())
        if ticker.upper() in rev:
            company_name = rev[ticker.upper()].title()
        elif bare in rev:
            company_name = rev[bare].title()
    except Exception:
        pass

    # Search for breach incidents
    incidents = await asyncio.to_thread(search_breach_incidents, company_name, 5)
    breach_found = len(incidents) > 0

    if breach_found:
        top = max(incidents, key=lambda x: (x.records_affected, x.confidence))
        breach_date = top.date if top.date else req.breach_date
        records = top.records_affected if top.records_affected > 0 else req.records_affected
        breach_type = top.breach_type
        breach_confidence = top.confidence
    else:
        breach_date = req.breach_date
        records = req.records_affected
        breach_type = req.breach_type
        breach_confidence = 0.0

    benchmark = detect_benchmark(ticker)

    stock_data, market_data = await asyncio.gather(
        asyncio.to_thread(fetch_stock_data, ticker, "2015-01-01"),
        asyncio.to_thread(fetch_market_data, "2015-01-01", benchmark),
    )
    if stock_data.empty:
        raise HTTPException(status_code=404, detail=f"No stock data for {ticker}")

    event = BreachEvent(
        company_name=company_name, ticker=ticker,
        breach_date=pd.Timestamp(breach_date),
        pwn_count=records, breach_type=breach_type,
        stock_data=stock_data, market_data=market_data,
        benchmark=benchmark,
    )

    features = compute_features(event)
    if features is None:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data around breach date {breach_date} for {company_name}",
        )

    model = load_model()
    if model is None:
        model = _train_synthetic()["model"]

    features_df = pd.DataFrame([features.to_dict()])
    prediction = predict_severity(model, features_df)

    return AutoScoreResponse(
        company=req.company, ticker=ticker,
        risk_score=prediction["risk_score"],
        prediction=prediction["prediction"],
        confidence=prediction["confidence"],
        probabilities=prediction["probabilities"],
        features=FeatureDetail(
            abnormal_return_day0=features.abnormal_return_day0,
            abnormal_return_day1=features.abnormal_return_day1,
            abnormal_return_day5=features.abnormal_return_day5,
            abnormal_return_day30=features.abnormal_return_day30,
            car_minus1_plus1=features.car_minus1_plus1,
            car_minus5_plus30=features.car_minus5_plus30,
            volatility_spike=features.volatility_spike,
            volume_change=features.volume_change,
            time_to_recovery=features.time_to_recovery,
            severity=classify_severity(features.car_minus5_plus30),
        ),
        breach_found=breach_found,
        breach_date_used=breach_date,
        records_used=records,
        breach_type_used=breach_type,
        breach_confidence=breach_confidence,
        incident_count=len(incidents),
    )


@app.get("/api/demo", response_model=list[DemoCase])
async def run_demo():
    """Run demo with three famous breaches."""
    demo_cases = [
        DemoCase(
            company="Equifax",
            ticker="EFX",
            breach_date="2017-09-07",
            pwn_count=147_000_000,
            breach_type="data_leak",
            description="Massive credit data breach exposing SSNs, birth dates, addresses",
        ),
        DemoCase(
            company="Capital One",
            ticker="COF",
            breach_date="2019-07-29",
            pwn_count=106_000_000,
            breach_type="data_leak",
            description="Cloud misconfiguration exposed credit card applications",
        ),
        DemoCase(
            company="Marriott",
            ticker="MAR",
            breach_date="2018-11-30",
            pwn_count=500_000_000,
            breach_type="data_leak",
            description="Starwood reservation system breach (4 years undetected)",
        ),
    ]

    market_data = fetch_market_data(start="2015-01-01")
    model = load_model()
    if model is None:
        result = _train_synthetic()
        model = result["model"]

    for case in demo_cases:
        try:
            stock_data = fetch_stock_data(case.ticker, start="2015-01-01")
            if stock_data.empty:
                continue

            event = BreachEvent(
                company_name=case.company,
                ticker=case.ticker,
                breach_date=pd.Timestamp(case.breach_date),
                pwn_count=case.pwn_count,
                breach_type=case.breach_type,
                stock_data=stock_data,
                market_data=market_data,
            )

            features = compute_features(event)
            if features is not None:
                features_df = pd.DataFrame([features.to_dict()])
                pred = predict_severity(model, features_df)
                case.risk_score = pred["risk_score"]
                case.prediction = pred["prediction"]
                case.confidence = pred["confidence"]
        except Exception as e:
            logger.error("Demo failed for %s: %s", case.company, e)

    return demo_cases


@app.post("/api/train", response_model=TrainResponse)
async def train_model_endpoint(req: TrainRequest):
    """Train the model on breach data."""
    from pathlib import Path

    path = Path(req.data_path).resolve()

    # Security: validate path is within allowed directories (uses path canonical comparison)
    allowed_dirs = [
        (Path(__file__).parent.parent / "data").resolve(),
        (Path(__file__).parent.parent).resolve(),
    ]
    if not any(path.is_relative_to(d) for d in allowed_dirs):
        raise HTTPException(status_code=403, detail="Access denied: path outside allowed directories")

    if not path.exists():
        raise HTTPException(status_code=404, detail="Data file not found")

    # Run entire training pipeline in thread to avoid blocking event loop
    def _train_worker():
        from .breach_loader import load_breaches
        from .ticker_resolver import resolve_all, load_overrides

        breaches = load_breaches(path)
        overrides = load_overrides()
        resolutions = resolve_all(breaches["Name"].tolist(), overrides)

        resolved = breaches[breaches["Name"].map(resolutions).notna()].copy()
        resolved["ticker"] = resolved["Name"].map(resolutions)

        if len(resolved) < 20:
            raise ValueError(f"Need at least 20 resolved companies to train (got {len(resolved)})")

        market_data = fetch_market_data(start="2010-01-01")
        features_list = []

        for _, row in resolved.iterrows():
            stock_data = fetch_stock_data(row["ticker"], start="2010-01-01")
            if stock_data.empty:
                continue

            event = BreachEvent(
                company_name=row["Name"],
                ticker=row["ticker"],
                breach_date=row["BreachDate"],
                pwn_count=int(row["PwnCount"]),
                breach_type="data_leak",
                stock_data=stock_data,
                market_data=market_data,
            )
            features = compute_features(event)
            if features is not None:
                features_list.append(features.to_dict())

        if not features_list:
            raise ValueError("No features could be computed")

        df = pd.DataFrame(features_list)
        result = train_model(df)
        save_model(result["model"], result["metrics"])
        return result

    try:
        result = await asyncio.to_thread(_train_worker)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return TrainResponse(
        status="ok",
        n_samples=result["metrics"]["n_samples"],
        cv_accuracy=result["metrics"]["cv_accuracy_mean"],
        cv_std=result["metrics"]["cv_accuracy_std"],
        feature_importance=result["metrics"]["feature_importance"],
    )


# ── Helpers ───────────────────────────────────────────────────────────────


def _train_synthetic() -> dict:
    """Train on synthetic data for demo/fallback purposes."""
    np.random.seed(42)
    n = 100
    synthetic = pd.DataFrame({
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
    return train_model(synthetic)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_dataset(file: UploadFile = File(...)):
    """Upload and preprocess a breach dataset (CSV, XLSX, Excel)."""
    allowed_types = {".csv", ".xlsx", ".xls", ".tsv"}
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Allowed: {', '.join(allowed_types)}",
        )

    # Save uploaded file to temp location with size limit
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            total_size = 0
            while True:
                chunk = await file.read(8192)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > _MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum upload size is {_MAX_UPLOAD_BYTES // (1024*1024)} MB.",
                    )
                tmp.write(chunk)
            tmp_path = tmp.name

        result = await asyncio.to_thread(preprocess_dataset, tmp_path)
        return UploadResponse(
            success=result.success,
            original_rows=result.original_rows,
            cleaned_rows=result.cleaned_rows,
            columns_detected=result.columns_detected,
            column_mapping=result.column_mapping,
            ticker_resolution_rate=result.ticker_resolution_rate,
            preview=result.preview,
            errors=result.errors,
            warnings=result.warnings,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload preprocessing failed: %s", e)
        raise HTTPException(status_code=500, detail="Preprocessing failed")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/api/upload/analyze", response_model=BatchResponse)
async def upload_and_analyze(file: UploadFile = File(...)):
    """Upload a dataset and analyze all breaches in it."""
    allowed_types = {".csv", ".xlsx", ".xls", ".tsv"}
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Allowed: {', '.join(allowed_types)}",
        )

    # Read file content with size limit
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            total_size = 0
            while True:
                chunk = await file.read(8192)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > _MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum upload size is {_MAX_UPLOAD_BYTES // (1024*1024)} MB.",
                    )
                tmp.write(chunk)
            tmp_path = tmp.name

        result = await asyncio.to_thread(preprocess_dataset, tmp_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not result.success or result.df is None:
        return BatchResponse(total=0, analyzed=0, failed=0, results=[])

    df = result.df

    tickers_needed = []
    row_map = []
    for _, row in df.iterrows():
        company = str(row.get("company_name", ""))
        ticker = row.get("ticker")
        breach_date = row.get("breach_date")
        records = int(row.get("records_affected", 0))
        breach_type = str(row.get("breach_type", "data_leak"))

        if not ticker or pd.isna(ticker):
            ticker = resolve_ticker(company)
        if ticker:
            tickers_needed.append(str(ticker))
            row_map.append((company, str(ticker), breach_date, records, breach_type))

    if not tickers_needed:
        return BatchResponse(total=0, analyzed=0, failed=0, results=[])

    stock_cache = fetch_stock_batch(list(set(tickers_needed)), start="2010-01-01")

    model = load_model()
    if model is None:
        model = _train_synthetic()["model"]

    events = []
    for company, ticker, breach_date, records, breach_type in row_map:
        stock_data = stock_cache.get(ticker, pd.DataFrame())
        # Fallback: if ticker from CSV resolved to no stock data, try company name
        if stock_data.empty:
            alt_ticker = resolve_ticker(company)
            if alt_ticker and alt_ticker != ticker:
                alt_data = fetch_stock_data(alt_ticker, start="2010-01-01")
                if not alt_data.empty:
                    stock_data = alt_data
                    stock_cache[alt_ticker] = alt_data
        if not stock_data.empty:
            bm = detect_benchmark(ticker)
            market_data = fetch_market_data(start="2010-01-01", benchmark=bm)
            events.append(BreachEvent(
                company_name=company, ticker=ticker,
                breach_date=pd.Timestamp(breach_date),
                pwn_count=records, breach_type=breach_type,
                stock_data=stock_data, market_data=market_data,
                benchmark=bm,
            ))

    if not events:
        return BatchResponse(total=0, analyzed=0, failed=0, results=[])

    features_df = compute_features_batch(events)

    results = []
    for _, feat_row in features_df.iterrows():
        fd = feat_row.to_dict()
        try:
            pred = predict_severity(model, pd.DataFrame([fd]))
            results.append(BatchResult(
                company=fd["company_name"], ticker=fd["ticker"],
                breach_date=fd["breach_date"],
                records_affected=int(fd["pwn_count"]),
                breach_type=fd["breach_type"],
                risk_score=pred["risk_score"], prediction=pred["prediction"],
                confidence=pred["confidence"], probabilities=pred["probabilities"],
                status="ok",
            ))
        except Exception as e:
            results.append(BatchResult(
                company=fd.get("company_name", "?"), ticker=fd.get("ticker", "?"),
                breach_date=fd.get("breach_date", "?"),
                records_affected=int(fd.get("pwn_count", 0)),
                breach_type=fd.get("breach_type", "?"),
                risk_score=0, prediction="error", confidence=0,
                probabilities={}, status="failed", error=str(e),
            ))

    analyzed = sum(1 for r in results if r.status == "ok")

    return BatchResponse(total=len(results), analyzed=analyzed, failed=len(results)-analyzed, results=results)


@app.post("/api/explain", response_model=ExplainResponse)
async def explain_score(req: ExplainRequest):
    """Generate a full explainability report for a breach analysis."""
    ticker = resolve_ticker(req.company)
    if ticker is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not resolve ticker for '{req.company}'",
        )

    ticker = _validate_ticker(ticker)
    benchmark = detect_benchmark(ticker)

    stock_data, market_data = await asyncio.gather(
        asyncio.to_thread(fetch_stock_data, ticker, "2015-01-01"),
        asyncio.to_thread(fetch_market_data, "2015-01-01", benchmark),
    )
    if stock_data.empty:
        raise HTTPException(status_code=404, detail=f"No stock data for {ticker}")

    event = BreachEvent(
        company_name=req.company,
        ticker=ticker,
        breach_date=pd.Timestamp(req.breach_date),
        pwn_count=req.records_affected,
        breach_type=req.breach_type,
        stock_data=stock_data,
        market_data=market_data,
        benchmark=benchmark,
    )

    features = compute_features(event)
    if features is None:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data around breach date for {req.company}",
        )

    model = load_model()
    if model is None:
        model = _train_synthetic()["model"]

    report = generate_explanation(event, features, model)

    return ExplainResponse(
        company=report.company,
        ticker=report.ticker,
        breach_date=report.breach_date,
        steps=[CalculationStepModel(**s.__dict__) for s in report.steps],
        final_score=report.final_score,
        final_prediction=report.final_prediction,
        confidence=report.confidence,
        probabilities=report.probabilities,
        feature_contributions=report.feature_contributions,
        methodology=report.methodology,
        limitations=report.limitations,
    )


@app.post("/api/explain/auto", response_model=ExplainResponse)
async def explain_auto(req: ScoreRequest):
    """Auto-search breach data for a company/ticker and explain the most significant incident."""
    import re
    from .breach_search import search_breach_incidents

    ticker = resolve_ticker(req.company)
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"Could not resolve ticker for '{req.company}'")

    ticker = _validate_ticker(ticker)

    company_name = req.company
    try:
        from .ticker_resolver import KNOWN_TICKERS
        rev = {v.upper(): k for k, v in KNOWN_TICKERS.items() if v}
        bare = re.sub(r"\.(NS|BO|NSE|BSE|L|DE|TO|HK|SS|SZ)$", "", ticker.upper())
        if ticker.upper() in rev:
            company_name = rev[ticker.upper()].title()
        elif bare in rev:
            company_name = rev[bare].title()
    except Exception:
        pass

    incidents = await asyncio.to_thread(search_breach_incidents, company_name, 5)
    if incidents:
        top = max(incidents, key=lambda x: (x.records_affected, x.confidence))
        breach_date = top.date if top.date else req.breach_date
        records = top.records_affected if top.records_affected > 0 else req.records_affected
        breach_type = top.breach_type
    else:
        breach_date = req.breach_date
        records = req.records_affected
        breach_type = req.breach_type

    benchmark = detect_benchmark(ticker)

    stock_data, market_data = await asyncio.gather(
        asyncio.to_thread(fetch_stock_data, ticker, "2015-01-01"),
        asyncio.to_thread(fetch_market_data, "2015-01-01", benchmark),
    )
    if stock_data.empty:
        raise HTTPException(status_code=404, detail=f"No stock data for {ticker}")

    event = BreachEvent(
        company_name=company_name, ticker=ticker,
        breach_date=pd.Timestamp(breach_date),
        pwn_count=records, breach_type=breach_type,
        stock_data=stock_data, market_data=market_data,
        benchmark=benchmark,
    )

    features = compute_features(event)
    if features is None:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data around breach date {breach_date} for {company_name}",
        )

    model = load_model()
    if model is None:
        model = _train_synthetic()["model"]

    report = generate_explanation(event, features, model)

    return ExplainResponse(
        company=report.company,
        ticker=report.ticker,
        breach_date=report.breach_date,
        steps=[CalculationStepModel(**s.__dict__) for s in report.steps],
        final_score=report.final_score,
        final_prediction=report.final_prediction,
        confidence=report.confidence,
        probabilities=report.probabilities,
        feature_contributions=report.feature_contributions,
        methodology=report.methodology,
        limitations=report.limitations,
    )


@app.get("/api/config/presets", response_model=list[ConfigPreset])
async def get_config_presets():
    """Return predefined analysis configuration presets."""
    return [
        ConfigPreset(
            name="fast",
            description="Quick analysis — minimal windows, fastest computation",
            config=AnalysisConfigRequest(
                estimation_window=100, pre_event_window=10, post_event_window=20,
                recovery_max_days=30, car_long_end=15,
            ),
        ),
        ConfigPreset(
            name="standard",
            description="Balanced analysis — good accuracy with reasonable speed",
            config=AnalysisConfigRequest(),
        ),
        ConfigPreset(
            name="thorough",
            description="Deep analysis — maximum accuracy, slower computation",
            config=AnalysisConfigRequest(
                estimation_window=500, pre_event_window=60, post_event_window=120,
                recovery_max_days=180, car_long_end=60,
            ),
        ),
        ConfigPreset(
            name="conservative",
            description="Conservative thresholds — only flags clearly severe breaches",
            config=AnalysisConfigRequest(
                threshold_critical=-0.20, threshold_high=-0.10, threshold_medium=-0.05,
            ),
        ),
        ConfigPreset(
            name="sensitive",
            description="Sensitive thresholds — catches milder impacts",
            config=AnalysisConfigRequest(
                threshold_critical=-0.10, threshold_high=-0.05, threshold_medium=-0.01,
            ),
        ),
    ]


@app.get("/api/cache", response_model=CacheInfoResponse)
async def get_cache_info_endpoint():
    """Get info about cached stock data."""
    info = get_cache_info()
    return CacheInfoResponse(**info)


@app.delete("/api/cache")
async def clear_cache_endpoint(older_than_days: int = None):
    """Clear cached stock data."""
    count = clear_cache(older_than_days)
    return {"status": "ok", "cleared": count}


@app.get("/api/data-sources", response_model=DataSourceConfigResponse)
async def get_data_sources():
    """Get current data source configuration and status."""
    status = get_data_sources_status()
    sources = {name: DataSourceStatus(**info) for name, info in status.items()}
    return DataSourceConfigResponse(
        primary_source="yfinance",
        alpha_vantage_key_set=bool(os.environ.get("ALPHA_VANTAGE_API_KEY")),
        enable_fallback=True,
        cache_ttl_hours=24,
        sources=sources,
    )


@app.post("/api/data-sources/configure", response_model=DataSourceConfigResponse)
async def configure_data_sources(req: DataSourceConfigRequest):
    """Configure data source preferences (thread-safe via app.state)."""
    # Store in app.state instead of os.environ (thread-safe)
    if req.alpha_vantage_key:
        app.state.alpha_vantage_key = req.alpha_vantage_key

    from .data_sources import FetcherConfig, DataFetcher
    current_key = getattr(app.state, "alpha_vantage_key", req.alpha_vantage_key or "")
    config = FetcherConfig(
        primary_source=req.primary_source,
        alpha_vantage_key=current_key,
        enable_fallback=req.enable_fallback,
        cache_ttl_hours=req.cache_ttl_hours,
    )
    fetcher = DataFetcher(config)

    status = fetcher.get_source_status()
    sources = {name: DataSourceStatus(**info) for name, info in status.items()}

    return DataSourceConfigResponse(
        primary_source=req.primary_source,
        alpha_vantage_key_set=bool(current_key),
        enable_fallback=req.enable_fallback,
        cache_ttl_hours=req.cache_ttl_hours,
        sources=sources,
    )


@app.get("/api/data-sources/test/{source_name}")
async def test_data_source(source_name: str, ticker: str = "MSFT"):
    """Test a specific data source with a ticker.

    Use source_name='auto' to test the full fallback chain.
    """
    from .data_sources import (
        YFinanceSource, AlphaVantageSource, NSEIndiaSource,
        YahooFinanceScrapeSource, DataFetcher, FetcherConfig,
    )

    # Auto-resolve ticker if it looks like a company name
    resolved = resolve_ticker(ticker)
    if resolved and resolved != ticker:
        ticker = resolved

    if source_name == "auto":
        # Test full fallback chain
        fetcher = DataFetcher(FetcherConfig(
            alpha_vantage_key=os.environ.get("ALPHA_VANTAGE_API_KEY", ""),
        ))
        import time
        start_time = time.time()
        try:
            df = fetcher.fetch(ticker, start="2024-01-01")
        except Exception as e:
            return {
                "source": "auto (fallback chain)",
                "ticker": ticker,
                "success": False,
                "error": str(e),
            }
        elapsed = time.time() - start_time

        result = {
            "source": "auto (fallback chain)",
            "ticker": ticker,
            "success": not df.empty,
            "rows": len(df),
            "elapsed_seconds": round(elapsed, 2),
            "date_range": [
                str(df.index.min())[:10] if not df.empty else None,
                str(df.index.max())[:10] if not df.empty else None,
            ],
            "latest_close": float(df["Close"].iloc[-1]) if not df.empty and "Close" in df.columns else None,
        }
        if df.empty:
            result["error"] = (
                "All data sources returned no data. "
                "Yahoo Finance may be blocking requests — try installing curl_cffi: pip install curl_cffi"
            )
        return result

    sources = {
        "yfinance": YFinanceSource(),
        "alphavantage": AlphaVantageSource(os.environ.get("ALPHA_VANTAGE_API_KEY", "")),
        "nse_india": NSEIndiaSource(),
        "yahoo_scrape": YahooFinanceScrapeSource(),
    }

    source = sources.get(source_name)
    if not source:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source_name}. Use 'auto' for fallback chain.")

    if not source.supports_ticker(ticker):
        raise HTTPException(status_code=400, detail=f"Source {source_name} does not support ticker {ticker}")

    try:
        import time
        start_time = time.time()
        df = source.fetch(ticker, start="2024-01-01")
        elapsed = time.time() - start_time

        return {
            "source": source_name,
            "ticker": ticker,
            "success": not df.empty,
            "rows": len(df),
            "elapsed_seconds": round(elapsed, 2),
            "date_range": [
                str(df.index.min())[:10] if not df.empty else None,
                str(df.index.max())[:10] if not df.empty else None,
            ],
            "latest_close": float(df["Close"].iloc[-1]) if not df.empty and "Close" in df.columns else None,
        }
    except Exception as e:
        return {
            "source": source_name,
            "ticker": ticker,
            "success": False,
            "error": str(e),
        }


@app.get("/api/search")
async def search_ticker(q: str = "", limit: int = 10):
    """Search for stock tickers — instant local match first, network fallback.

    Supports company names (e.g., "Reliance"), partial tickers (e.g., "VEDL"),
    or full tickers (e.g., "MSFT"). Local KNOWN_TICKERS dict is searched first
    (instant), then Yahoo Finance + NSE India as fallback.
    """
    from .ticker_resolver import KNOWN_TICKERS

    if not q or len(q.strip()) < 1:
        return {"query": q, "results": [], "count": 0}

    query = q.strip()
    query_lower = query.lower()

    # --- Phase 1: Instant local match against KNOWN_TICKERS ---
    local_results = []
    seen = set()

    # Exact name match
    if query_lower in KNOWN_TICKERS and KNOWN_TICKERS[query_lower]:
        ticker = KNOWN_TICKERS[query_lower]
        local_results.append({"symbol": ticker, "name": query.title(), "ticker_full": ticker, "source": "local"})
        seen.add(ticker)

    # Partial name match
    if len(local_results) < limit:
        for name, ticker in KNOWN_TICKERS.items():
            if not ticker or ticker in seen:
                continue
            if query_lower in name or name.startswith(query_lower):
                local_results.append({"symbol": ticker, "name": name.title(), "ticker_full": ticker, "source": "local"})
                seen.add(ticker)
                if len(local_results) >= limit:
                    break

    # Bare ticker match (user typed "MSFT", "TCS", etc.)
    if len(local_results) < limit:
        query_upper = query.upper()
        for name, ticker in KNOWN_TICKERS.items():
            if not ticker or ticker in seen:
                continue
            bare = ticker.split(".")[0]
            if query_upper == bare or query_upper == ticker:
                local_results.append({"symbol": ticker, "name": name.title(), "ticker_full": ticker, "source": "local"})
                seen.add(ticker)
                if len(local_results) >= limit:
                    break

    # If we have enough local results, return immediately (no network)
    if len(local_results) >= limit:
        return {"query": query, "results": local_results[:limit], "count": len(local_results)}

    # --- Phase 2: Network fallback for unknown queries (cached) ---
    cached = _search_cache.get(query_lower)
    if cached is not None:
        network_results = cached
    else:
        from .ticker_search import smart_resolve
        network_results = await asyncio.to_thread(smart_resolve, query, limit)
        _search_cache[query_lower] = network_results

    for r in network_results:
        ticker = r.get("ticker_full", r.get("symbol", ""))
        if ticker and ticker not in seen:
            r["source"] = "network"
            local_results.append(r)
            seen.add(ticker)

    return {"query": query, "results": local_results[:limit], "count": len(local_results)}


@app.get("/api/breach-search")
async def search_breach(q: str = "", limit: int = 5):
    """Search for breach incidents for a company from the internet.

    Finds breach dates, types, and affected records from news sources.
    """
    from .breach_search import search_breach_incidents

    q = _validate_breach_search_query(q)
    limit = max(1, min(limit, 20))

    incidents = await asyncio.to_thread(search_breach_incidents, q, limit)

    return {
        "query": q,
        "incidents": [
            {
                "company": inc.company,
                "date": inc.date,
                "breach_type": inc.breach_type,
                "records_affected": inc.records_affected,
                "source": inc.source,
                "description": inc.description,
                "confidence": inc.confidence,
            }
            for inc in incidents
        ],
        "count": len(incidents),
    }


@app.get("/api/llm/status")
async def llm_status():
    """Check if LM Studio / LLM is available."""
    from .llm_integration import check_lm_studio, LLMConfig
    config = LLMConfig()
    status = check_lm_studio(config)
    return {
        "available": status["available"],
        "url": status["url"],
        "models": status.get("models", []),
        "default_model": status.get("default_model", ""),
        "error": status.get("error"),
    }


class LLMAnalysisRequest(BaseModel):
    dataset_summary: str = Field(..., description="Summary of the dataset")
    analysis_results: str = Field(..., description="Results from numerical analysis")
    model: str = Field(default="", description="Model name (empty = default)")


class LLMRiskRequest(BaseModel):
    company: str
    risk_score: float
    prediction: str
    features: dict


class LLMQuestionRequest(BaseModel):
    question: str = Field(..., description="Question about breach data")
    context: str = Field(default="", description="Additional context")


@app.post("/api/llm/analyze-dataset")
async def llm_analyze_dataset(req: LLMAnalysisRequest):
    """Use LLM to analyze a dataset and generate insights."""
    from .llm_integration import analyze_breach_dataset, LLMConfig

    config = LLMConfig()
    if req.model:
        config.model = req.model

    result = analyze_breach_dataset(
        dataset_summary=req.dataset_summary,
        analysis_results=req.analysis_results,
        config=config,
    )

    if result is None:
        raise HTTPException(
            status_code=503,
            detail="LLM unavailable. Make sure LM Studio is running on 192.168.56.1:1234",
        )

    return {"analysis": result, "model": config.model}


@app.post("/api/llm/risk-summary")
async def llm_risk_summary(req: LLMRiskRequest):
    """Generate a natural language risk summary for a company."""
    from .llm_integration import generate_risk_summary, LLMConfig

    config = LLMConfig()
    result = generate_risk_summary(
        company=req.company,
        risk_score=req.risk_score,
        prediction=req.prediction,
        features=req.features,
        config=config,
    )

    if result is None:
        raise HTTPException(
            status_code=503,
            detail="LLM unavailable. Make sure LM Studio is running on 192.168.56.1:1234",
        )

    return {"summary": result, "model": config.model}


@app.post("/api/llm/ask")
async def llm_ask(req: LLMQuestionRequest):
    """Ask a question about breach data using the LLM."""
    from .llm_integration import answer_breach_question, LLMConfig

    config = LLMConfig()
    result = answer_breach_question(
        question=req.question,
        context=req.context,
        config=config,
    )

    if result is None:
        raise HTTPException(
            status_code=503,
            detail="LLM unavailable. Make sure LM Studio is running on 192.168.56.1:1234",
        )

    return {"answer": result, "model": config.model}


@app.post("/api/llm/enrich")
async def llm_enrich_records(records: list[dict]):
    """Enrich breach records with LLM-generated context."""
    from .llm_integration import enrich_breach_records, LLMConfig

    config = LLMConfig()
    enriched = enrich_breach_records(records, config=config)

    if enriched is None:
        raise HTTPException(
            status_code=503,
            detail="LLM unavailable. Make sure LM Studio is running on 192.168.56.1:1234",
        )

    return {"enriched": enriched, "count": len(enriched), "model": config.model}


@app.post("/api/score/config", response_model=ScoreResponse)
async def score_with_config(req: ScoreRequest, config: AnalysisConfigRequest = None):
    """Score a company with custom analysis configuration."""
    if config is None:
        config = AnalysisConfigRequest()

    ticker = resolve_ticker(req.company)
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"Could not resolve ticker for '{req.company}'")

    ticker = _validate_ticker(ticker)
    benchmark = detect_benchmark(ticker)

    stock_data, market_data = await asyncio.gather(
        asyncio.to_thread(fetch_stock_data, ticker, config.start_date),
        asyncio.to_thread(fetch_market_data, config.start_date, benchmark),
    )
    if stock_data.empty:
        raise HTTPException(status_code=404, detail=f"No stock data available for {ticker}")

    feature_config = FeatureConfig(
        estimation_window=config.estimation_window,
        pre_event_window=config.pre_event_window,
        post_event_window=config.post_event_window,
        recovery_max_days=config.recovery_max_days,
        threshold_critical=config.threshold_critical,
        threshold_high=config.threshold_high,
        threshold_medium=config.threshold_medium,
        car_short_start=config.car_short_start,
        car_short_end=config.car_short_end,
        car_long_start=config.car_long_start,
        car_long_end=config.car_long_end,
    )

    event = BreachEvent(
        company_name=req.company, ticker=ticker,
        breach_date=pd.Timestamp(req.breach_date),
        pwn_count=req.records_affected, breach_type=req.breach_type,
        stock_data=stock_data, market_data=market_data,
        benchmark=benchmark,
    )

    features = compute_features(event, feature_config)
    if features is None:
        raise HTTPException(status_code=422, detail=f"Insufficient data for {req.company}")

    model = load_model()
    if model is None:
        model = _train_synthetic()["model"]

    features_df = pd.DataFrame([features.to_dict()])
    prediction = predict_severity(model, features_df)

    return ScoreResponse(
        company=req.company, ticker=ticker,
        risk_score=prediction["risk_score"], prediction=prediction["prediction"],
        confidence=prediction["confidence"], probabilities=prediction["probabilities"],
        features=FeatureDetail(
            abnormal_return_day0=features.abnormal_return_day0,
            abnormal_return_day1=features.abnormal_return_day1,
            abnormal_return_day5=features.abnormal_return_day5,
            abnormal_return_day30=features.abnormal_return_day30,
            car_minus1_plus1=features.car_minus1_plus1,
            car_minus5_plus30=features.car_minus5_plus30,
            volatility_spike=features.volatility_spike,
            volume_change=features.volume_change,
            time_to_recovery=features.time_to_recovery,
            severity=classify_severity(features.car_minus5_plus30, feature_config),
        ),
    )


@app.post("/api/upload/config", response_model=UploadResponse)
async def upload_with_config(file: UploadFile = File(...), config: UploadConfigRequest = None):
    """Upload dataset with custom preprocessing configuration."""
    if config is None:
        config = UploadConfigRequest()

    allowed_types = {".csv", ".xlsx", ".xls", ".tsv"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            total_size = 0
            while True:
                chunk = await file.read(8192)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > _MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum upload size is {_MAX_UPLOAD_BYTES // (1024*1024)} MB.",
                    )
                tmp.write(chunk)
            tmp_path = tmp.name

        preprocess_config = PreprocessConfig(
            column_mapping=config.column_mapping,
            date_format=config.date_format,
            records_threshold=config.records_threshold,
            start_date=config.start_date,
            end_date=config.end_date,
            ticker_overrides=config.ticker_overrides,
            skip_ticker_resolution=config.skip_ticker_resolution,
            max_rows=config.max_rows,
        )
        result = await asyncio.to_thread(preprocess_dataset, tmp_path, preprocess_config)
        return UploadResponse(
            success=result.success, original_rows=result.original_rows,
            cleaned_rows=result.cleaned_rows, columns_detected=result.columns_detected,
            column_mapping=result.column_mapping, ticker_resolution_rate=result.ticker_resolution_rate,
            preview=result.preview, errors=result.errors, warnings=result.warnings,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload preprocessing failed: %s", e)
        raise HTTPException(status_code=500, detail="Preprocessing failed")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/api/upload/analyze/config", response_model=BatchResponse)
async def upload_analyze_with_config(file: UploadFile = File(...), config: UploadConfigRequest = None):
    """Upload and analyze with custom configuration."""
    if config is None:
        config = UploadConfigRequest()

    allowed_types = {".csv", ".xlsx", ".xls", ".tsv"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            total_size = 0
            while True:
                chunk = await file.read(8192)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > _MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum upload size is {_MAX_UPLOAD_BYTES // (1024*1024)} MB.",
                    )
                tmp.write(chunk)
            tmp_path = tmp.name

        preprocess_config = PreprocessConfig(
            column_mapping=config.column_mapping,
            date_format=config.date_format,
            records_threshold=config.records_threshold,
            start_date=config.start_date,
            end_date=config.end_date,
            ticker_overrides=config.ticker_overrides,
            skip_ticker_resolution=config.skip_ticker_resolution,
            max_rows=config.max_rows,
        )
        result = await asyncio.to_thread(preprocess_dataset, tmp_path, preprocess_config)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload preprocessing failed: %s", e)
        raise HTTPException(status_code=500, detail="Preprocessing failed")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not result.success or result.df is None:
        return BatchResponse(total=0, analyzed=0, failed=0, results=[])

    df = result.df

    # Batch fetch all stock data at once (optimized)
    tickers = [str(t) for t in df["ticker"].dropna().unique() if t]
    stock_cache = fetch_stock_batch(tickers, start=config.start_date if hasattr(config, 'start_date') else "2010-01-01")

    model = load_model()
    if model is None:
        model = _train_synthetic()["model"]

    # Build events list
    events = []
    skipped = []
    for _, row in df.iterrows():
        company = str(row.get("company_name", ""))
        ticker = str(row.get("ticker", ""))
        breach_date = row.get("breach_date")
        records = int(row.get("records_affected", 0))
        breach_type = str(row.get("breach_type", "data_leak"))

        if not company or pd.isna(breach_date) or not ticker or ticker == "nan":
            skipped.append(BatchResult(
                company=company, ticker=ticker or "N/A", breach_date=str(breach_date)[:10] if not pd.isna(breach_date) else "N/A",
                records_affected=records, breach_type=breach_type,
                risk_score=0, prediction="unknown", confidence=0,
                probabilities={}, status="skipped",
                error="Missing company, date, or ticker",
            ))
            continue

        stock_data = stock_cache.get(ticker, pd.DataFrame())
        if stock_data.empty:
            skipped.append(BatchResult(
                company=company, ticker=ticker, breach_date=str(breach_date)[:10],
                records_affected=records, breach_type=breach_type,
                risk_score=0, prediction="unknown", confidence=0,
                probabilities={}, status="failed", error=f"No stock data for {ticker}",
            ))
            continue

        bm = detect_benchmark(ticker)
        market_data = fetch_market_data(start="2010-01-01", benchmark=bm)
        events.append(BreachEvent(
            company_name=company, ticker=ticker,
            breach_date=pd.Timestamp(breach_date),
            pwn_count=records, breach_type=breach_type,
            stock_data=stock_data, market_data=market_data,
            benchmark=bm,
        ))

    # Batch compute features (parallel)
    features_df = compute_features_batch(events)

    # Batch predict
    results = []
    for _, feat_row in features_df.iterrows():
        features_dict = feat_row.to_dict()
        features_df_single = pd.DataFrame([features_dict])
        try:
            pred = predict_severity(model, features_df_single)
            results.append(BatchResult(
                company=features_dict["company_name"], ticker=features_dict["ticker"],
                breach_date=features_dict["breach_date"],
                records_affected=int(features_dict["pwn_count"]),
                breach_type=features_dict["breach_type"],
                risk_score=pred["risk_score"], prediction=pred["prediction"],
                confidence=pred["confidence"], probabilities=pred["probabilities"],
                status="ok",
            ))
        except Exception as e:
            results.append(BatchResult(
                company=features_dict.get("company_name", "?"), ticker=features_dict.get("ticker", "?"),
                breach_date=features_dict.get("breach_date", "?"),
                records_affected=int(features_dict.get("pwn_count", 0)),
                breach_type=features_dict.get("breach_type", "?"),
                risk_score=0, prediction="error", confidence=0,
                probabilities={}, status="failed", error=str(e),
            ))

    all_results = results + skipped
    analyzed = sum(1 for r in all_results if r.status == "ok")
    failed = sum(1 for r in all_results if r.status in ("failed", "skipped"))

    return BatchResponse(total=len(all_results), analyzed=analyzed, failed=failed, results=all_results)


# ── Static File Serving (Production) ──────────────────────────────────────

from pathlib import Path
from fastapi.responses import FileResponse

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for all non-API routes."""
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="API route not found")
        resolved = (FRONTEND_DIR / full_path).resolve()
        if not str(resolved).startswith(str(FRONTEND_DIR.resolve())):
            return FileResponse(FRONTEND_DIR / "index.html")
        if resolved.exists() and resolved.is_file():
            return FileResponse(resolved)
        return FileResponse(FRONTEND_DIR / "index.html")
