import asyncio
from typing import Any

import streamlit as st

from app.agents.clinical_agent_main.clinical_agent import build_workflow


@st.cache_resource
def _workflow():
    return build_workflow()


def _run_workflow(*, weight_kg: float, height_cm: float, query: str) -> dict[str, Any]:
    workflow = _workflow()
    initial_state = {
        "user_input": {"weight_kg": weight_kg, "height_cm": height_cm, "query": query},
        "bmi_metrics": {},
        "nutrition_plan": "",
        "fitness_plan": "",
        "final_report": "",
    }
    return asyncio.run(workflow.ainvoke(initial_state))


st.title("Clinical Agent System")

st.caption(
    "Enter weight/height and a food query. This runs the Clinical workflow, which calls: "
    "BMI MCP tool (local stdio) + Nutrition agent (http://localhost:5002/a2a) + "
    "Fitness agent (http://localhost:5001/a2a)."
)

col1, col2 = st.columns(2)
with col1:
    weight_kg = st.number_input("Weight (kg)", min_value=1.0, max_value=500.0, value=85.0, step=0.5)
with col2:
    height_cm = st.number_input("Height (cm)", min_value=50.0, max_value=250.0, value=175.0, step=0.5)

query = st.text_input("Food query", value="chicken and rice")

run = st.button("Run")

if run:
    try:
        with st.spinner("Running agents..."):
            out = _run_workflow(weight_kg=float(weight_kg), height_cm=float(height_cm), query=query.strip() or "healthy recipe")

        st.subheader("Final Report")
        st.text_area("", value=str(out.get("final_report", "")), height=220)

        st.subheader("Structured Output")
        st.json(
            {
                "bmi_metrics": out.get("bmi_metrics"),
                "nutrition_plan": out.get("nutrition_plan"),
                "fitness_plan": out.get("fitness_plan"),
            }
        )
    except Exception as e:
        st.error(f"Run failed: {type(e).__name__}: {e}")
        st.info(
            "Make sure the Nutrition agent is running on :5002 and the Fitness agent on :5001. "
            "Then retry."
        )
