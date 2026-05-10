import os
import requests

from dotenv import load_dotenv


load_dotenv()  # loads variables from a local .env file if present

# USDA FoodData Central API
USDA_API_KEY = os.getenv("USDA_API_KEY")

BASE_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

def get_nutritional_data(food_query: str):
    """
    Fetch factual nutrition data from USDA FoodData Central.
    """
    if not food_query or not food_query.strip():
        return {"error": "food_query is required"}

    params = {
        "api_key": USDA_API_KEY,
        "query": food_query.strip(),
        "pageSize": 1,  # Get the most relevant match
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"error": f"USDA request failed: {exc}"}

    data = response.json()
    foods = data.get("foods") or []
    if not foods:
        return {"error": "Food data not found"}

    food = foods[0]
    food_nutrients = food.get("foodNutrients") or []

    # Extract a small set of nutrients if present.
    nutrients = {
        n.get("nutrientName"): n.get("value")
        for n in food_nutrients
        if n.get("nutrientName") is not None
    }

    return {
        "food": food.get("description"),
        "nutrients": nutrients,
        "dataType": food.get("dataType"),
        "fdcId": food.get("fdcId"),
    }