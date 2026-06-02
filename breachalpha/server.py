"""FastAPI backend for BreachAlpha.

Run with:
    uvicorn breachalpha.server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import re
import time

import structlog
import numpy as np
import pandas as pd
from cachetools import TTLCache
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .schemas import (
    ScoreRequest, ExplainRequest, TrainRequest, AnalysisConfigRequest,
    UploadConfigRequest, DataSourceConfigRequest, LLMAnalysisRequest,
    LLMRiskRequest, LLMQuestionRequest, FeatureDetail, ScoreResponse,
    AutoScoreResponse, DemoCase, TrainResponse, HealthResponse,
    UploadResponse, BatchResult, BatchResponse, CalculationStepModel,
    ExplainResponse, CacheInfoResponse, ConfigPreset, DataSourceStatus,
    DataSourceConfigResponse,
)

# Bounded TTL cache for network search results (prevents memory DoS)
_search_cache: TTLCache = TTLCache(maxsize=1000, ttl=300)

# ── Security Constants ───────────────────────────────────────────────────
_ADMIN_KEY = os.environ.get("BREACHALPHA_ADMIN_KEY", "")

from .feature_engine import BreachEvent, compute_features, compute_features_batch, classify_severity, AnalysisConfig as FeatureConfig
from .model import load_model, predict_severity, train_model, save_model
from .stock_loader import (
    fetch_stock_data, fetch_market_data, fetch_stock_batch,
    get_cache_info, clear_cache, get_data_sources_status,
)
from .ticker_resolver import resolve_ticker, detect_benchmark
from .preprocessor import preprocess_dataset, PreprocessingResult, PreprocessConfig
from .explainability import generate_explanation, ExplainabilityReport
from .data_sources import DataFetcher, FetcherConfig
from .core.constants import (
    RISK_WEIGHTS, FEATURE_COLS, SEVERITY_LABELS,
    MAX_UPLOAD_BYTES, ALLOWED_UPLOAD_EXTENSIONS, TICKER_RE,
)
from .services.file_upload import validate_upload_extension, save_upload, cleanup_upload
from .services.model import get_or_train_model, score_features, batch_score, _train_synthetic
from .services.scoring import (
    validate_ticker as _validate_ticker_svc,
    resolve_company_name_from_ticker,
    fetch_breach_data,
    build_breach_event,
    score_company as score_company_svc,
)

# Structured logging configuration
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger(__name__)

app = FastAPI(
    title="BreachAlpha API",
    description="Quantify the financial impact of cybersecurity incidents",
    version="0.1.0",
)

# Rate limiting: in-memory storage (single-server; use Redis for multi-instance)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    headers_enabled=False,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_CORS_ORIGINS = os.environ.get(
    "BREACHALPHA_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
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
        if is_admin:
            if not _ADMIN_KEY:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Admin endpoints disabled. Set BREACHALPHA_ADMIN_KEY environment variable."},
                )
            key = request.headers.get("X-Admin-Key", "")
            if not hmac.compare_digest(key, _ADMIN_KEY):
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
    try:
        return _validate_ticker_svc(ticker)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _validate_breach_search_query(q: str) -> str:
    """Validate breach search query to prevent injection/SSRF."""
    q = q.strip()
    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters.")
    if len(q) > 100:
        raise HTTPException(status_code=400, detail="Query too long (max 100 characters).")
    return q


# ── Endpoints ─────────────────────────────────────────────────────────────


@app.get("/api/health", response_model=HealthResponse)
@limiter.exempt
async def health_check(request: Request):
    """Health check endpoint."""
    model = load_model()
    return HealthResponse(
        status="ok",
        model_loaded=model is not None,
        version="0.1.0",
    )


@app.post("/api/score", response_model=ScoreResponse)
@limiter.limit("10/minute")
async def score_company(request: Request, req: ScoreRequest):
    """Score a company for breach impact."""
    response, _ = await score_company_svc(
        company_name=req.company,
        breach_date=req.breach_date,
        records_affected=req.records_affected,
        breach_type=req.breach_type,
    )
    return response


@app.post("/api/score/auto", response_model=AutoScoreResponse)
@limiter.limit("5/minute")
async def score_auto(request: Request, req: ScoreRequest):
    """Search for real breach data and score using the most significant incident."""
    from .breach_search import search_breach_incidents

    ticker = resolve_ticker(req.company)
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"Could not resolve ticker for '{req.company}'")

    ticker = _validate_ticker(ticker)

    company_name = resolve_company_name_from_ticker(ticker)

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

    features = await asyncio.to_thread(compute_features, event)
    if features is None:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data around breach date {breach_date} for {company_name}",
        )

    model = get_or_train_model()

    features_df = pd.DataFrame([features.to_dict()])
    prediction = score_features(model, features_df)

    return AutoScoreResponse(
        company=req.company, ticker=ticker,
        risk_score=prediction["risk_score"],
        prediction=prediction["prediction"],
        confidence=prediction["confidence"],
        probabilities=prediction["probabilities"],
        features=FeatureDetail.from_features(features, classify_severity(features.car_minus5_plus30)),
        breach_found=breach_found,
        breach_date_used=breach_date,
        records_used=records,
        breach_type_used=breach_type,
        breach_confidence=breach_confidence,
        incident_count=len(incidents),
    )


@app.get("/api/demo", response_model=list[DemoCase])
@limiter.limit("30/minute")
async def run_demo(request: Request):
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
    model = get_or_train_model()

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

            features = await asyncio.to_thread(compute_features, event)
            if features is not None:
                features_df = pd.DataFrame([features.to_dict()])
                pred = predict_severity(model, features_df)
                case.risk_score = pred["risk_score"]
                case.prediction = pred["prediction"]
                case.confidence = pred["confidence"]
        except Exception as e:
            log.error("demo_failed", company=case.company, error=str(e))

    return demo_cases


@app.post("/api/train", response_model=TrainResponse)
@limiter.limit("1/minute")
async def train_model_endpoint(request: Request, req: TrainRequest):
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


@app.post("/api/upload", response_model=UploadResponse)
@limiter.limit("5/minute")
async def upload_dataset(request: Request, file: UploadFile = File(...)):
    """Upload and preprocess a breach dataset (CSV, XLSX, Excel)."""
    suffix = validate_upload_extension(file.filename)
    tmp_path = None
    try:
        tmp_path = await save_upload(file, suffix)
        result = await asyncio.to_thread(preprocess_dataset, str(tmp_path))
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
        log.error("upload_preprocessing_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Preprocessing failed")
    finally:
        cleanup_upload(tmp_path)


@app.post("/api/upload/analyze", response_model=BatchResponse)
@limiter.limit("2/minute")
async def upload_and_analyze(request: Request, file: UploadFile = File(...)):
    """Upload a dataset and analyze all breaches in it."""
    suffix = validate_upload_extension(file.filename)
    tmp_path = None
    try:
        tmp_path = await save_upload(file, suffix)
        result = await asyncio.to_thread(preprocess_dataset, str(tmp_path))
    finally:
        cleanup_upload(tmp_path)

    if not result.success or result.df is None:
        return BatchResponse(total=0, analyzed=0, failed=0, results=[])

    # Run the analysis pipeline in a thread to avoid blocking the event loop
    raw_results = await asyncio.to_thread(_run_analysis_pipeline, result)

    # Convert dicts to BatchResult models
    results = [BatchResult(**r) for r in raw_results]
    analyzed = sum(1 for r in results if r.status == "ok")

    return BatchResponse(total=len(results), analyzed=analyzed, failed=len(results)-analyzed, results=results)


@app.post("/api/explain", response_model=ExplainResponse)
@limiter.limit("10/minute")
async def explain_score(request: Request, req: ExplainRequest):
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

    features = await asyncio.to_thread(compute_features, event)
    if features is None:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data around breach date for {req.company}",
        )

    model = get_or_train_model()

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
@limiter.limit("5/minute")
async def explain_auto(request: Request, req: ScoreRequest):
    """Auto-search breach data for a company/ticker and explain the most significant incident."""
    from .breach_search import search_breach_incidents

    ticker = resolve_ticker(req.company)
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"Could not resolve ticker for '{req.company}'")

    ticker = _validate_ticker(ticker)

    company_name = resolve_company_name_from_ticker(ticker)

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

    features = await asyncio.to_thread(compute_features, event)
    if features is None:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data around breach date {breach_date} for {company_name}",
        )

    model = get_or_train_model()

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
@limiter.exempt
async def get_config_presets(request: Request):
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
@limiter.exempt
async def get_cache_info_endpoint(request: Request):
    """Get info about cached stock data."""
    info = get_cache_info()
    return CacheInfoResponse(**info)


@app.delete("/api/cache")
@limiter.exempt
async def clear_cache_endpoint(request: Request, older_than_days: int = None):
    """Clear cached stock data."""
    count = clear_cache(older_than_days)
    return {"status": "ok", "cleared": count}


@app.get("/api/data-sources", response_model=DataSourceConfigResponse)
@limiter.exempt
async def get_data_sources(request: Request):
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
@limiter.limit("10/minute")
async def configure_data_sources(request: Request, req: DataSourceConfigRequest):
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
@limiter.limit("10/minute")
async def test_data_source(request: Request, source_name: str, ticker: str = "MSFT"):
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
        start_time = time.time()
        try:
            df = await asyncio.to_thread(fetcher.fetch, ticker, start="2024-01-01")
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
        start_time = time.time()
        df = await asyncio.to_thread(source.fetch, ticker, start="2024-01-01")
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
@limiter.limit("30/minute")
async def search_ticker(request: Request, q: str = "", limit: int = 10):
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
@limiter.limit("10/minute")
async def search_breach(request: Request, q: str = "", limit: int = 5):
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
@limiter.exempt
async def llm_status(request: Request):
    """Check if LM Studio / LLM is available."""
    from .llm_integration import check_lm_studio, LLMConfig
    config = LLMConfig()
    status = await asyncio.to_thread(check_lm_studio, config)
    return {
        "available": status["available"],
        "url": status["url"],
        "models": status.get("models", []),
        "default_model": status.get("default_model", ""),
        "error": status.get("error"),
    }


@app.post("/api/llm/analyze-dataset")
@limiter.limit("5/minute")
async def llm_analyze_dataset(request: Request, req: LLMAnalysisRequest):
    """Use LLM to analyze a dataset and generate insights."""
    from .llm_integration import analyze_breach_dataset, LLMConfig

    config = LLMConfig()
    if req.model:
        config.model = req.model

    result = await asyncio.to_thread(analyze_breach_dataset,
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
@limiter.limit("10/minute")
async def llm_risk_summary(request: Request, req: LLMRiskRequest):
    """Generate a natural language risk summary for a company."""
    from .llm_integration import generate_risk_summary, LLMConfig

    config = LLMConfig()
    result = await asyncio.to_thread(generate_risk_summary,
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
@limiter.limit("10/minute")
async def llm_ask(request: Request, req: LLMQuestionRequest):
    """Ask a question about breach data using the LLM."""
    from .llm_integration import answer_breach_question, LLMConfig

    config = LLMConfig()
    result = await asyncio.to_thread(answer_breach_question,
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
@limiter.limit("5/minute")
async def llm_enrich_records(request: Request, records: list[dict]):
    """Enrich breach records with LLM-generated context."""
    from .llm_integration import enrich_breach_records, LLMConfig

    config = LLMConfig()
    enriched = await asyncio.to_thread(enrich_breach_records, records, config=config)

    if enriched is None:
        raise HTTPException(
            status_code=503,
            detail="LLM unavailable. Make sure LM Studio is running on 192.168.56.1:1234",
        )

    return {"enriched": enriched, "count": len(enriched), "model": config.model}


@app.post("/api/score/config", response_model=ScoreResponse)
@limiter.limit("10/minute")
async def score_with_config(request: Request, req: ScoreRequest, config: AnalysisConfigRequest = None):
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

    features = await asyncio.to_thread(compute_features, event, feature_config)
    if features is None:
        raise HTTPException(status_code=422, detail=f"Insufficient data for {req.company}")

    model = get_or_train_model()

    features_df = pd.DataFrame([features.to_dict()])
    prediction = score_features(model, features_df)

    return ScoreResponse(
        company=req.company, ticker=ticker,
        risk_score=prediction["risk_score"], prediction=prediction["prediction"],
        confidence=prediction["confidence"], probabilities=prediction["probabilities"],
        features=FeatureDetail.from_features(features, classify_severity(features.car_minus5_plus30, feature_config)),
    )


@app.post("/api/upload/config", response_model=UploadResponse)
@limiter.limit("5/minute")
async def upload_with_config(request: Request, file: UploadFile = File(...), config: UploadConfigRequest = None):
    """Upload dataset with custom preprocessing configuration."""
    if config is None:
        config = UploadConfigRequest()

    suffix = validate_upload_extension(file.filename)
    tmp_path = None
    try:
        tmp_path = await save_upload(file, suffix)

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
        result = await asyncio.to_thread(preprocess_dataset, str(tmp_path), preprocess_config)
        return UploadResponse(
            success=result.success, original_rows=result.original_rows,
            cleaned_rows=result.cleaned_rows, columns_detected=result.columns_detected,
            column_mapping=result.column_mapping, ticker_resolution_rate=result.ticker_resolution_rate,
            preview=result.preview, errors=result.errors, warnings=result.warnings,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error("upload_preprocessing_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Preprocessing failed")
    finally:
        cleanup_upload(tmp_path)


@app.post("/api/upload/analyze/config", response_model=BatchResponse)
@limiter.limit("2/minute")
async def upload_analyze_with_config(request: Request, file: UploadFile = File(...), config: UploadConfigRequest = None):
    """Upload and analyze with custom configuration."""
    if config is None:
        config = UploadConfigRequest()

    suffix = validate_upload_extension(file.filename)
    tmp_path = None
    try:
        tmp_path = await save_upload(file, suffix)

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
        result = await asyncio.to_thread(preprocess_dataset, str(tmp_path), preprocess_config)
    except HTTPException:
        raise
    except Exception as e:
        log.error("upload_preprocessing_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Preprocessing failed")
    finally:
        cleanup_upload(tmp_path)

    if not result.success or result.df is None:
        return BatchResponse(total=0, analyzed=0, failed=0, results=[])

    df = result.df

    # Batch fetch all stock data at once (optimized)
    tickers = [str(t) for t in df["ticker"].dropna().unique() if t]
    stock_cache = fetch_stock_batch(tickers, start=config.start_date if hasattr(config, 'start_date') else "2010-01-01")

    model = get_or_train_model()

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


def _run_analysis_pipeline(preprocess_result) -> list[dict]:
    """Run batch analysis on preprocessed dataset. Used by /api/upload/analyze."""
    df = preprocess_result.df

    tickers = [str(t) for t in df["ticker"].dropna().unique() if t]
    stock_cache = fetch_stock_batch(tickers, start="2010-01-01")

    model = get_or_train_model()

    events = []
    skipped = []
    for _, row in df.iterrows():
        company = str(row.get("company_name", ""))
        ticker = str(row.get("ticker", ""))
        breach_date = row.get("breach_date")
        records = int(row.get("records_affected", 0))
        breach_type = str(row.get("breach_type", "data_leak"))

        if not company or pd.isna(breach_date) or not ticker or ticker == "nan":
            skipped.append({
                "company": company, "ticker": ticker or "N/A",
                "breach_date": str(breach_date)[:10] if not pd.isna(breach_date) else "N/A",
                "records_affected": records, "breach_type": breach_type,
                "risk_score": 0, "prediction": "unknown", "confidence": 0,
                "probabilities": {}, "status": "skipped",
                "error": "Missing company, date, or ticker",
            })
            continue

        stock_data = stock_cache.get(ticker, pd.DataFrame())
        if stock_data.empty:
            skipped.append({
                "company": company, "ticker": ticker,
                "breach_date": str(breach_date)[:10],
                "records_affected": records, "breach_type": breach_type,
                "risk_score": 0, "prediction": "unknown", "confidence": 0,
                "probabilities": {}, "status": "failed",
                "error": f"No stock data for {ticker}",
            })
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

    features_df = compute_features_batch(events)

    results = []
    for _, feat_row in features_df.iterrows():
        features_dict = feat_row.to_dict()
        features_df_single = pd.DataFrame([features_dict])
        try:
            pred = predict_severity(model, features_df_single)
            results.append({
                "company": features_dict["company_name"],
                "ticker": features_dict["ticker"],
                "breach_date": features_dict["breach_date"],
                "records_affected": int(features_dict["pwn_count"]),
                "breach_type": features_dict["breach_type"],
                "risk_score": pred["risk_score"], "prediction": pred["prediction"],
                "confidence": pred["confidence"], "probabilities": pred["probabilities"],
                "status": "ok",
            })
        except Exception as e:
            results.append({
                "company": features_dict.get("company_name", "?"),
                "ticker": features_dict.get("ticker", "?"),
                "breach_date": features_dict.get("breach_date", "?"),
                "records_affected": int(features_dict.get("pwn_count", 0)),
                "breach_type": features_dict.get("breach_type", "?"),
                "risk_score": 0, "prediction": "error", "confidence": 0,
                "probabilities": {}, "status": "failed", "error": str(e),
            })

    return results + skipped


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
