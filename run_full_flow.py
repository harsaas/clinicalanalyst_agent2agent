from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class _Proc:
    name: str
    popen: subprocess.Popen[str] | None

    def stop(self) -> None:
        if not self.popen:
            return
        if self.popen.poll() is not None:
            return
        try:
            self.popen.terminate()
        except Exception:
            pass


def _is_up(url: str, timeout_s: float = 1.5) -> bool:
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.get(url)
            return r.status_code == 200
    except Exception:
        return False


def _wait_up(url: str, *, timeout_s: float = 20.0) -> None:
    start = time.monotonic()
    while True:
        if _is_up(url):
            return
        if time.monotonic() - start > timeout_s:
            raise TimeoutError(f"Timed out waiting for {url}")
        time.sleep(0.2)


def _start_server_if_needed(*, name: str, cmd: list[str], health_url: str) -> _Proc:
    if _is_up(health_url):
        return _Proc(name=name, popen=None)

    popen = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=os.environ.copy(),
    )

    try:
        _wait_up(health_url, timeout_s=25.0)
    except Exception:
        # Dump a bit of server output for debugging
        if popen.stdout:
            try:
                out = "".join(popen.stdout.readlines()[-60:])
            except Exception:
                out = ""
            if out:
                print(f"\n--- {name} output ---\n{out}\n--- end ---\n", file=sys.stderr)
        popen.terminate()
        raise

    return _Proc(name=name, popen=popen)


async def _run_clinical(*, weight_kg: float, height_cm: float, query: str) -> dict[str, Any]:
    from app.agents.clinical_agent_main.clinical_agent import build_workflow

    app = build_workflow()
    initial_state = {
        "user_input": {"weight_kg": weight_kg, "height_cm": height_cm, "query": query},
        "bmi_metrics": {},
        "nutrition_plan": "",
        "fitness_plan": "",
        "final_report": "",
    }
    return await app.ainvoke(initial_state)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full Clinical agent flow from the CLI.")
    parser.add_argument("--weight-kg", type=float, required=True)
    parser.add_argument("--height-cm", type=float, required=True)
    parser.add_argument("--query", type=str, default="healthy recipe")
    parser.add_argument("--nutrition-url", type=str, default=os.getenv("NUTRITION_AGENT_URL", "http://localhost:5002/a2a"))
    parser.add_argument("--fitness-url", type=str, default=os.getenv("FITNESS_AGENT_URL", "http://localhost:5001/a2a"))
    parser.add_argument(
        "--no-servers",
        action="store_true",
        help="Do not start Nutrition/Fitness servers; assume they are already running.",
    )

    args = parser.parse_args()

    nutrition_health = args.nutrition_url.rstrip("/") + "/.well-known/agent.json"
    fitness_health = args.fitness_url.rstrip("/") + "/.well-known/agent.json"

    nutrition_proc = _Proc("nutrition", None)
    fitness_proc = _Proc("fitness", None)

    try:
        if not args.no_servers:
            nutrition_proc = _start_server_if_needed(
                name="Nutrition",
                cmd=[sys.executable, "app/agents/nutrition_agent/main.py"],
                health_url=nutrition_health,
            )
            fitness_proc = _start_server_if_needed(
                name="Fitness",
                cmd=[sys.executable, "app/agents/fitness_agent/main.py"],
                health_url=fitness_health,
            )

        out = asyncio.run(
            _run_clinical(weight_kg=float(args.weight_kg), height_cm=float(args.height_cm), query=args.query)
        )

        print("\n===== FINAL REPORT =====\n")
        print(out.get("final_report", ""))

        print("\n===== JSON OUTPUT =====\n")
        print(json.dumps(out, indent=2))

        return 0
    finally:
        # Only stop the servers we started.
        fitness_proc.stop()
        nutrition_proc.stop()


if __name__ == "__main__":
    raise SystemExit(main())
