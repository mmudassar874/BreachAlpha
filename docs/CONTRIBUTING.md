# Contributing Guide

## Development Setup

```bash
# Clone the repo
git clone <repo-url>
cd breachalpha

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest
```

## Code Style

- Python 3.10+ features (type hints, `match`, walrus operator)
- Type hints on all public functions
- Docstrings for all public functions (Google style)
- No comments unless the *why* is non-obvious
- Keep functions under 30 lines
- Keep modules under 300 lines

## Project Layout

```
breachalpha/
├── __init__.py           # Package version
├── __main__.py           # python -m breachalpha entry point
├── breach_loader.py      # Data ingestion (CSV → DataFrame)
├── ticker_resolver.py    # Name resolution (company → ticker)
├── stock_loader.py       # Market data (yfinance + cache)
├── feature_engine.py     # Feature engineering (event study)
├── model.py              # ML model (XGBoost)
└── cli.py                # CLI interface (thin wrapper)
```

### Separation Rules
- `breach_loader` and `stock_loader` handle data I/O only
- `feature_engine` is pure computation (no I/O)
- `model` handles ML only (no data fetching)
- `cli` is a thin wrapper (no business logic)

## Adding a Feature

1. Write tests first (`tests/test_<module>.py`)
2. Implement the feature
3. Ensure all tests pass: `pytest`
4. Check coverage: `pytest --cov=breachalpha`
5. Update this document if adding new modules

## Adding a New Breach Type

1. Add the breach type string to `classify_severity` thresholds in `feature_engine.py`
2. Add the type to `OVERRIDES` or `KNOWN_TICKERS` in `ticker_resolver.py` if needed
3. Add tests for the new type

## Commit Messages

Use conventional commits:
- `feat:` new feature
- `fix:` bug fix
- `test:` add/modify tests
- `docs:` documentation only
- `refactor:` code restructuring
- `chore:` build/CI/tooling

## Release Process

1. Update version in `pyproject.toml` and `__init__.py`
2. Update `CHANGELOG.md`
3. Tag the release: `git tag v0.1.0`
4. Push: `git push origin main --tags`
