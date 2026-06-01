# Testing Guide

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=breachalpha --cov-report=term-missing

# Run specific test file
pytest tests/test_feature_engine.py -v

# Run specific test
pytest tests/test_model.py::TestTrainModel::test_basic_training -v
```

## Test Structure

```
tests/
├── __init__.py
├── test_breach_loader.py    # 8 tests — CSV parsing, filtering, dedup
├── test_ticker_resolver.py  # 10 tests — name → ticker mapping
├── test_feature_engine.py   # 22 tests — returns, AR, CAR, volatility, recovery
└── test_model.py            # 10 tests — training, prediction, persistence
```

## Test Categories

### Unit Tests (Pure Functions)
- `compute_daily_returns` — price → return conversion
- `compute_abnormal_returns` — stock vs market returns
- `compute_car` — cumulative abnormal returns
- `compute_volatility_ratio` — pre/post volatility
- `compute_volume_change` — pre/post volume
- `compute_recovery_time` — days to price recovery
- `classify_severity` — CAR → severity label
- `resolve_ticker` — company name → ticker symbol

### Integration Tests (Multi-Module)
- `compute_features` — full feature pipeline (stock data → features)
- `train_model` — features → trained model
- `predict_severity` — features → risk score

### Data Tests
- `load_breaches` — CSV loading, validation, filtering
- `get_breach_summary` — aggregate statistics

## Test Data

Tests use **synthetic data** — no network calls required. This means:
- Tests run fast (~5 seconds total)
- Tests are deterministic (seeded random)
- Tests work offline
- No yfinance API calls during testing

## Writing New Tests

### Convention
- Test files: `test_<module>.py`
- Test classes: `Test<Feature>`
- Test methods: `test_<behavior>`
- Use `pytest.raises` for exception testing
- Use `tmp_path` fixture for file system tests

### Example
```python
class TestMyFeature:
    def test_basic_case(self):
        result = my_function(input)
        assert result == expected

    def test_edge_case(self):
        result = my_function(empty_input)
        assert result is None

    def test_raises_on_bad_input(self):
        with pytest.raises(ValueError, match="specific message"):
            my_function(bad_input)
```

## Coverage Target

Minimum 60% coverage (configured in `pyproject.toml`). Current coverage:

| Module | Coverage |
|---|---|
| breach_loader | ~90% |
| ticker_resolver | ~95% |
| feature_engine | ~85% |
| model | ~80% |
| stock_loader | ~70% (network-dependent) |
| cli | ~50% (integration, tested manually) |
