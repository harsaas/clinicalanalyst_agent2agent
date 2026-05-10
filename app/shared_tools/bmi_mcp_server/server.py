from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server with a descriptive name
mcp = FastMCP("BMI calculator server")

@mcp.tool()
def calculate_bmi(weight_kg: float, height_cm: float) -> dict[str, float | str]:
    """
    Calculate Body Mass Index (BMI) given weight in kilograms and height in centimeters.

    Parameters:
    weight_kg (float): Weight in kilograms
    height_cm (float): Height in centimeters

    Returns:
    float: Calculated BMI
    """
    if weight_kg <= 0:
        raise ValueError("weight_kg must be > 0")
    if height_cm <= 0:
        raise ValueError("height_cm must be > 0")

    # Convert height from centimeters to meters
    height_m = height_cm / 100.0
    
    # Calculate BMI using the formula: BMI = weight (kg) / (height (m))^2
    bmi_value = weight_kg / (height_m ** 2)
    
    if bmi_value < 18.5:
        category = "Underweight"
    elif 18.5 <= bmi_value < 25:
        category = "Normal weight"
    elif 25 <= bmi_value < 30:
        category = "Overweight"
    else:
        category = "Obese"
        
    return {
        "bmi": bmi_value,
        "category": category,
        "units": "metric"
    }

if __name__ == "__main__":
    # Keep it simple: stdio transport (default).
    # This works with MCP Inspector and with stdio-spawned clients.
    mcp.run()