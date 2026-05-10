from __future__ import annotations

import json
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel, ValidationError

try:
    from .nutrition_tool import get_nutritional_data
except ImportError:  # Allows running as a script: `python main.py`
    from nutrition_tool import get_nutritional_data

import os

from dotenv import load_dotenv
from openai import OpenAI

from python_a2a import Message, MessageRole
from python_a2a.models.content import TextContent

app = FastAPI()

load_dotenv()

_openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")

_openai_client = OpenAI()

class A2AMessage(BaseModel):
    query: str
    # Populated by the Clinical Agent (which can fetch BMI via the BMI MCP server)
    bmi: float | None = None
    bmi_category: str | None = None


def _format_fallback_two_recipes(*, query: str, bmi_context: str) -> str:
    q = query.strip() or "healthy recipe"
    return (
        f"BMI context: {bmi_context}\n\n"
        "Recipe 1: High-Fiber Bean & Veggie Rice Bowl\n"
        "Ingredients:\n"
        "- 3/4 cup cooked beans (black/kidney)\n"
        "- 1/2 cup cooked rice\n"
        "- 1 cup mixed vegetables (pepper, onion, spinach)\n"
        "- 1 tsp olive oil\n"
        "- Spices: cumin, chili, salt, pepper\n\n"
        "Steps (10):\n"
        "1) Rinse and drain beans (if canned).\n"
        "2) Chop vegetables into small pieces.\n"
        "3) Heat oil in a pan on medium heat.\n"
        "4) Saute onion/pepper for 3–4 minutes.\n"
        "5) Add remaining vegetables; cook 3–5 minutes.\n"
        "6) Add beans; stir 1 minute.\n"
        "7) Add rice; stir until warmed through.\n"
        "8) Season with cumin/chili/salt/pepper.\n"
        "9) Taste and adjust seasoning; add a squeeze of lemon/lime if you have it.\n"
        "10) Serve in a bowl; add a side salad if available.\n\n"
        "Recipe 2: Protein-Forward Chicken & Veggie Stir-Fry with Rice\n"
        "Ingredients:\n"
        "- 120–150g chicken breast (or tofu)\n"
        "- 1/2 cup cooked rice\n"
        "- 1–2 cups mixed vegetables (broccoli, carrots, peppers)\n"
        "- 1 tsp olive oil\n"
        "- 1–2 tbsp low-sodium soy sauce (or salt + pepper)\n\n"
        "Steps (10):\n"
        "1) Slice chicken (or tofu) into thin strips.\n"
        "2) Chop vegetables into bite-size pieces.\n"
        "3) Heat oil in a pan on medium-high heat.\n"
        "4) Cook chicken 4–6 minutes (until fully cooked).\n"
        "5) Remove chicken to a plate (optional, keeps veggies crisp).\n"
        "6) Add vegetables; stir-fry 3–5 minutes.\n"
        "7) Add soy sauce (or seasoning) and 2–3 tbsp water; stir.\n"
        "8) Return chicken to the pan; mix 1 minute.\n"
        "9) Add cooked rice (or serve stir-fry over rice).\n"
        "10) Serve hot; keep portion of rice moderate for weight management.\n\n"
        f"Query used: {q}"
    )


def _parse_a2a_text_json(payload: dict) -> tuple[Message, A2AMessage]:
    """Parse an A2A SDK Message payload whose TextContent.text is JSON."""

    try:
        message = Message.from_dict(payload)
        if not isinstance(message.content, TextContent):
            raise ValueError("Only TextContent messages are supported")

        text = (message.content.text or "").strip()
        if not text:
            raise ValueError("TextContent.text must be non-empty")

        data = json.loads(text)
        request = A2AMessage(**data)
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
            "name": "Nutrition Recipe Agent",
            "description": "Generates BMI-aware recipe suggestions.",
            "version": "unknown",
        }

@app.post("/a2a")
async def handle_nutrition_task(payload: dict = Body(...)):
    """A2A endpoint (python-a2a SDK compatible only)."""

    message, request = _parse_a2a_text_json(payload)

    # 1. Fetch real-world data
    raw_data = get_nutritional_data(request.query)

    # 2. Let the LLM process the data (e.g., provide a clinical recipe)
    bmi_context = (
        f"BMI {request.bmi} ({request.bmi_category})"
        if request.bmi is not None
        else "BMI not provided"
    )
    prompt = (
        "Create TWO recipe options tailored to the user's query and BMI context. "
        "Return VALID JSON only (no markdown, no extra text).\n\n"
        "Constraints:\n"
        "- EXACTLY 2 recipes\n"
        "- Each recipe must have EXACTLY 10 steps\n"
        "- Steps must be short, actionable, one sentence each\n\n"
        "Practicality constraints:\n"
        "- No soaking, no overnight steps, no 'prep the night before'\n"
        "- Prefer canned beans / pre-cooked grains / quick-cook options\n"
        "- Total cook time should be about 30 minutes or less\n\n"
        "JSON schema:\n"
        "{\n"
        '  "recipes": [\n'
        '    {"name": "...", "ingredients": ["..."], "steps": ["..."]},\n'
        '    {"name": "...", "ingredients": ["..."], "steps": ["..."]}\n'
        "  ]\n"
        "}\n\n"
        f"User query: {request.query}\n"
        f"BMI context: {bmi_context}\n"
        f"USDA data: {raw_data}\n"
    )

    if not os.getenv("OPENAI_API_KEY"):
        recipe_text = _format_fallback_two_recipes(query=request.query, bmi_context=bmi_context)
    else:
        try:
            completion = _openai_client.chat.completions.create(
                model=_openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a nutrition assistant. Output JSON only that matches the given schema.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )

            content = (completion.choices[0].message.content or "").strip()
            data = json.loads(content)
            recipe_text = _format_two_recipes_from_json(bmi_context=bmi_context, data=data)
        except Exception:
            recipe_text = _format_fallback_two_recipes(query=request.query, bmi_context=bmi_context)
    
    # Return the artifact to the Clinical Agent as an A2A Message
    reply = Message(
        content=TextContent(text=recipe_text),
        role=MessageRole.AGENT,
        parent_message_id=message.message_id,
        conversation_id=message.conversation_id,
    )
    return reply.to_dict()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5002)