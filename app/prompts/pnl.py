"""
PNL-related AI prompts for the business application.
All prompts used for revenue, COGS, operating expenses, depreciation, 
other income, interest expense, and income before taxes.
"""

from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Body
from app.models.models import PNLStatement, UserProgress, UserBasicDetails, RevenueStream, Return, COGS, OperatingExpenses, DepreciationNAmortisation, Skipped, OtherIncome, BalanceSheet, WorkingCapital, Inventory, InterestExpense, IncomeBeforeTaxes, CashFlowStatement, OtherExpense
from app.schemas.response_schemas import (
    REVENUE_SCHEMA_DESCRIPTION,
    RETURNS_SCHEMA_DESCRIPTION
)

from app.core.database import get_db
# Constants
NUMBER_OF_SUGGESTIONS = 10
NUMBER_OF_PROJECTIONS = 5

# Legacy constants for backward compatibility
REVENUE = {
    f"""
    GenAI to suggest what are the different revenue streams (Product/ Service 1-n), and client will select all or fewer. Client can also select and modify name, or add their own by typing,
    Client inputs average price and units sold in Y1 per selected product/ service. Alternatively, client can directly put the revenue amount for simplicity,
    Calculation is performed by multiplying price and units sold for Y1, or direct client revenue input is populated,
   Revenue output is projected using YoY growth rate from GenAI OR client's input on price and units sold increase YoY
    """
}

REVENUE_SCHEMA = REVENUE_SCHEMA_DESCRIPTION

RETURNS = {
    f"""
    GenAI to suggest whether this business can have returns (e.g. in case of product business there are returns). Only if applicable, the return option will pop up for client inputs,
    Client to specify any returns to units sold by product. Units returned × average price will be calculated to get return value,
    Calculate %age of return by units sold, and apply across rest of the years
    """
}

RETURNS_SCHEMA = RETURNS_SCHEMA_DESCRIPTION


# ============================================================================
# REVENUE PROMPTS
# ============================================================================

def get_revenue_title_suggestions_prompt(basic_details, projections: int = None):
    """
    Generate revenue title suggestions with growth rates for multiple years.
    """
    # projections = projections or basic_details.projections or 3
    
    return f"""
      Based on the following business details, suggest up to 10 revenue stream titles (products/services) with their respective yearly growth rate projections.
  
        Company Details:
        - Industry: {basic_details.industry}
        - Country: {basic_details.country}
        - City: {basic_details.city}
        - Company Size: {basic_details.company_size}
        - Business Model: {basic_details.business_model}
        - Projection Period: {projections} years

        STRICT RULES:
        1. The "growth_rates" array MUST contain exactly {projections - 1} numeric values.
        - Example: If projections = 5 total years (Y1–Y5), growth_rates must contain exactly 4 values (for Y2–Y5).
        2. Y1 is the base year and MUST NOT be included in growth_rates.
        3. Total suggestions must be between 1 and 10.
        4. "market_trend" MUST be exactly one of:
        - "rising"
        - "stable"
        - "declining"

        For each revenue stream, include:
        1. "name": A product or service relevant to this industry and business model.
        2. "growth_rates": A list of {projections - 1} yearly growth percentages (positive, zero, or negative).
        3. "confidence": A score between 0 and 1 reflecting confidence in the growth projection.
        4. "market_trend": Overall trend indicator (from the allowed list).

        Return strictly in this JSON structure:
       {{ 
        "suggestions": [
            {{
                "name": "Product/Service Name",
                "growth_rates": [Y2, Y3, ..., Y{{projections}}],
                "confidence": 0.85,
                "market_trend": "rising"
            }}
                  ]
        }}


       Growth Rate Guidelines:
        - Base Y1 has no growth; projections start from Y2 onward.
        - Growth rates must be realistic based on market standards, historical data patterns, competitive environment, and macroeconomic conditions.
        - Growth should reflect:
        - current trends in {basic_details.industry},
        - economic environment of {basic_details.country},
        - business model and company size dynamics.
        - Growth rates must be integers only and may be positive, negative, or zero
        - Year-over-year growth can be stable, increasing, or decreasing.
        - Negative or zero growth is also acceptable where market or financial conditions justify it.
        - Confidence should be aligned with industry maturity, market volatility, business resilience, and forecast predictability.

        IMPORTANT:
        - Provide ONLY up to 10 suggestions.
        - Ensure growth_rates length is exactly {projections - 1} and never more or fewer.
        - Return only the "suggestions" array in the defined JSON structure (no additional text).


        """


def get_product_growth_rate_prompt(product_name: str, basic_details, projections: int = None):
    """
    Get real growth rates for legitimate products using AI.
    """
    projections = projections or basic_details.projections or 3
    
    return f"""
        Based on the following business context, analyze the REAL growth rates for the legitimate product/service: "{product_name}".

        Company Details:
        - Industry: {basic_details.industry}
        - Country: {basic_details.country}
        - City: {basic_details.city}
        - Company Size: {basic_details.company_size}
        - Business Model: {basic_details.business_model}
        - Projections: {projections} years

        IMPORTANT: Keep the product name EXACTLY as provided: "{product_name}" - DO NOT modify it.

        Research and provide REALISTIC growth rates based on:
        1. Current market trends for this specific product in the {basic_details.industry} industry
        2. Company size and business model factors
        3. Economic conditions in {basic_details.country}
        4. Industry growth patterns and forecasts

        Return JSON format:
        {{
            "growth_rates": [15.5, 18.2],
            "confidence": 0.85,
            "market_trend": "rising",
            "analysis": "Detailed explanation of growth rate reasoning based on real market research"
        }}

        CRITICAL:
        - Provide up to 4 growth rate values in the array.
        - Return ONLY valid JSON.
        - Do not include explanations.
        - Do not include markdown.
        - Do not include comments.
        - Do not include text outside JSON.
        - Growth rates must be integers only and may be positive, negative, or zero
        - Growth rates must be realistic based on actual market conditions for the product, industry, company size, and country.
        - AI is free to determine any appropriate growth rate range (including very low, very high, negative, or zero) as long as it is justified in the analysis.
        - Negative, zero, or >25% growth is allowed when supported by market reasoning.
        """


def validate_product_name_prompt(product_name: str, basic_details):
    """
    Strict validation of whether a product/service name is meaningful and usable in a business context.
    """
    return f"""
       You are a business data validation assistant.

        Your task is to evaluate whether the given name represents a
        REASONABLE, MEANINGFUL, and USABLE business product or service
        within the provided company context.

        Product / Service Name to Evaluate:
        "{product_name}"

        Company Context:
        - Industry: {basic_details.industry}
        - Company Size: {basic_details.company_size}
        - Business Model: {basic_details.business_model}

        EVALUATION GUIDELINES:

        Mark LEGITIMATE if:
        - The name reasonably represents a real-world product or service
        - A typical customer or business user could understand what it refers to
        - It fits a plausible commercial or business use case in the given industry
        - It could reasonably appear in a product catalog, pricing sheet, or invoice

        Mark NON-LEGITIMATE only if the name is CLEARLY invalid, such as:
        - Random letters or numbers (e.g. "asdf123", "qwepoi")
        - Pure placeholders (e.g. "test", "demo", "sample")
        - Completely meaningless or invented words with no business interpretation
        - Extremely vague terms with no identifiable product or service meaning

        BORDERLINE CASES:
        - If the name is generic but still usable (e.g. "Quality & Compliance",
        "Digital Services", "Support Package"), mark LEGITIMATE with lower confidence
        - Use the confidence score to reflect uncertainty instead of rejecting
        - Do NOT over-penalize early-stage, internal, or descriptive product names

        WHEN IN DOUBT:
        - Prefer LEGITIMATE with reduced confidence

        IMPORTANT:
        - Do NOT assume legitimacy just because something sounds like a brand
        - Do NOT be overly strict or pedantic
        - Focus on usability for financial modeling and business analysis

        Return ONLY valid JSON.
        No markdown.
        No explanations outside JSON.

        JSON FORMAT:
        {{
            "is_legitimate": true | false,
            "confidence": 0.0-1.0,
            "reasoning": "Short, concrete business-focused explanation",
            "suggested_category": "Specific category or null"
        }}

        EXAMPLES:

        Legitimate (High Confidence):
        - "iPhone"
        - "Cloud Backup Service"
        - "Gas Cylinders"
        - "Enterprise SaaS Subscription"

        Legitimate (Lower Confidence):
        - "Quality & Compliance"
        - "Digital Services"
        - "Support Package"
        - "Professional Services"

        Not Legitimate:
        - "asdf123"
        - "xyzqwerty"
        - "product1"
        - "test service"
        """



# ============================================================================
# COGS PROMPTS
# ============================================================================

def get_cogs_title_suggestions_prompt(basic_details):
    """
    Generate COGS title suggestions based on user's business context.
    """
    return f"""
        Based on the following business details, suggest up to 10 Cost of Goods Sold (COGS) categories that would be appropriate for this business.

        Company Details:
        - Industry: {basic_details.industry}
        - Country: {basic_details.country}
        - City: {basic_details.city}
        - Company Size: {basic_details.company_size}
        - Business Model: {basic_details.business_model}

        Please provide Upto 10 COGS categories that are:
        1. Relevant to the industry and business model
        2. Appropriate for the company size
        3. Realistic and practical for the business
        4. Specific enough to be actionable
        5. Varied in nature (materials, labor, overhead, etc.)

        Return the suggestions as a JSON array of strings with the exact field name "titles".
        Example format: {{"titles": ["Title 1", "Title 2", "Title 3", ...]}}

        Make sure to provide Upto 10 suggestions.
        """

def validate_cogs_product_name_prompt(cogs_name: str, basic_details):
    """
    Strict validation of whether a COGS (Cost of Goods Sold) item is valid,
    meaningful, and appropriate for financial modeling.
    """
    return f"""
       You are a financial modeling assistant with accounting knowledge.

        Your task is to evaluate whether the given name represents a
        REASONABLE and MEANINGFUL **Cost of Goods Sold (COGS)** item
        for the given business context.

        COGS Item to Evaluate:
        "{cogs_name}"

        Company Context:
        - Industry: {basic_details.industry}
        - Company Size: {basic_details.company_size}
        - Business Model: {basic_details.business_model}

        IMPORTANT CONTEXT:
        COGS generally includes **direct or semi-direct costs** that are
        closely related to producing, delivering, or supporting a product
        or service.

        COGS MAY INCLUDE (depending on industry & model):
        - Raw materials and inputs
        - Manufacturing or processing labor
        - Packaging, logistics, and fulfillment
        - Direct production utilities
        - Cloud infrastructure or hosting tied to service delivery
        - Quality control, testing, compliance, or certification costs
        - Third-party services required to deliver the product
        - Transaction or usage-based fees

        CLEARLY INVALID (mark NON-LEGITIMATE):
        • Random strings or nonsense (e.g. "asdf123")
        • Placeholders (e.g. "test", "demo", "sample")
        • Pure revenue items (e.g. "Product Sales", "Subscriptions")
        • High-level or vague terms with no cost meaning (e.g. "Costs", "Operations")
        • Capital assets or depreciation items

        BORDERLINE CASES:
        - If the item could be COGS in some industries but OPEX in others,
          lean toward LEGITIMATE with LOWER confidence.
        - Use confidence to express uncertainty instead of rejecting.

        DECISION GUIDELINES:
        - Mark LEGITIMATE if a finance professional could reasonably justify
          including it in COGS for this business context.
        - Mark NON-LEGITIMATE only if it clearly does not belong in COGS.

        WHEN IN DOUBT:
        - Prefer LEGITIMATE with reduced confidence.

        Return ONLY valid JSON.
        No markdown.
        No explanations outside JSON.

        JSON FORMAT:
        {{
            "is_legitimate": true | false,
            "confidence": 0.0-1.0,
            "reasoning": "Short, finance-focused explanation",
            "suggested_category": "Specific COGS category or null"
        }}

        EXAMPLES:

        Legitimate (High Confidence):
        - "Raw Materials"
        - "Manufacturing Labor"
        - "Packaging Costs"
        - "Cloud Hosting Costs"
        - "Payment Gateway Fees"

        Legitimate (Lower Confidence / Context-Dependent):
        - "Quality & Compliance"
        - "Testing & Certification"
        - "Third-Party Audits"
        - "Production Support Services"

        Not Legitimate:
        - "Marketing Spend"
        - "Office Rent"
        - "HR Salaries"
        - "Sales Revenue"
        - "General Expenses"
        - "asdf123"
        """

def get_cogs_title_suggestions_with_revenue_context_prompt(basic_details, revenue_selected_titles: list, revenue_projected_titles: list, projections: int = None):
    """
    Generate COGS title suggestions with growth rates based on user's business context and revenue selected titles.
    """
    projections = projections or basic_details.projections or 3
    revenue_titles_combined = list(set((revenue_selected_titles or [])))
    
    return f"""
        Based on the following business details and revenue products, suggest Upto 10 Cost of Goods Sold (COGS) categories appropriate for this business.

        Company Details:
        - Industry: {basic_details.industry}
        - Country: {basic_details.country}
        - City: {basic_details.city}
        - Company Size: {basic_details.company_size}
        - Business Model: {basic_details.business_model}
        - Projections: {projections} years

        Revenue Products/Services (Selected + Projected):
        {', '.join(revenue_titles_combined) if revenue_titles_combined else 'No revenue products specified'}

        IMPORTANT CONTEXT NOTE:
        - The Revenue Products/Services listed above are provided **only to establish business context**.
        - Do NOT map or generate COGS on a per-revenue-item basis.
        - Use the revenue titles only to understand the nature of the business and its core value delivery, then suggest appropriate **business-level COGS categories**.

        IMPORTANT RULES:
        - COGS categories must represent **direct cost components** required to produce, manufacture, or deliver the listed revenue products.
        - Examples:
        - If revenue is "Generic Drugs", valid COGS include "Raw Material Procurement", "Manufacturing Labor", "Packaging & Distribution".
        - If revenue is "Software Subscription Sales", valid COGS include "Server Hosting Costs", "Customer Support Operations".
        - Avoid generic or vague names such as "Miscellaneous Costs" or "General Expenses".
        - COGS must be tightly linked to the revenue products listed above.

        For each COGS category, provide:
        1. COGS category name relevant to the industry, business model, and revenue products
        2. Percentage of total revenue for each year of the projection period ({projections} years total)
        3. Confidence score for the percentage estimates
        4. Market trend analysis (rising / stable / declining)

        Please provide Upto 10 COGS categories with the following JSON structure:
        {{
            "suggestions": [
                {{
                    "name": "COGS Category Name",
                    "percentage_of_revenue": [35, 36, 37, 38, 39],
                    "confidence": 0.82,
                    "market_trend": "rising"
                }}
            ]
        }}

        COGS Percentage Guidelines:
        - Research current market norms for COGS components in the {basic_details.industry} industry
        - Consider the company size ({basic_details.company_size}) and business model ({basic_details.business_model})
        - Factor in country-level economic conditions ({basic_details.country})
        - Account for location-specific cost structures ({basic_details.city}, {basic_details.country})
        - Percentages must reflect how each COGS category typically behaves as a share of revenue
        - Provide realistic year-over-year changes in COGS percentage based on:
        - Input cost inflation/deflation
        - Efficiency gains or scaling effects
        - Industry pricing pressure
        - The AI has full flexibility to determine appropriate values (including low, high, zero, or declining percentages), as long as they are realistic and justified
        - Percentages must be **integers only**
        - Percentages may increase, decrease, or remain stable year over year
        - Avoid extreme or unrealistic jumps unless clearly justified by business or market conditions
        - Higher confidence for well-established cost categories, lower for volatile or emerging ones

        CRITICAL:
        - Provide EXACTLY {projections} percentage_of_revenue values for each COGS category
        - Make sure to provide Upto 10 suggestions

        """


def get_cogs_product_growth_rate_prompt(product_name: str, basic_details, projections: int = None):
    """
    Calculate growth rates for a COGS product using AI analysis.
    """
    projections = projections or basic_details.projections or 5
    
    return f"""
        You are a financial analyst. Analyze the Cost of Goods Sold (COGS) behavior for the product "{product_name}" in the {basic_details.industry} industry.

        Business Context:
        - Industry: {basic_details.industry}
        - Company Size: {basic_details.company_size}
        - Business Model: {basic_details.business_model}
        - Location: {basic_details.city}, {basic_details.country}

        CRITICAL:
        - Generate REALISTIC and UNIQUE COGS percentage-of-revenue values based on the specific product "{product_name}".
        - Different products MUST have different COGS percentage patterns.
        - Do NOT use generic or repeated values across products.

        IMPORTANT:
        - You MUST respond with ONLY valid JSON.
        - Do NOT include explanations, reasoning steps, or any text outside the JSON.

        Return ONLY this JSON format (no other text):
        {{
            "corrected_name": "{product_name}",
            "percentage_of_revenue": [X, X, X, X, X],
            "confidence": 0.X,
            "market_trend": "rising/stable/declining"
        }}

        Guidelines:
        - Focus on **direct COGS cost behavior** for "{product_name}"
        - Consider:
        - Raw material or input costs
        - Labor or processing costs
        - Supply chain and logistics costs
        - Economies of scale or efficiency improvements
        - Provide EXACTLY {projections} percentage_of_revenue values
        - Percentages must be **integers only**
        - Percentages may increase, decrease, or remain stable year over year
        - Percentages may be low, high, zero, or declining if justified by the product economics
        - Avoid extreme or unrealistic jumps unless clearly justified
        - Confidence should reflect certainty in the estimates (0.0 to 1.0)
        - Market trend must be one of: "rising", "stable", or "declining"
        - Return ONLY the JSON object, no explanations

        """


# ============================================================================
# OPERATING EXPENSES PROMPTS
# ============================================================================

def get_operating_expenses_title_suggestions_prompt(basic_details, projections: int = None):
    """
    Generate operating expenses title suggestions with growth rates based on user's business context.
    """
    # projections = projections or getattr(basic_details, 'projections', 5)
    # • Existing Revenue Titles: {existing_revenue_titles}
    #  • Existing COGS Titles: {existing_cogs_titles}
    return f"""
        List all the operating expenses for a business of SIZE ({basic_details.company_size}), in the INDUSTRY/SECTOR ({basic_details.industry}), from LOCATION ({basic_details.city}, {basic_details.country}), operating under the following BUSINESS MODEL(S): {basic_details.business_model}.

        For each operating expense category, provide:
        1. Operating expense category name that is relevant to the industry, business model, and company size
        2. Provide the percentage of total revenue for each year of the projection period. ({projections} years total)
        3. Confidence score for the growth rate predictions
        4. Market trend analysis (rising/stable/declining)

        Please provide Upto 10 operating expense categories with the following JSON structure:
        {{
            "suggestions": [
                {{
                    "name": "Operating Expense Category Name",
                    "percentage_of_revenue": [5.5, 6.0, 6.5, 7.0, 7.5],
                    "confidence": 0.82,
                    "market_trend": "rising"
                }}
            ]
        }}
        IMPORTANT RESTRICTIONS:
        - DO NOT use, repeat, copy, or derive from any existing user revenue or COGS titles.
        - Avoid naming, category similarity, or variants of the following:
        

        Revenue Percentage Guidelines:
        - Research current market trends for each operating expense category in the {basic_details.industry} industry
        - Consider the company size ({basic_details.company_size}) and business model ({basic_details.business_model})
        - Factor in the country's economic conditions ({basic_details.country})
        - Consider the location-specific costs ({basic_details.city}, {basic_details.country})
        - Provide realistic year-over-year changes in the percentage of revenue based on market conditions, industry norms, and business context. The AI has full flexibility to determine appropriate values (including low, high, zero, or negative changes) as long as they are justified.
        - These percentage-of-revenue values should be provided for each of the {projections} years.
        - The percentage of revenue for each operating expense should be provided for every year of the {projections}-year period.
        - These percentages may vary year to year, but the fluctuations should remain realistic and within a reasonable range based on industry norms and business context.
        - Avoid extreme or unrealistic jumps unless clearly justified by the business model or market conditions.
        - Higher confidence for well-established categories, lower for emerging markets

        Make sure to provide Upto 10 suggestions with exactly {projections} growth rates each.
        """


def get_operating_expense_growth_rate_prompt(expense_name: str, basic_details, projections: int = None):
    """
    Calculate growth rates for an operating expense using AI analysis.
    """
    projections = projections or getattr(basic_details, 'projections', 5)
    
    return f"""
        You are a financial analyst. Analyze the revenue percentage for the operating expense "{expense_name}" in the {basic_details.industry} industry.

        Business Context:
        - Industry: {basic_details.industry}
        - Company Size: {basic_details.company_size}
        - Business Model(s): {basic_details.business_model}
        - Location: {basic_details.city}, {basic_details.country}

        CRITICAL:
        - Generate REALISTIC percentage-of-revenue values for this expense category.
        - Percentages should be provided for every year in the {projections}-year projection period.
        - Percentages may vary year to year, but variations must be reasonable and reflect industry norms.
        - The percentage of Revenue must be integers only and may be positive, negative, or zero
        - Avoid extreme, unjustified jumps unless supported by business logic.
        - This is NOT a growth rate; it represents the portion of revenue allocated to this operating expense.

        IMPORTANT:
        You MUST respond with ONLY valid JSON. Do not include any explanations, steps, or text outside the JSON.

        Return ONLY this JSON format (no other text):
        {{
            "corrected_name": "{expense_name}",
            "percentage_of_revenue": [X, X, X, X],
            "confidence": 0.X,
            "market_trend": "rising" | "stable" | "declining"
        }}

        Guidelines:
        - Focus on realistic yearly revenue percentage patterns for "{expense_name}".
        - Consider overhead behavior, cost structure, and industry expense norms.
        - Provide EXACTLY {projections} values in the revenue_percentage array.
        - The percentage of Revenue must be integers only and may be positive, negative, or zero
        - AI has full flexibility: percentages may be low, high, zero, or negative if justified.
        - Confidence should reflect certainty in the analysis (0.0 to 1.0).
        - Market trend must be exactly one of: "rising", "stable", "declining".
        - Return ONLY the JSON object.

        """



def validate_operating_expense_product_name_prompt(opex_name: str, basic_details):
    """
    Strict validation of whether an Operating Expense (OPEX) item is valid,
    meaningful, and appropriate for financial modeling.
    """
    return f"""
        You are a STRICT financial and accounting data validator.

        Your task is to decide whether the given name represents a
        REAL, MEANINGFUL, and VALID **Operating Expense (OPEX)** item.

        Operating Expense to Validate:
        "{opex_name}"

        Company Context:
        - Industry: {basic_details.industry}
        - Company Size: {basic_details.company_size}
        - Business Model: {basic_details.business_model}

        IMPORTANT DEFINITION:
        Operating Expenses (OPEX) are **indirect costs** required to run
        the business but are **NOT directly tied** to producing or delivering
        a product or service.

        VALID OPEX examples:
        - Marketing and advertising spend
        - Sales team salaries
        - Administrative salaries
        - Office rent
        - Utilities (non-production)
        - Legal, accounting, and professional fees
        - HR and recruitment costs
        - Software subscriptions (internal use)
        - Travel and training expenses
        - Customer support costs
        - Insurance and compliance costs

        STRICT RULES (VERY IMPORTANT):

        Mark NONSENSE or INVALID if the name is:
        • Random letters or numbers (e.g. "asdf123", "qwepoi")
        • A placeholder (e.g. "test", "sample", "demo")
        • A revenue item (e.g. "Product Sales", "Subscriptions")
        • A COGS / direct production cost such as:
          - Raw materials
          - Manufacturing labor
          - Packaging costs
          - Hosting costs directly tied to product delivery
        • A capital expenditure (CapEx) or asset purchase
        • Depreciation or amortization
        • Too vague or generic (e.g. "Costs", "Expenses", "Operations")
        • A category label instead of a specific expense

        Mark LEGITIMATE only if:
        • It is an indirect cost required to operate the business
        • It clearly fits under OPEX from an accounting perspective
        • A finance professional would confidently classify it as OPEX
        • It does NOT scale directly with production or sales volume

        WHEN IN DOUBT:
        - Choose NONSENSE / INVALID

        DO NOT assume legitimacy.
        DO NOT be lenient.
        BE STRICT.

        Return ONLY valid JSON.
        No markdown.
        No explanations outside JSON.

        JSON FORMAT:
        {{
            "is_legitimate": true | false,
            "confidence": 0.0-1.0,
            "reasoning": "Short, finance-focused explanation",
            "suggested_category": "Specific OPEX category or null"
        }}

        EXAMPLES:

        Legitimate:
        - "Marketing Spend"
        - "Office Rent"
        - "Sales Team Salaries"
        - "HR Software Subscription"
        - "Legal and Compliance Fees"
        - "Customer Support Salaries"

        NOT Legitimate:
        - "Raw Materials"
        - "Manufacturing Labor"
        - "Product Sales"
        - "Payment Gateway Fees"
        - "Depreciation"
        - "Capital Equipment"
        - "asdf123"
        - "test expense"
        """


# ============================================================================
# DEPRECIATION & AMORTISATION PROMPTS
# ============================================================================

def get_depreciation_assets_prompt(basic_details, user_id, db):
    """
    Generate 3 depreciation/amortisation assets using AI based on user's business context.
    """
    pnl_statement = db.query(PNLStatement).filter(
        PNLStatement.user_id == user_id
    ).first()
    # 📌 Existing Revenue
    existing_revenue_titles = []
    revenue_record = db.query(RevenueStream).filter(
        RevenueStream.pnl_id == pnl_statement.id
    ).first()
    if revenue_record and revenue_record.selected_titles:
        for s in revenue_record.selected_titles:
            if isinstance(s, dict):
                existing_revenue_titles.append((s.get("name") or "").strip().lower())
            elif isinstance(s, str):
                existing_revenue_titles.append(s.strip().lower())


    return f"""
      You are a financial analyst. Generate upto 6 realistic depreciation/amortisation assets for a business.

    Business Context:
    - Industry: {basic_details.industry}
    - Company Size: {basic_details.company_size}
    - Business Model: {basic_details.business_model}
    - Location: {basic_details.city}, {basic_details.country}
    - Base Year: {basic_details.base_year}

    CRITICAL: Generate REALISTIC and RELEVANT assets based on the specific business context.
    Different industries and company sizes should have different types of assets.

    🔒 RESTRICTION:
    The following Revenue Products are provided strictly for understanding the business context only:
    • Existing Revenue Titles: {existing_revenue_titles}

    IMPORTANT: You MUST respond with ONLY valid JSON. Do not include any explanations, steps, or text outside the JSON.

    Return ONLY this JSON format (no other text):
    {{
        "assets": [
            {{
            "asset_name": "Asset Name",
            "purchase_year": 2022,
            "purchase_cost": 1000,
            "asset_type": "Tangible asset",
            "useful_life_years": 10
            }},
            {{
            "asset_name": "Asset Name",
            "purchase_year": 2023,
            "purchase_cost": 2000,
            "asset_type": "Intangible asset",
            "useful_life_years": 5
            }},
            {{
            "asset_name": "Asset Name",
            "purchase_year": 2024,
            "purchase_cost": 1500,
            "asset_type": "Tangible asset",
            "useful_life_years": 8
            }}
        ]
    }}


    Guidelines:
    - Generate upto 6 assets.
    - Mix of tangible assets (for depreciation) and intangible assets (for amortisation).
    - Asset names should be specific to the {basic_details.industry} industry.
    - Purchase years should be {basic_details.base_year}.
    - Purchase costs should be realistic for a {basic_details.company_size} company.
    - Include both high-value and medium-value assets.
    - asset_type MUST be exactly one of:
        - "Tangible asset"
        - "Intangible asset"
    - useful_life_years MUST be a positive integer number of years (or null ONLY if the asset clearly has no depreciation, such as land if you decide to include it).
    - Tangible assets examples: furniture, equipment, machinery, vehicles, buildings.
    - Intangible assets examples: software, licenses, patents, trademarks, goodwill.
    - Use realistic useful lives, e.g.:
        - Buildings: 30–50 years
        - Machinery/Equipment: 8–15 years
        - Computers/IT equipment: 3–5 years
        - Furniture & fixtures: 7–10 years
        - Vehicles: 5–10 years
        - Software/Licenses: 3–7 years
    - Return ONLY the JSON object, no explanations or extra text.
    """

def get_depreciation_details_prompt(user_details, assets_for_ai):
    """
    Generate AI-powered depreciation and amortisation details for assets.
    """
    import json
    
    return f"""
        You are a professional accountant.

        Business Context:
        - Industry: {user_details.industry or 'Not specified'}
        - Company Size: {user_details.company_size or 'Not specified'}
        - Business Model: {user_details.business_model or 'Not specified'}

        STRICT RULES:
        - You must analyze ONLY the assets provided.
        - Do NOT invent, rename, or merge assets.
        - Use standard accounting depreciation rules.
        - Maintain the SAME ORDER as input.

        Assets:
        {json.dumps(assets_for_ai, indent=2)}

        TASK:
        For each asset, determine:

        1. asset_type:
        - "Tangible asset" → physical assets
        - "Intangible asset" → non-physical assets

        2. useful_life_years:
        - Return a positive integer (e.g., 3, 5, 10)    

        OUTPUT FORMAT (STRICT JSON ONLY):
            {{
            "assets": [
                {{
                "asset_type": "Tangible asset",
                "useful_life_years": 5
                }}
            ]
            }}

        CRITICAL:
        - Return ONLY JSON
        - No markdown
        - No explanations
        - No extra fields
        - Assets array length MUST match input length
        """


# ============================================================================
# OTHER INCOME PROMPTS
# ============================================================================

def get_other_charges_title_suggestions_prompt(basic_details, db: Session,
    user_id: int,
    projections: int = None):
    """
    Generate other charges/expenses title suggestions with growth rates based on user's business context.
    """
    projections = projections or basic_details.projections or 5
    pnl_record = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
    existing_revenue_titles = []
    if pnl_record:
        revenue_record = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_record.id).first()
        if revenue_record and revenue_record.selected_titles:
            existing_revenue_titles = [item.get("name", "") for item in revenue_record.selected_titles]
    
    return f"""
        You are a financial expert helping a {basic_details.company_size} company in the {basic_details.industry} industry.
        The company's business model is: {basic_details.business_model}
        
        Generate Upto 6 "Other Incomes" that are SPECIFIC to this {basic_details.industry} industry and {basic_details.company_size} company size.
        
        CRITICAL:
        All titles must be highly specific to the {basic_details.industry} industry.
        Avoid any generic, broad, or universally applicable terms. 
        Each title must clearly reflect a specialised income source unique to how companies in this industry operate.
        
        IMPORTANT RESTRICTIONS:
        - The following are EXISTING REVENUE TITLES and are provided ONLY for CONTEXT.
        - Use them strictly to understand the business model and cost structure.
            • Existing Revenue Titles: {existing_revenue_titles}
            

        Instead, think of SPECIFIC Incomes that a {basic_details.industry} company would have:
        - You must independently and creatively identify other income streams that are naturally and realistically possible for companies in the {basic_details.industry} industry.
        - Do NOT rely on pre-given examples. 
        - Do NOT generalize. 
        - Think deeply about this industry’s unique operations, ecosystem, compliance, partnerships, and monetisation opportunities.
        
        Return ONLY a JSON array with Upto 6 objects:
        [
            {{"name": "Industry-Specific Charge 1", "description": "Specific to {basic_details.industry}", "growth_rates": [2,3,4,4,5], "market_trend": "rising"}},
            {{"name": "Industry-Specific Charge 2", "description": "Specific to {basic_details.industry}", "growth_rates": [1,2,2,3,3], "market_trend": "stable"}},
            {{"name": "Industry-Specific Charge 3", "description": "Specific to {basic_details.industry}", "growth_rates": [3,4,5,5,6], "market_trend": "rising"}},
            {{"name": "Industry-Specific Charge 4", "description": "Specific to {basic_details.industry}", "growth_rates": [2,2,3,3,4], "market_trend": "stable"}},
            {{"name": "Industry-Specific Charge 5", "description": "Specific to {basic_details.industry}", "growth_rates": [4,5,6,6,7], "market_trend": "rising"}},
            {{"name": "Industry-Specific Charge 6", "description": "Specific to {basic_details.industry}", "growth_rates": [1,1,2,2,3], "market_trend": "stable"}}
        ]
        
        REQUIREMENTS:
        - Upto 6 objects, no more, no less
        - Use double quotes for all strings
        - Growth rates as numbers (including negative or zero growth, if any)
        - Market trend: "rising", "stable", or "declining"
        - NO generic terms - be specific to {basic_details.industry}
        - Return ONLY the JSON array
        """


# ============================================================================
# OTHER EXPENSE PROMPTS
# ============================================================================

def get_other_expense_title_suggestions_prompt(
    basic_details,
    projections: int = None,
    user_id: int = None,
    db: Session = None
):    

    """
    Generate other expense title suggestions with growth rates based on user's business context.
    """
    projections = projections or basic_details.projections or 5
    pnl_record = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()

    existing_revenue_titles = []
    existing_cogs_titles = []
    existing_operating_titles = []
    existing_other_income_titles = []
    if pnl_record:
    # ---------------- Revenue ---------------- #
        revenue_record = db.query(RevenueStream).filter(
            RevenueStream.pnl_id == pnl_record.id
        ).first()
        if revenue_record and revenue_record.selected_titles:
            existing_revenue_titles = [
                (item.get("name") or "").lower()
                for item in revenue_record.selected_titles
                if isinstance(item, dict)
            ]


    return f"""
        You are a financial expert helping a {basic_details.company_size} company in the {basic_details.industry} industry.
        The company's business model is: {basic_details.business_model}
        
        Generate Upto 6 "Other Expenses" that are SPECIFIC to this {basic_details.industry} industry and {basic_details.company_size} company size.

        CRITICAL: Do NOT use generic terms like "Rent", "Utilities", "Salaries", "Insurance", "Marketing", "Bank Charges", 
        "Interest", "Depreciation", "Bad Debts", "Miscellaneous", "Office Supplies", "Professional Fees", or "Taxes".

        IMPORTANT RESTRICTIONS:
        - The following are EXISTING REVENUE TITLES and are provided ONLY for CONTEXT.
        - Use them strictly to understand the business model and cost structure.    
            • Existing Revenue Titles: {existing_revenue_titles}

        Instead, think of SPECIFIC expenses that a {basic_details.industry} company would have:
        - You must independently identify expense categories that are realistic, specialised, and naturally occurring in companies operating within the {basic_details.industry} industry.
        - Do NOT rely on predefined examples.
        - Do NOT generalise.
        - Focus on actual industry-specific operations, workflows, compliance needs, risks, facilities, and ecosystem interactions.
        
        Return ONLY a JSON array with Upto 6  objects:
        [
            {{"name": "Industry-Specific Expense 1", "description": "Specific to {basic_details.industry}", "growth_rates": [2,3,4,4,5], "market_trend": "rising"}},
            {{"name": "Industry-Specific Expense 2", "description": "Specific to {basic_details.industry}", "growth_rates": [1,2,2,3,3], "market_trend": "stable"}},
            {{"name": "Industry-Specific Expense 3", "description": "Specific to {basic_details.industry}", "growth_rates": [3,4,5,5,6], "market_trend": "rising"}},
            {{"name": "Industry-Specific Expense 4", "description": "Specific to {basic_details.industry}", "growth_rates": [2,2,3,3,4], "market_trend": "stable"}},
            {{"name": "Industry-Specific Expense 5", "description": "Specific to {basic_details.industry}", "growth_rates": [4,5,6,6,7], "market_trend": "rising"}},
            {{"name": "Industry-Specific Expense 6", "description": "Specific to {basic_details.industry}", "growth_rates": [1,1,2,2,3], "market_trend": "stable"}}
        ]

        REQUIREMENTS:
        - Upto 6 objects
        - Double quotes for all strings
        - Growth rates as numbers (including negative or zero growth, if any)
        - Market trend: "rising", "stable", or "declining"
        - NO generic terms — must be industry-specific
        - Return ONLY the JSON array
        """


# ============================================================================
# INTEREST EXPENSE PROMPTS
# ============================================================================
# Note: Interest expense doesn't have AI prompts for generation, only manual input


# ============================================================================
# INCOME BEFORE TAXES PROMPTS
# ============================================================================

def get_tax_rate_prompt(user_details):
    """
    Generate effective corporate tax rate using AI.
    """
    return f"""
        Give the effective corporate tax rate to be charged in P&L account for the business from USER BASIC DETAILS? Only give a percentage.
        
        User Business Details:
        - Industry: {user_details.industry}
        - Country: {user_details.country}
        - City: {user_details.city}
        - Company Size: {user_details.company_size}
        - Business Model: {user_details.business_model}
        
        Please provide only a percentage number (e.g., 25.5 or 30) without any additional text or explanation.
        """

def get_spelling_correction_prompt(data: dict) -> str:
    return f"""
            You are a spelling correction engine.

            STRICT RULES (DO NOT VIOLATE):
            - ONLY correct spelling mistakes
            - DO NOT rephrase or rewrite
            - DO NOT change meaning
            - DO NOT add or remove words
            - DO NOT change word order
            - DO NOT change casing unless required to fix spelling
            - DO NOT add explanations or comments
            - Output MUST be valid JSON only
            - Output keys MUST exactly match input keys
            - If a value is already correct, return it unchanged

            INPUT (JSON):
            {data}

            OUTPUT (JSON ONLY, NO TEXT):
            """
