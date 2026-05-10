from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel, ValidationError

from python_a2a import Message, MessageRole
from python_a2a.models.content import TextContent

try:
    from .tavily_tool import fitness_search_tool
except ImportError:  # Allows running as a script: `python main.py`
    from tavily_tool import fitness_search_tool

app = FastAPI()


class A2AFitnessRequest(BaseModel):
    bmi_category: str


def _parse_a2a_text_json(payload: dict) -> tuple[Message, A2AFitnessRequest]:
    """Parse an A2A SDK Message payload whose TextContent.text is JSON."""

    try:
        message = Message.from_dict(payload)
        if not isinstance(message.content, TextContent):
            raise ValueError("Only TextContent messages are supported")

        text = (message.content.text or "").strip()
        if not text:
            raise ValueError("TextContent.text must be non-empty")

        data = json.loads(text)
        request = A2AFitnessRequest(**data)
        return message, request
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e))


def _agent_card_path() -> Path:
    return Path(__file__).resolve().parent / ".well-known" / "agent-card.json"


@app.get("/.well-known/agent.json")
@app.get("/a2a/.well-known/agent.json")
async def agent_card() -> dict:
    try:
        return json.loads(_agent_card_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "name": "Fitness Plan Agent",
            "description": "Suggests fitness plans based on BMI category.",
            "version": "unknown",
        }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def handle_fitness_request(bmi_category: str) -> str:
    user_goal = "lose weight" if bmi_category in ["Overweight", "Obese"] else "maintain a healthy lifestyle"
    query = f"Best safe exercises for a person in the {bmi_category} category looking to {user_goal}"

    if fitness_search_tool is None:
        return (
            "Tavily is not configured (missing TAVILY_API_KEY or tool dependency). "
            f"Fallback suggestion: start with 30–45 minutes/week of low-impact cardio + 2x/week full-body strength. "
            f"(BMI category: {bmi_category})"
        )

    try:
        research = fitness_search_tool.run(query)
    except Exception as e:
        return (
            f"Tavily search failed ({type(e).__name__}). "
            f"Fallback suggestion: start with 30–45 minutes/week of low-impact cardio + 2x/week full-body strength. "
            f"(BMI category: {bmi_category})"
        )
    # TavilySearchResults typically returns a list of dicts; keep it simple.
    if isinstance(research, list) and research:
        top = research[0]
        return top.get("content") or top.get("snippet") or str(top)

    if isinstance(research, dict) and "summary" in research:
        return str(research["summary"])

    return str(research)


@app.post("/a2a")
async def a2a(payload: dict = Body(...)) -> dict:
    """A2A endpoint (python-a2a SDK compatible only)."""

    message, req = _parse_a2a_text_json(payload)

    plan = await handle_fitness_request(req.bmi_category)

    reply = Message(
        content=TextContent(text=plan),
        role=MessageRole.AGENT,
        parent_message_id=message.message_id,
        conversation_id=message.conversation_id,
    )
    return reply.to_dict()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("FITNESS_AGENT_PORT", "5001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
