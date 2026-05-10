from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


_REPO_ROOT = Path(__file__).resolve().parents[4]
BMI_MCP_SERVER_PY = _REPO_ROOT / "app" / "shared_tools" / "bmi_mcp_server" / "server.py"


async def calculate_bmi_via_mcp(*, weight_kg: float, height_cm: float) -> dict[str, Any]:
    """Fetch BMI metrics from the BMI MCP server.

    This is the function the Clinical Agent should call using user-provided weight/height.
    """

    server_py = BMI_MCP_SERVER_PY
    if not server_py.is_file():
        raise FileNotFoundError(f"BMI MCP server.py not found at: {server_py}")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_py)],
        env=None,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "calculate_bmi",
                arguments={
                    "weight_kg": float(weight_kg),
                    "height_cm": float(height_cm),
                },
            )

            if result.isError:
                raise RuntimeError(f"BMI MCP tool error: {result}")

            if not result.structuredContent:
                raise RuntimeError("BMI MCP tool returned no structuredContent")

            return dict(result.structuredContent)
