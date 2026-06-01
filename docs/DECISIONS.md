# Decision Log

Track architectural and design decisions here.

## 2026-05-31: Initial Architecture

**Decision:** Build as single-package Python CLI tool with 5 core modules.

**Rationale:**
- Smallest reliable architecture for MVP
- 6 dependencies, all open-source and free
- Separates data ingestion from analysis from presentation
- Testable at every layer

**Alternatives considered:**
- Monolithic script: Rejected — no separation of concerns
- Multi-service architecture: Rejected — overengineered for MVP
- Jupyter notebook: Rejected — not testable, not deployable

---

## 2026-05-31: Dataset Choice — HIBP via Kaggle

**Decision:** Use "Cyber Breach Analysis Dataset" from Kaggle (HIBP data, MIT license).

**Rationale:**
- Free, MIT licensed, well-structured CSV
- Has breach dates, company names, record counts
- Missing: ticker symbols (solved by ticker_resolver.py)

**Alternatives considered:**
- Privacy Rights Clearinghouse: Rejected — paid dataset
- Self-scraped breach notifications: Rejected — too much maintenance
- Synthetic data: Rejected — not grounded in reality

---

## 2026-05-31: Abnormal Return Model

**Decision:** Use Market-Adjusted Model (AR = R_stock - R_market) instead of full OLS market model.

**Rationale:**
- Simpler to implement and explain
- No estimation window required (simplifies timestamp alignment)
- Used in ~15% of published event studies
- Good enough for MVP; can upgrade to OLS later

**Trade-off:** Less precise than OLS model. Acceptable at this stage.

---

## 2026-05-31: XGBoost over LightGBM

**Decision:** Use XGBoost for the prediction model.

**Rationale:**
- Level-wise tree growth is less prone to overfitting on small datasets
- Better regularization options (gamma, min_child_weight, reg_alpha, reg_lambda)
- 10 years of production use, larger community
- Speed difference negligible at ~5K records

---

## 2026-05-31: CLI-First Interface

**Decision:** Build CLI interface only. No web framework.

**Rationale:**
- No users yet; CLI is sufficient for MVP
- Can add web interface later without changing core logic
- Business logic is transport-agnostic (easy to wrap in API later)

**Future:** When users arrive, add FastAPI wrapper around existing functions.
