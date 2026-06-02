"""LLM integration for BreachAlpha using LM Studio (local Qwen 3.5 9B).

Connects to LM Studio's OpenAI-compatible API at http://localhost:1234.
Used for:
- Enriching breach datasets with natural language analysis
- Generating risk summaries from financial data
- Parsing unstructured breach descriptions into structured data
- Answering questions about breach impact patterns
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# LM Studio default endpoint — configurable via BREACHALPHA_LLM_URL env var
DEFAULT_LM_STUDIO_URL = os.environ.get("BREACHALPHA_LLM_URL", "http://192.168.56.1:1234/v1")


@dataclass
class LLMConfig:
    """Configuration for LLM connection."""
    base_url: str = DEFAULT_LM_STUDIO_URL
    model: str = "qwen3.5-9b"  # Default model name in LM Studio
    temperature: float = 0.3
    max_tokens: int = 2048
    timeout: int = 60


def _get_session():
    """Get HTTP session for LM Studio API."""
    try:
        from curl_cffi import requests as curl_requests
        return curl_requests.Session(impersonate="chrome"), True
    except ImportError:
        import requests
        return requests.Session(), False


def check_lm_studio(config: LLMConfig = None) -> dict:
    """Check if LM Studio is running and what models are available."""
    if config is None:
        config = LLMConfig()

    session, _ = _get_session()
    result = {"available": False, "models": [], "url": config.base_url}

    try:
        resp = session.get(f"{config.base_url}/models", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data", [])
            result["available"] = True
            result["models"] = [m.get("id", "") for m in models]
            if models:
                result["default_model"] = models[0].get("id", "")
    except Exception as e:
        logger.debug("LM Studio not available: %s", e)
        result["error"] = str(e)

    return result


def chat_completion(
    prompt: str,
    config: LLMConfig = None,
    system_prompt: str = None,
    temperature: float = None,
    max_tokens: int = None,
) -> Optional[str]:
    """Send a chat completion request to LM Studio.

    Returns the assistant's response as a string, or None if failed.
    """
    if config is None:
        config = LLMConfig()

    session, _ = _get_session()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature or config.temperature,
        "max_tokens": max_tokens or config.max_tokens,
        "stream": False,
    }

    try:
        resp = session.post(
            f"{config.base_url}/chat/completions",
            json=payload,
            timeout=config.timeout,
        )

        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        else:
            logger.warning("LM Studio returned status %d: %s", resp.status_code, resp.text[:200])

    except Exception as e:
        logger.warning("LM Studio request failed: %s", e)

    return None


# ── Breach Analysis Prompts ──────────────────────────────────────────────

SYSTEM_PROMPT_RISK_ANALYST = """You are a cybersecurity risk analyst specializing in quantifying
the financial impact of data breaches on publicly traded companies.

Your analysis should be:
- Concise and data-driven
- Focused on financial metrics (stock impact, recovery time, severity)
- Based on the event study methodology
- Grounded in the provided data, not speculation

Always structure your response with clear sections."""

SYSTEM_PROMPT_BREACH_ENRICHER = """You are a data enrichment assistant for cybersecurity breach datasets.
Given breach records, extract and standardize:
- Company name normalization
- Breach type classification
- Estimated severity based on records affected
- Potential financial impact keywords

Output structured JSON when possible."""


def analyze_breach_dataset(
    dataset_summary: str,
    analysis_results: str,
    config: LLMConfig = None,
) -> Optional[str]:
    """Use LLM to analyze a dataset of breaches and generate insights.

    Args:
        dataset_summary: Summary of the uploaded dataset
        analysis_results: Results from the numerical analysis
        config: LLM configuration

    Returns:
        Natural language analysis of the breach dataset
    """
    prompt = f"""Analyze this cybersecurity breach dataset and its financial impact analysis:

## Dataset Summary
{dataset_summary}

## Analysis Results
{analysis_results}

Provide:
1. **Key Findings**: What patterns emerge from the data?
2. **Risk Assessment**: Which companies show highest financial exposure?
3. **Impact Patterns**: What breach types cause the most damage?
4. **Recovery Insights**: What does recovery time tell us?
5. **Recommendations**: What should investors/watchers focus on?

Be specific with numbers from the data. Max 500 words."""

    return chat_completion(
        prompt=prompt,
        config=config,
        system_prompt=SYSTEM_PROMPT_RISK_ANALYST,
        max_tokens=1500,
    )


def generate_risk_summary(
    company: str,
    risk_score: float,
    prediction: str,
    features: dict,
    config: LLMConfig = None,
) -> Optional[str]:
    """Generate a natural language risk summary for a company.

    Args:
        company: Company name
        risk_score: Risk score (0-100)
        prediction: Severity prediction (low/medium/high/critical)
        features: Feature dictionary from analysis
        config: LLM configuration

    Returns:
        Human-readable risk summary
    """
    prompt = f"""Generate a concise risk summary for {company} based on this breach analysis:

Risk Score: {risk_score}/100
Severity: {prediction.upper()}
Abnormal Return (Day 0): {features.get('abnormal_return_day0', 0):.4f}
CAR (-5, +30): {features.get('car_minus5_plus30', 0):.4f}
Volatility Spike: {features.get('volatility_spike', 1):.2f}x
Recovery Time: {features.get('time_to_recovery', 'N/A')} days

Write a 2-3 sentence executive summary suitable for an investor briefing."""

    return chat_completion(
        prompt=prompt,
        config=config,
        system_prompt=SYSTEM_PROMPT_RISK_ANALYST,
        max_tokens=300,
    )


def enrich_breach_records(
    records: list[dict],
    config: LLMConfig = None,
) -> Optional[list[dict]]:
    """Use LLM to enrich raw breach records with additional context.

    Args:
        records: List of breach record dicts
        config: LLM configuration

    Returns:
        Enriched records with additional fields, or None if failed
    """
    records_json = json.dumps(records[:10], indent=2)  # Limit to 10 for context window

    prompt = f"""Enrich these cybersecurity breach records with additional context:

{records_json}

For each record, add:
1. "estimated_severity": low/medium/high/critical based on records_affected
2. "financial_impact_category": "stock_drop", "recovery", "litigation", "regulatory"
3. "key_risk_factors": list of 2-3 key risk factors

Return as a JSON array with the original fields plus the new ones."""

    response = chat_completion(
        prompt=prompt,
        config=config,
        system_prompt=SYSTEM_PROMPT_BREACH_ENRICHER,
        max_tokens=2000,
    )

    if response:
        try:
            # Try to extract JSON from response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM enrichment response as JSON")

    return None


def answer_breach_question(
    question: str,
    context: str = "",
    config: LLMConfig = None,
) -> Optional[str]:
    """Answer a question about breach data using the LLM.

    Args:
        question: User's question
        context: Additional context (dataset summary, analysis results, etc.)
        config: LLM configuration

    Returns:
        Answer string, or None if LLM unavailable
    """
    prompt = f"""Answer this question about cybersecurity breach financial impact:

Question: {question}

{f'Context: {context}' if context else ''}

Provide a clear, concise answer based on the data and analysis methodology.
If you don't have enough information, say so."""

    return chat_completion(
        prompt=prompt,
        config=config,
        system_prompt=SYSTEM_PROMPT_RISK_ANALYST,
        max_tokens=1000,
    )
