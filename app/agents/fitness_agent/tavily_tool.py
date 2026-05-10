import os

from dotenv import load_dotenv

from tavily import TavilyClient

load_dotenv()  # loads variables from a local .env file if present

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


def get_tavily_client():
    """Create a Tavily client."""
    if not TAVILY_API_KEY:
        raise RuntimeError(
            "TAVILY_API_KEY is not set. Put `TAVILY_API_KEY=...` in .env (repo root) or set it in your environment."
        )
    return TavilyClient(api_key=TAVILY_API_KEY)


class _TavilySearchTool:
    def __init__(self, max_results: int = 2):
        self.max_results = max_results

    def run(self, query: str):
        client = get_tavily_client()
        resp = client.search(query=query, max_results=self.max_results, include_answer=True)
        # Prefer returning results list for compatibility with existing callers
        if isinstance(resp, dict) and isinstance(resp.get("results"), list):
            return resp["results"]
        return resp


try:
    from langchain_community.tools.tavily_search import TavilySearchResults  # type: ignore
    if TAVILY_API_KEY:
        fitness_search_tool = TavilySearchResults(
            max_results=3,
            description="Search for the latest workout routines and physical activity guidelines.",
        )
    else:
        fitness_search_tool = None
except ModuleNotFoundError:
    fitness_search_tool = _TavilySearchTool(max_results=2) if TAVILY_API_KEY else None