"""LLM Provider abstraction for PaisaClarity AI Copilot (Phase 9).

Supports Gemini REST API, OpenAI-compatible APIs, and a deterministic
offline MockLLMProvider for unit testing and CI environments.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import os
import re
from typing import Any, Dict, List, Optional
import httpx


@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class AIProviderResponse:
    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    raw_response: Optional[Dict[str, Any]] = None


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    def generate_chat_turn(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        system_prompt: str,
    ) -> AIProviderResponse:
        """Process messages and return either assistant text or tool calls."""
        pass


class MockLLMProvider(BaseLLMProvider):
    """Deterministic, offline LLM provider for reliable testing and evaluation without API keys."""

    def generate_chat_turn(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        system_prompt: str,
    ) -> AIProviderResponse:
        if not messages:
            return AIProviderResponse(content="Hello! How can I assist you with your finances today?")

        last_msg = messages[-1]
        role = last_msg.get("role")

        # 1. If previous turn was a tool execution result, synthesize a summary
        if role == "tool":
            tool_name = last_msg.get("name", "")
            raw_content = last_msg.get("content", "{}")
            try:
                data = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
            except Exception:
                data = {"raw": raw_content}

            return self._synthesize_tool_response(tool_name, data)

        # 2. If user message, inspect intent and decide which tool to call
        if role == "user":
            prompt = str(last_msg.get("content", "")).lower()

            # Rule-based intent mapping for deterministic test coverage
            if "reach" in prompt or "projection" in prompt or ("calculat" in prompt and "sav" in prompt) or "how long will it take" in prompt or "how long to save" in prompt:
                # Extract numbers if present
                numbers = [float(s) for s in re.findall(r"\b\d+(?:\.\d+)?\b", prompt)]
                if len(numbers) >= 2:
                    g_amt = max(numbers[0], numbers[1])
                    m_amt = min(numbers[0], numbers[1])
                elif len(numbers) == 1:
                    g_amt = numbers[0]
                    m_amt = 5000.0
                else:
                    g_amt = 50000.0
                    m_amt = 5000.0
                return AIProviderResponse(
                    tool_calls=[
                        ToolCall(
                            call_id="call_projection",
                            name="calculate_savings_projection",
                            arguments={"goal_amount": g_amt, "monthly_contribution": m_amt},
                        )
                    ]
                )

            if "account" in prompt or "balance" in prompt or "liquid" in prompt:
                return AIProviderResponse(
                    tool_calls=[ToolCall(call_id="call_accounts", name="get_account_summary", arguments={})]
                )

            if "compare" in prompt or "vs" in prompt:
                return AIProviderResponse(
                    tool_calls=[
                        ToolCall(
                            call_id="call_compare",
                            name="compare_spending_periods",
                            arguments={
                                "period1_start": "2026-09-01",
                                "period1_end": "2026-09-30",
                                "period2_start": "2026-10-01",
                                "period2_end": "2026-10-31",
                            },
                        )
                    ]
                )

            if "category" in prompt or "breakdown" in prompt or "where did my money go" in prompt:
                return AIProviderResponse(
                    tool_calls=[ToolCall(call_id="call_categories", name="get_category_breakdown", arguments={})]
                )

            if "cashflow" in prompt or "cash flow" in prompt or "trend" in prompt or "history" in prompt:
                return AIProviderResponse(
                    tool_calls=[ToolCall(call_id="call_cashflow", name="get_monthly_cashflow", arguments={"months": 6})]
                )

            if "budget" in prompt:
                return AIProviderResponse(
                    tool_calls=[ToolCall(call_id="call_budget", name="get_budget_status", arguments={})]
                )

            if "goal" in prompt or "savings goal" in prompt:
                return AIProviderResponse(
                    tool_calls=[ToolCall(call_id="call_goals", name="get_savings_goals", arguments={})]
                )

            if "recurring" in prompt or "subscription" in prompt or "bill" in prompt:
                return AIProviderResponse(
                    tool_calls=[ToolCall(call_id="call_recurring", name="get_recurring_payments", arguments={})]
                )

            if "alert" in prompt or "warning" in prompt:
                return AIProviderResponse(
                    tool_calls=[ToolCall(call_id="call_alerts", name="get_financial_alerts", arguments={})]
                )

            if "invest" in prompt or "portfolio" in prompt or "mutual fund" in prompt or "stock" in prompt:
                return AIProviderResponse(
                    tool_calls=[ToolCall(call_id="call_invest", name="get_investment_summary", arguments={})]
                )

            if "forecast" in prompt or "predict" in prompt or "estimate" in prompt or "project" in prompt or "end of this month" in prompt or "end of month" in prompt or "month end" in prompt:
                return AIProviderResponse(
                    tool_calls=[ToolCall(call_id="call_forecast", name="get_spending_forecast", arguments={})]
                )

            if "spend" in prompt or "expense" in prompt or "income" in prompt or "saving" in prompt or "savings rate" in prompt:
                return AIProviderResponse(
                    tool_calls=[ToolCall(call_id="call_spending", name="get_spending_summary", arguments={})]
                )

            # Default conversational response
            return AIProviderResponse(
                content="I am your PaisaClarity Financial Copilot. I can help analyze your spending, check budgets, track savings goals, forecast end-of-month expenses, and review recurring bills. How can I help you today?"
            )

        return AIProviderResponse(content="I am here to help with your financial questions.")

    def _synthesize_tool_response(self, tool_name: str, data: Dict[str, Any]) -> AIProviderResponse:
        """Deterministic summary generator for tool outputs."""
        if "error" in data:
            return AIProviderResponse(content=f"I encountered an error querying your records: {data['error']}")

        if tool_name == "get_spending_summary":
            inc = data.get("total_income", 0.0)
            exp = data.get("total_expenses", 0.0)
            net = data.get("net_cash_flow", 0.0)
            rate = data.get("savings_rate_pct", 0.0)
            return AIProviderResponse(
                content=f"Your recorded total income is ₹{inc:,.2f} and total expenses are ₹{exp:,.2f}. Your net savings are ₹{net:,.2f} with a savings rate of {rate}%."
            )

        if tool_name == "get_category_breakdown":
            breakdown = data.get("breakdown", [])
            tot = data.get("total_expense", 0.0)
            if not breakdown:
                return AIProviderResponse(content="You have no recorded categorized expenses for this period.")
            top_cats = ", ".join([f"{c['category']}: ₹{c['amount']:,.2f} ({c['percentage']}%)" for c in breakdown[:3]])
            return AIProviderResponse(
                content=f"Your total spending is ₹{tot:,.2f}. Top categories include {top_cats}."
            )

        if tool_name == "get_budget_status":
            if not data.get("has_budget"):
                return AIProviderResponse(content="You do not have an active budget configured for this month.")
            limit = data.get("total_budget_limit", 0.0)
            spent = data.get("total_actual_spent", 0.0)
            pct = data.get("total_utilization_pct", 0.0)
            status_txt = "over budget" if data.get("is_over_budget") else "within budget"
            return AIProviderResponse(
                content=f"For {data.get('year')}-{data.get('month'):02d}, your budget limit is ₹{limit:,.2f} and you have spent ₹{spent:,.2f} ({pct}% utilized). You are currently {status_txt}."
            )

        if tool_name == "get_savings_goals":
            goals = data.get("goals", [])
            if not goals:
                return AIProviderResponse(content="You do not currently have any active savings goals.")
            lines = [f"{g['name']}: ₹{g['current_saved']:,.2f} / ₹{g['target_amount']:,.2f} ({g['progress_percentage']}%)" for g in goals]
            return AIProviderResponse(
                content=f"You have {len(goals)} active savings goal(s):\n- " + "\n- ".join(lines)
            )

        if tool_name == "get_account_summary":
            accs = data.get("accounts", [])
            tot = data.get("total_liquid_verified_balance", 0.0)
            return AIProviderResponse(
                content=f"You have {len(accs)} account(s) with a total verified liquid balance of ₹{tot:,.2f}."
            )

        if tool_name == "get_recurring_payments":
            items = data.get("recurring_payments", [])
            monthly = data.get("total_monthly_commitment", 0.0)
            return AIProviderResponse(
                content=f"You have {len(items)} active recurring payment(s) totaling ₹{monthly:,.2f} in estimated monthly commitments."
            )

        if tool_name == "get_financial_alerts":
            alerts = data.get("alerts", [])
            if not alerts:
                return AIProviderResponse(content="You have no active unread financial alerts. Everything looks healthy!")
            lines = [f"[{a['severity'].upper()}] {a['title']}: {a['message']}" for a in alerts[:3]]
            return AIProviderResponse(
                content=f"You have {len(alerts)} active alert(s):\n- " + "\n- ".join(lines)
            )

        if tool_name == "get_investment_summary":
            tot = data.get("total_invested", 0.0)
            mkt = data.get("market_investments_total", 0.0)
            pol = data.get("policy_investments_total", 0.0)
            return AIProviderResponse(
                content=f"Your investment portfolio total is ₹{tot:,.2f} (Market investments: ₹{mkt:,.2f}, Insurance/Policies: ₹{pol:,.2f})."
            )

        if tool_name == "get_spending_forecast":
            proj = data.get("predicted_total") or data.get("projected_month_end_total", 0.0)
            mtd = data.get("actual_mtd") or data.get("month_to_date_spend", 0.0)
            recurring = data.get("confirmed_recurring") or data.get("upcoming_recurring_bills_total", 0.0)
            discretionary = data.get("projected_discretionary", 0.0)
            period = data.get("forecast_period", "this month")
            unc = data.get("uncertainty_range")
            range_txt = ""
            if unc:
                range_txt = f" (expected range: ₹{unc['lower_bound']:,.2f} - ₹{unc['upper_bound']:,.2f})"
            method = data.get("method_used", "")
            method_txt = f" Projection derived via {method}." if method else ""
            return AIProviderResponse(
                content=(
                    f"Forecast for {period}: Projected month-end total is ₹{proj:,.2f}{range_txt}. "
                    f"This accounts for ₹{mtd:,.2f} spent MTD, ₹{recurring:,.2f} in confirmed recurring commitments, "
                    f"and ₹{discretionary:,.2f} in projected discretionary burn.{method_txt}"
                )
            )

        if tool_name == "calculate_savings_projection":
            months = data.get("months_to_goal")
            date_str = data.get("projected_completion_date")
            g_amt = data.get("goal_amount", 0.0)
            m_amt = data.get("monthly_contribution", 0.0)
            return AIProviderResponse(
                content=f"To reach your goal of ₹{g_amt:,.2f} saving ₹{m_amt:,.2f} per month, it will take approximately {months} month(s) (estimated completion around {date_str})."
            )

        # Fallback tool synthesis
        return AIProviderResponse(content=f"Retrieved data for {tool_name}: {json.dumps(data)}")


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider using direct REST endpoints."""

    def __init__(self, api_key: str, model_name: Optional[str] = None):
        self.api_key = api_key
        self.model_name = model_name or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"

    def generate_chat_turn(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        system_prompt: str,
    ) -> AIProviderResponse:
        contents = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content") or ""
            if role == "tool":
                # Gemini tool response representation
                tool_name = m.get("name", "tool")
                try:
                    res_obj = json.loads(content) if isinstance(content, str) else content
                except Exception:
                    res_obj = {"result": str(content)}
                contents.append({
                    "role": "user",
                    "parts": [{"functionResponse": {"name": tool_name, "response": {"name": tool_name, "content": res_obj}}}],
                })
            elif role == "assistant":
                # Check if it was a tool call message or plain text
                contents.append({"role": "model", "parts": [{"text": str(content)}]})
            else:
                contents.append({"role": "user", "parts": [{"text": str(content)}]})

        # Format Gemini tool declarations
        function_declarations = []
        for t in tools_schema:
            function_declarations.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object"}),
            })

        payload: Dict[str, Any] = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "tools": [{"functionDeclarations": function_declarations}] if function_declarations else [],
        }

        # Securely pass API key via header rather than exposing in URL query params
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        # Safe request with retry on transient network errors
        attempts = 2
        last_exc = None
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(
                        self.base_url,
                        json=payload,
                        headers=headers,
                    )
                    resp.raise_for_status()
                    res_json = resp.json()
                    break
            except Exception as exc:
                last_exc = exc
                if attempt == attempts - 1:
                    raise RuntimeError(f"Gemini API request failed after {attempts} attempts: {str(exc)}") from exc

        candidates = res_json.get("candidates", [])
        if not candidates:
            return AIProviderResponse(content="No response generated by model.")

        first_cand = candidates[0].get("content", {})
        parts = first_cand.get("parts", [])
        text_parts = []
        tool_calls = []

        for p in parts:
            if "text" in p:
                text_parts.append(p["text"])
            if "functionCall" in p:
                fc = p["functionCall"]
                tool_calls.append(
                    ToolCall(
                        call_id=f"call_{fc.get('name')}",
                        name=fc.get("name"),
                        arguments=fc.get("args", {}),
                    )
                )

        return AIProviderResponse(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            raw_response=res_json,
        )


class OpenAICompatibleProvider(BaseLLMProvider):
    """OpenAI-compatible Chat Completions provider."""

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def generate_chat_turn(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        system_prompt: str,
    ) -> AIProviderResponse:
        openai_tools = [{"type": "function", "function": t} for t in tools_schema]
        formatted_msgs = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = m.get("role", "user")
            if role == "tool":
                formatted_msgs.append({
                    "role": "tool",
                    "tool_call_id": m.get("tool_call_id") or f"call_{m.get('name', 'tool')}",
                    "content": str(m.get("content", "")),
                })
            else:
                formatted_msgs.append({
                    "role": role,
                    "content": str(m.get("content", "")),
                })

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted_msgs,
        }
        if openai_tools:
            payload["tools"] = openai_tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        attempts = 2
        last_exc = None
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    resp.raise_for_status()
                    res_json = resp.json()
                    break
            except Exception as exc:
                last_exc = exc
                if attempt == attempts - 1:
                    raise RuntimeError(f"OpenAI API request failed after {attempts} attempts: {str(exc)}") from exc

        choice = res_json.get("choices", [{}])[0].get("message", {})
        content = choice.get("content")
        tool_calls_raw = choice.get("tool_calls", [])

        tool_calls = []
        for tc in tool_calls_raw:
            fn = tc.get("function", {})
            args_str = fn.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except Exception:
                args = {}
            tool_calls.append(
                ToolCall(
                    call_id=tc.get("id", "call_openai"),
                    name=fn.get("name", ""),
                    arguments=args,
                )
            )

        return AIProviderResponse(
            content=content,
            tool_calls=tool_calls,
            raw_response=res_json,
        )


def get_llm_provider() -> BaseLLMProvider:
    """Factory to retrieve the appropriate LLM provider based on environment configuration.
    
    Security rule: Production environments CANNOT silently fall back to MockLLMProvider.
    """
    env = os.environ.get("ENVIRONMENT", "").lower()
    mock_flag = os.environ.get("MOCK_AI", "").lower()

    # In test environment or when explicitly requested via MOCK_AI=true
    if env == "test" or mock_flag in ("1", "true", "yes"):
        return MockLLMProvider()

    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        return GeminiProvider(api_key=gemini_key)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        return OpenAICompatibleProvider(api_key=openai_key)

    # In production, do not silently fake responses if keys are missing
    if env in ("production", "prod") or os.environ.get("RENDER"):
        raise RuntimeError(
            "AI Copilot configuration error: In production, GEMINI_API_KEY or OPENAI_API_KEY must be configured. "
            "Silent fallback to MockLLMProvider is disallowed."
        )

    # In local development without configured keys, provide Mock with warning
    return MockLLMProvider()
