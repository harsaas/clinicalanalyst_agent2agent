import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv
from python_a2a import A2AClient, Message, MessageRole
from python_a2a.models.content import TextContent
load_dotenv()  # loads variables from a local .env file if present

# Allow running as a script: `python app/agents/clinical_agent_main/clinical_agent.py`
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

class HealthState(TypedDict):
    user_input: dict
    bmi_metrics: dict
    nutrition_plan: str
    fitness_plan: str
    final_report: str


NUTRITION_AGENT_URL = os.getenv("NUTRITION_AGENT_URL", "http://localhost:5002/a2a")
FITNESS_AGENT_URL = os.getenv("FITNESS_AGENT_URL", "http://localhost:5001/a2a")


async def _send_a2a_json(endpoint_url: str, payload: dict[str, Any]) -> str:
    """Send a TextContent message containing JSON and return text response."""

    def _call() -> Message:
        client = A2AClient(endpoint_url=endpoint_url, timeout=60)
        msg = Message(
            content=TextContent(text=json.dumps(payload)),
            role=MessageRole.USER,
        )
        return client.send_message(msg)

    response = await asyncio.to_thread(_call)

    if isinstance(response.content, TextContent):
        return (response.content.text or "").strip()
    # Fallback: stringified content
    try:
        return json.dumps(response.content.to_dict())
    except Exception:
        return str(response.content)
# 1. Node: Calculate BMI Metrics via MCP
async def calculate_metrics_node_async(state: HealthState) -> HealthState:
    """Populate BMI metrics by calling the BMI MCP server."""

    user_input = state.get("user_input") or {}
    weight_kg = user_input.get("weight_kg", user_input.get("weight"))
    height_cm = user_input.get("height_cm", user_input.get("height"))

    if weight_kg is None or height_cm is None:
        raise ValueError("user_input must include weight_kg and height_cm")

    from app.agents.clinical_agent_main.mcp_clients.bmi_client import calculate_bmi_via_mcp

    bmi_result = await calculate_bmi_via_mcp(weight_kg=float(weight_kg), height_cm=float(height_cm))
    return {
        **state,
        "bmi_metrics": {
            "bmi": bmi_result.get("bmi"),
            "bmi_category": bmi_result.get("category"),
            "units": bmi_result.get("units", "metric"),
        },
    }

# 2. Node: Call Nutrition Agent (A2A)
async def nutrition_delegate_node(state: HealthState):
    user_input = state.get("user_input") or {}
    query = user_input.get("query") or user_input.get("food") or "healthy recipe"

    payload: dict[str, Any] = {
        "query": query,
        "bmi": (state.get("bmi_metrics") or {}).get("bmi"),
        "bmi_category": (state.get("bmi_metrics") or {}).get("bmi_category"),
    }

    text = await _send_a2a_json(NUTRITION_AGENT_URL, payload)
    return {"nutrition_plan": text}

# 3. Node: Call Fitness Agent (A2A)
async def fitness_delegate_node(state: HealthState):
    bmi_category = (state.get("bmi_metrics") or {}).get("bmi_category")
    payload = {"bmi_category": bmi_category or "Unknown"}

    text = await _send_a2a_json(FITNESS_AGENT_URL, payload)
    return {"fitness_plan": text}


def final_report_node(state: HealthState) -> dict[str, str]:
    bmi = (state.get("bmi_metrics") or {}).get("bmi")
    bmi_category = (state.get("bmi_metrics") or {}).get("bmi_category")
    nutrition = state.get("nutrition_plan", "")
    fitness = state.get("fitness_plan", "")

    report = (
        f"BMI: {bmi} ({bmi_category})\n\n"
        f"Nutrition:\n{nutrition}\n\n"
        f"Fitness:\n{fitness}\n"
    )
    return {"final_report": report}

def build_workflow():
    graph = StateGraph(HealthState)
    graph.add_node("bmi", calculate_metrics_node_async)
    graph.add_node("nutrition", nutrition_delegate_node)
    graph.add_node("fitness", fitness_delegate_node)
    graph.add_node("final", final_report_node)

    graph.add_edge(START, "bmi")
    graph.add_edge("bmi", "nutrition")
    graph.add_edge("nutrition", "fitness")
    graph.add_edge("fitness", "final")
    graph.add_edge("final", END)

    return graph.compile()

# Example Execution
if __name__ == "__main__":
    app = build_workflow()
    initial_state: HealthState = {
        "user_input": {"weight_kg": 85, "height_cm": 175, "query": "chicken and rice"},
        "bmi_metrics": {},
        "nutrition_plan": "",
        "fitness_plan": "",
        "final_report": "",
    }

    out = asyncio.run(app.ainvoke(initial_state))
    print(out.get("final_report", ""))



