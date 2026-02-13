"""
Centralized response schemas for revenue and returns data.
These schemas define the structure of response_json for both revenue and returns.
"""

# Revenue Response Schema
REVENUE_RESPONSE_SCHEMA = {
    "data": {
        "years": ["Y1", "Y2", "Y3", "Y4"],
        "products": [
            {
                "name": "string",
                "average_price": "number",
                "units_sold": "number",
                "revenue": ["number"]
            }
        ],
        "total_revenue": ["number"]
    },
    "component_type": "chart",
    "chart_type": "bar|pie|line",
    "fin_year": "string",
    "projections": "number",
    "currency": "string"
}

# Returns Response Schema
RETURNS_RESPONSE_SCHEMA = {
    "data": {
        "years": ["Y1", "Y2", "Y3", "Y4"],
        "products": [
            {
                "name": "string",
                "average_price": "number",
                "units_returned": "number",
                "revenue": ["number"]
            }
        ],
        "total_revenue": ["number"]
    },
    "component_type": "chart",
    "chart_type": "bar|pie|line",
    "fin_year": "string",
    "projections": "number",
    "currency": "string"
}

# Example data structures for prompts
REVENUE_EXAMPLE_DATA = {
    "data": {
        "years": ["Y1", "Y2", "Y3"],
        "products": [
            {
                "name": "AI_GENERATED_PRODUCT_NAME_1",
                "average_price": None,
                "units_sold": None,
                "revenue": [None, None, None]
            },
            {
                "name": "AI_GENERATED_PRODUCT_NAME_2",
                "average_price": None,
                "units_sold": None,
                "revenue": [None, None, None]
            },
            {
                "name": "AI_GENERATED_PRODUCT_NAME_3",
                "average_price": None,
                "units_sold": None,
                "revenue": [None, None, None]
            },
            {
                "name": "AI_GENERATED_PRODUCT_NAME_4",
                "average_price": None,
                "units_sold": None,
                "revenue": [None, None, None]
            },
            {
                "name": "AI_GENERATED_PRODUCT_NAME_5",
                "average_price": None,
                "units_sold": None,
                "revenue": [None, None, None]
            }
        ],
        "total_revenue": [None, None, None]
    },
    "component_type": "chart",
    "chart_type": "bar"
}

RETURNS_EXAMPLE_DATA = {
    "data": {
        "years": ["Y1", "Y2", "Y3"],
        "products": [
            {
                "name": "Product/Service 1",
                "average_price": None,
                "units_returned": None,
                "revenue": [None, None, None]
            },
            {
                "name": "Product/Service 2",
                "average_price": None,
                "units_returned": None,
                "revenue": [None, None, None]
            },
            {
                "name": "Product/Service 3",
                "average_price": None,
                "units_returned": None,
                "revenue": [None, None, None]
            },
            {
                "name": "Product/Service 4",
                "average_price": None,
                "units_returned": None,
                "revenue": [None, None, None]
            },
            {
                "name": "Product/Service 5",
                "average_price": None,
                "units_returned": None,
                "revenue": [None, None, None]
            }
        ],
        "total_revenue": [None, None, None]
    },
    "component_type": "chart",
    "chart_type": "bar"
}

# Schema descriptions for prompts
REVENUE_SCHEMA_DESCRIPTION = """
Revenue data structure:
- data: Object containing years, products, and total_revenue
  - years: Array of year labels (Y1, Y2, Y3, Y4, etc.)
  - products: Array of product objects with name, average_price, units_sold, and revenue array
  - total_revenue: Array of total revenue values for each year
- component_type: Always "chart"
- chart_type: "bar", "pie", or "line"
- fin_year: Financial year period
- projections: Number of years to project
- currency: Currency code
"""

RETURNS_SCHEMA_DESCRIPTION = """
Returns data structure:
- data: Object containing years, products, and total_revenue
  - years: Array of year labels (Y1, Y2, Y3, Y4, etc.)
  - products: Array of product objects with name, average_price, units_returned, and revenue array
  - total_revenue: Array of total revenue values for each year
- component_type: Always "chart"
- chart_type: "bar", "pie", or "line"
- fin_year: Financial year period
- projections: Number of years to project
- currency: Currency code
"""

# Utility functions to generate dynamic schemas based on projections
def generate_revenue_response_format(projections: int, fin_year: str, currency: str) -> dict:
    """Generate revenue response format with dynamic projections."""
    # Use the exact projections provided
    years = [f"Y{i+1}" for i in range(projections)]
    
    return {
        "response_json": {
            "data": {
                "years": years,
                "products": [
                    {
                        "name": "AI_GENERATED_PRODUCT_NAME_1",
                        "average_price": None,
                        "units_sold": None,
                        "revenue": [None] * projections
                    },
                    {
                        "name": "AI_GENERATED_PRODUCT_NAME_2",
                        "average_price": None,
                        "units_sold": None,
                        "revenue": [None] * projections
                    },
                    {
                        "name": "AI_GENERATED_PRODUCT_NAME_3",
                        "average_price": None,
                        "units_sold": None,
                        "revenue": [None] * projections
                    },
                    {
                        "name": "AI_GENERATED_PRODUCT_NAME_4",
                        "average_price": None,
                        "units_sold": None,
                        "revenue": [None] * projections
                    },
                    {
                        "name": "AI_GENERATED_PRODUCT_NAME_5",
                        "average_price": None,
                        "units_sold": None,
                        "revenue": [None] * projections
                    }
                ],
                "total_revenue": [None] * projections
            },
            "component_type": "chart",
            "chart_type": "bar",
            "fin_year": fin_year,
            "projections": projections,
            "currency": currency
        }
    }

def generate_returns_response_format(projections: int, fin_year: str, currency: str) -> dict:
    """Generate returns response format with dynamic projections."""
    # Use the exact projections provided
    years = [f"Y{i+1}" for i in range(projections)]
    
    return {
        "response_json": {
            "data": {
                "years": years,
                "products": [
                    {
                        "name": "Product/Service 1",
                        "average_price": None,
                        "units_returned": None,
                        "revenue": [None] * projections
                    },
                    {
                        "name": "Product/Service 2",
                        "average_price": None,
                        "units_returned": None,
                        "revenue": [None] * projections
                    },
                    {
                        "name": "Product/Service 3",
                        "average_price": None,
                        "units_returned": None,
                        "revenue": [None] * projections
                    },
                    {
                        "name": "Product/Service 4",
                        "average_price": None,
                        "units_returned": None,
                        "revenue": [None] * projections
                    },
                    {
                        "name": "Product/Service 5",
                        "average_price": None,
                        "units_returned": None,
                        "revenue": [None] * projections
                    }
                ],
                "total_revenue": [None] * projections
            },
            "component_type": "chart",
            "chart_type": "bar",
            "fin_year": fin_year,
            "projections": projections,
            "currency": currency,
            "topic": "pnl",
            "subject": "returns"
        }
    } 