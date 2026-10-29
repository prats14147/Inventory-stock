"""Golden routing cases for the Gemini planner and rules fallback.

These cases cover everyday inventory questions, tool/calc distinctions, and
requests which must clarify instead of guessing. The live-LLM's linguistic
quality still needs a separate provider evaluation; these tests verify that
both paths share the same schema, allowlist, and backend route mappings.
"""

import json

import pytest

from app.nlp.intent import Intent
from app.nlp.parser import parse
from app.nlp.request_planner import (
    RequestPlan,
    plan_intent,
    plan_request,
    prefer_explicit_stock_action,
    reject_conflicting_read_plan,
)
from app.nlp.rules import classify_intent
from app.nlp.tool_registry import TOOLS_BY_INTENT, TOOLS_BY_NAME
from app.services.chat_service import _planner_clarification


GOLDEN_CASES = [
    ("How much stock do we have for P0001?", Intent.CURRENT_STOCK, "get_current_stock"),
    ("Which products are low on stock?", Intent.LOW_STOCK, "get_low_stock"),
    ("What did P0002 sell last month?", Intent.SALES_TREND, "get_sales_summary"),
    ("Forecast P0003 for the next 7 days", Intent.DEMAND_FORECAST, "forecast_demand"),
    ("What was the gross profit for P0002?", Intent.FINANCIAL_ANALYSIS, "get_gross_profit"),
    ("How are stores performing?", Intent.STORE_PROFITABILITY, "get_store_profitability"),
    ("Which store sold the most units?", Intent.STORE_ANALYSIS, "get_store_analysis"),
    ("What needs to be reordered?", Intent.REORDER_RECOMMENDATION, "get_reorder_recommendation"),
]


class FakePlanner:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete_json(self, system_prompt, user_message):
        self.calls.append((system_prompt, user_message))
        return json.dumps(self.response)


@pytest.mark.parametrize("question,intent,tool_name", GOLDEN_CASES)
def test_fallback_question_selects_registered_backend_tool(question, intent, tool_name):
    assert classify_intent(question) == intent
    assert TOOLS_BY_INTENT[intent].name == tool_name


@pytest.mark.parametrize("question,intent,tool_name", GOLDEN_CASES)
def test_gemini_plan_and_fallback_share_tool_mapping(question, intent, tool_name):
    fake = FakePlanner({
        "request_type": "read",
        "tool": tool_name,
        "arguments": {},
        "confidence": 0.95,
    })
    plan = plan_request(question, fake)
    assert plan is not None
    assert plan_intent(plan) == intent
    assert TOOLS_BY_NAME[plan.tool].name == TOOLS_BY_INTENT[classify_intent(question)].name


def test_planner_strips_product_id_not_present_in_user_message():
    fake = FakePlanner({
        "request_type": "read", "tool": "get_current_stock",
        "arguments": {"product_id": "P0003"}, "confidence": 0.95,
    })
    plan = plan_request("How much stock do we have?", fake)
    assert plan is not None
    assert plan.arguments.get("product_id") is None


def test_planner_preserves_product_name_reference_for_catalog_resolution():
    fake = FakePlanner({
        "request_type": "read", "tool": "get_current_stock",
        "arguments": {}, "confidence": 0.95,
    })
    plan = plan_request("How much stock for kitchen blender?", fake)
    assert plan is not None
    assert plan.arguments["product_reference"] == "kitchen"


def test_low_confidence_plan_is_preserved_for_clarification():
    fake = FakePlanner({
        "request_type": "unclear", "arguments": {}, "confidence": 0.42,
    })
    plan = plan_request("change that thing", fake)
    assert plan is not None
    assert plan.confidence == 0.42
    assert "asking about stock" in _planner_clarification(plan)


def test_ambiguous_stock_decrease_clarifies_sale_vs_adjustment():
    plan = RequestPlan(
        request_type="decrease", quantity=10,
        arguments={"product_id": "P0001", "store_id": "S001"},
        confidence=0.9,
    )
    assert _planner_clarification(plan) == (
        "Do you mean the units were sold to a customer, or removed for another reason?"
    )


@pytest.mark.parametrize(
    "message,model_guess,expected,reason",
    [
        ("deduct 25 stocks in P0018 at S003", "receive", "decrease", "unknown"),
        ("add 100 units to P0001 at S001", "decrease", "receive", "receipt"),
        ("received 20 units of P0002 at S002", "decrease", "receive", "receipt"),
        ("sold 8 units of P0002 at S002", "receive", "sale", "sale"),
    ],
)
def test_explicit_stock_action_wording_overrides_conflicting_model_guess(
    message, model_guess, expected, reason
):
    plan = RequestPlan(
        request_type=model_guess,
        quantity=25 if "25" in message else 100 if "100" in message else 20 if "20" in message else 8,
        arguments={"product_id": "P0001", "store_id": "S001"},
        confidence=0.9,
    )
    corrected = prefer_explicit_stock_action(message, plan)
    assert corrected is not None
    assert corrected.request_type == expected
    assert corrected.reason == reason


def test_unknown_read_tool_is_rejected():
    fake = FakePlanner({
        "request_type": "read", "tool": "run_sql", "arguments": {}, "confidence": 0.99,
    })
    assert plan_request("How much stock?", fake) is None


def test_conflicting_gemini_read_tool_yields_to_confident_rules_route():
    plan = RequestPlan(
        request_type="read", tool="get_sales_summary", arguments={}, confidence=0.99,
    )
    assert reject_conflicting_read_plan("Which store sold the most units?", plan) is None


def test_low_confidence_llm_fallback_is_not_executable():
    fake = FakePlanner({
        "request_type": "read", "tool": "get_current_stock",
        "arguments": {}, "confidence": 0.3,
    })
    intent, _, method = parse("what's happening there?", fake)
    assert intent == Intent.UNKNOWN
    assert method == "rules"


def test_rules_parser_is_stable_when_model_is_unavailable():
    class OfflinePlanner:
        def complete_json(self, *_):
            raise TimeoutError("offline")

    intent, entities, method = parse("How much stock for P0001?", OfflinePlanner())
    assert (intent, entities.product_id, method) == (Intent.CURRENT_STOCK, "P0001", "rules")
