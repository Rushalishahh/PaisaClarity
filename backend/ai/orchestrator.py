"""Multi-turn tool execution orchestrator and conversational loop (Phase 9)."""

from dataclasses import dataclass, field
import json
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from models import User
from ai.provider import BaseLLMProvider, get_llm_provider
from ai.tools import FINANCIAL_TOOLS_SCHEMA, execute_tool
from ai.guardrails import check_prompt_safety, attach_disclaimer

logger = logging.getLogger(__name__)

MAX_TOOL_DEPTH = 5

SYSTEM_PROMPT = """You are PaisaClarity Copilot, a trusted, intelligent, and secure personal finance assistant.
Your goal is to help the user understand their finances, track budgets, analyze spending, manage savings goals,
review recurring bills and subscriptions, monitor financial alerts, and forecast future cash flow.

Rules and Security Guidelines:
1. You have strictly READ-ONLY access to the authenticated user's financial data via provided tools.
2. You CANNOT create, update, delete, or modify any transactions, accounts, budgets, or goals.
3. Always use the provided tools to fetch real data before answering specific financial questions. Never invent or hallucinate financial numbers.
4. Format all monetary amounts clearly in Indian Rupees (₹) with appropriate commas (e.g. ₹12,500.00).
5. Be concise, objective, encouraging, and clear. Avoid overly dense financial jargon.
6. If the user asks about something outside their financial data or safe financial projections, politely explain your focus as a personal finance copilot.
"""


@dataclass
class ToolExecutionRecord:
    tool_name: str
    arguments: Dict[str, Any]
    result: Dict[str, Any]


@dataclass
class OrchestrationResult:
    content: str
    tool_executions: List[Dict[str, Any]] = field(default_factory=list)
    is_safe: bool = True
    error: Optional[str] = None


def run_copilot_turn(
    user_prompt: str,
    db: Session,
    user: User,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    provider: Optional[BaseLLMProvider] = None,
) -> OrchestrationResult:
    """Execute a complete conversational turn, coordinating safety, tool calls, and LLM synthesis."""
    # 1. Guardrail Safety Check
    is_safe, warning = check_prompt_safety(user_prompt)
    if not is_safe:
        return OrchestrationResult(
            content=attach_disclaimer(warning or "Request rejected for safety reasons."),
            is_safe=False,
            error=warning,
        )

    llm = provider or get_llm_provider()
    messages: List[Dict[str, Any]] = []

    # 2. Append prior conversation history if provided
    if conversation_history:
        for m in conversation_history:
            messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

    # 3. Append current user prompt
    messages.append({"role": "user", "content": user_prompt})

    tool_executions_log: List[Dict[str, Any]] = []
    depth = 0

    while depth < MAX_TOOL_DEPTH:
        depth += 1
        try:
            res = llm.generate_chat_turn(
                messages=messages,
                tools_schema=FINANCIAL_TOOLS_SCHEMA,
                system_prompt=SYSTEM_PROMPT,
            )
        except Exception as exc:
            logger.error(f"LLM generation failed: {exc}")
            return OrchestrationResult(
                content=attach_disclaimer(
                    "I encountered an error communicating with the AI service. Please try again shortly."
                ),
                is_safe=True,
                error=str(exc),
            )

        # If LLM returned text without tool calls, we are done
        if not res.tool_calls:
            final_content = res.content or "I have processed your request."
            return OrchestrationResult(
                content=attach_disclaimer(final_content),
                tool_executions=tool_executions_log,
                is_safe=True,
            )

        # Execute requested tools
        for tc in res.tool_calls:
            tool_res = execute_tool(
                name=tc.name,
                args=tc.arguments,
                db=db,
                user=user,
            )
            tool_executions_log.append({
                "tool_name": tc.name,
                "arguments": tc.arguments,
                "result": tool_res,
            })

            # Append assistant's tool call and the execution result back into message thread
            messages.append({
                "role": "assistant",
                "content": f"[Called tool {tc.name} with {json.dumps(tc.arguments)}]",
            })
            messages.append({
                "role": "tool",
                "name": tc.name,
                "content": json.dumps(tool_res),
            })

    # If depth exceeded without natural response
    return OrchestrationResult(
        content=attach_disclaimer(
            "I gathered the necessary data but reached the conversation depth limit before finishing the response."
        ),
        tool_executions=tool_executions_log,
        is_safe=True,
    )

