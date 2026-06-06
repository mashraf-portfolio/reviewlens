"""Unit tests for CostMeter — no real API calls needed."""

import pytest

# Patch the price table so tests are insulated from upstream pricing changes
MOCK_PRICES = {
    "mock-model": {"input": 10.0, "output": 30.0},  # $10/$30 per million tokens
    "__default__": {"input": 10.0, "output": 30.0},
}


@pytest.fixture(autouse=True)
def patch_prices(monkeypatch):
    import llm.client as client_module

    monkeypatch.setattr(client_module, "_COST_PER_M", MOCK_PRICES)


from llm.client import BudgetExceeded, CostMeter  # noqa: E402


def test_cost_accumulates():
    meter = CostMeter(ceiling_usd=1.0)
    # 100k input + 10k output with mock-model
    # cost = (100_000 * 10 + 10_000 * 30) / 1_000_000 = (1_000_000 + 300_000) / 1_000_000 = 1.3
    # but ceiling is 1.0 so this should raise — let's use a smaller call first
    meter.record("mock-model", input_tokens=10_000, output_tokens=1_000)
    # cost = (10_000*10 + 1_000*30) / 1_000_000 = 0.13  — under ceiling
    assert meter.total_usd == pytest.approx(0.13)


def test_budget_exceeded_raises():
    meter = CostMeter(ceiling_usd=0.10)
    with pytest.raises(BudgetExceeded) as exc_info:
        # cost = (10_000*10 + 1_000*30) / 1_000_000 = 0.13 > 0.10
        meter.record("mock-model", input_tokens=10_000, output_tokens=1_000)
    assert exc_info.value.spent > exc_info.value.ceiling


def test_budget_exceeded_message_contains_amounts():
    meter = CostMeter(ceiling_usd=0.05)
    with pytest.raises(BudgetExceeded) as exc_info:
        meter.record("mock-model", input_tokens=5_000, output_tokens=500)
    msg = str(exc_info.value)
    assert "spent" in msg
    assert "ceiling" in msg


def test_budget_not_exceeded_when_exactly_at_ceiling():
    meter = CostMeter(ceiling_usd=0.13)
    # cost = exactly 0.13 — should NOT raise (strict greater-than check)
    meter.record("mock-model", input_tokens=10_000, output_tokens=1_000)
    assert meter.total_usd == pytest.approx(0.13)


def test_cumulative_spend_across_calls():
    meter = CostMeter(ceiling_usd=1.0)
    meter.record("mock-model", input_tokens=10_000, output_tokens=1_000)  # 0.13
    meter.record("mock-model", input_tokens=10_000, output_tokens=1_000)  # 0.26
    assert meter.total_usd == pytest.approx(0.26)


def test_reset_clears_spend():
    meter = CostMeter(ceiling_usd=1.0)
    meter.record("mock-model", input_tokens=10_000, output_tokens=1_000)
    meter.reset()
    assert meter.total_usd == 0.0


def test_budget_exceeded_after_reset_and_reuse():
    meter = CostMeter(ceiling_usd=0.10)
    meter.reset()
    with pytest.raises(BudgetExceeded):
        meter.record("mock-model", input_tokens=10_000, output_tokens=1_000)
