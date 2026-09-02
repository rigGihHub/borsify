from ai_cost import estimate_usage_cost, format_cost_usd


def test_luna_cost_uses_current_standard_rates():
    cost = estimate_usage_cost("gpt-5.6-luna", 1_000_000, 1_000_000)
    assert abs(cost.cost_usd - 1.40) < 1e-12


def test_typical_small_request_cost_is_tiny():
    cost = estimate_usage_cost("gpt-5.6-luna", 2500, 500)
    assert abs(cost.cost_usd - 0.0011) < 1e-12


def test_unknown_model_does_not_invent_price():
    cost = estimate_usage_cost("custom-unknown", 1000, 1000)
    assert cost.cost_usd == 0.0


def test_cost_formatter_preserves_small_values():
    assert format_cost_usd(0.0011) == "$0.0011"
