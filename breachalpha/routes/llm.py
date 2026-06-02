"""LLM integration endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from ..schemas import (
    LLMAnalysisRequest, LLMRiskRequest, LLMQuestionRequest,
    LLMStatusResponse, LLMAnalysisResponse, LLMSummaryResponse,
    LLMAnswerResponse, LLMEnrichResponse,
)
from ..core.exceptions import LLMUnavailableError


def create_llm_routes(limiter) -> APIRouter:
    router = APIRouter()

    @router.get("/api/llm/status", response_model=LLMStatusResponse)
    @limiter.exempt
    async def llm_status(request: Request):
        from ..llm_integration import check_lm_studio, LLMConfig
        config = LLMConfig()
        status = await asyncio.to_thread(check_lm_studio, config)
        return LLMStatusResponse(
            available=status["available"],
            url=status["url"],
            models=status.get("models", []),
            default_model=status.get("default_model", ""),
            error=status.get("error"),
        )

    @router.post("/api/llm/analyze-dataset", response_model=LLMAnalysisResponse)
    @limiter.limit("5/minute")
    async def llm_analyze_dataset(request: Request, req: LLMAnalysisRequest):
        from ..llm_integration import analyze_breach_dataset, LLMConfig

        config = LLMConfig()
        if req.model:
            config.model = req.model

        result = await asyncio.to_thread(analyze_breach_dataset,
            dataset_summary=req.dataset_summary,
            analysis_results=req.analysis_results,
            config=config,
        )

        if result is None:
            raise LLMUnavailableError()

        return LLMAnalysisResponse(analysis=result, model=config.model)

    @router.post("/api/llm/risk-summary", response_model=LLMSummaryResponse)
    @limiter.limit("10/minute")
    async def llm_risk_summary(request: Request, req: LLMRiskRequest):
        from ..llm_integration import generate_risk_summary, LLMConfig

        config = LLMConfig()
        result = await asyncio.to_thread(generate_risk_summary,
            company=req.company, risk_score=req.risk_score,
            prediction=req.prediction, features=req.features, config=config,
        )

        if result is None:
            raise LLMUnavailableError()

        return LLMSummaryResponse(summary=result, model=config.model)

    @router.post("/api/llm/ask", response_model=LLMAnswerResponse)
    @limiter.limit("10/minute")
    async def llm_ask(request: Request, req: LLMQuestionRequest):
        from ..llm_integration import answer_breach_question, LLMConfig, check_prompt_injection

        if len(req.question) > 5000:
            raise HTTPException(status_code=400, detail="Question too long (max 5000 characters).")
        if req.context and len(req.context) > 10000:
            raise HTTPException(status_code=400, detail="Context too long (max 10000 characters).")
        if check_prompt_injection(req.question):
            raise HTTPException(status_code=400, detail="Your question contains patterns that may indicate prompt injection. Please rephrase.")

        config = LLMConfig()
        result = await asyncio.to_thread(answer_breach_question,
            question=req.question, context=req.context, config=config,
        )

        if result is None:
            raise LLMUnavailableError()

        return LLMAnswerResponse(answer=result, model=config.model)

    @router.post("/api/llm/enrich", response_model=LLMEnrichResponse)
    @limiter.limit("5/minute")
    async def llm_enrich_records(request: Request, records: list[dict]):
        from ..llm_integration import enrich_breach_records, LLMConfig

        config = LLMConfig()
        enriched = await asyncio.to_thread(enrich_breach_records, records, config=config)

        if enriched is None:
            raise LLMUnavailableError()

        return LLMEnrichResponse(enriched=enriched, count=len(enriched), model=config.model)

    return router
