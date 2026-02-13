from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Body
from app.models.models import PNLStatement, UserProgress, UserBasicDetails, RevenueStream, Return, COGS, OperatingExpenses, DepreciationNAmortisation, Skipped, OtherIncome, BalanceSheet, WorkingCapital, Inventory, InterestExpense, IncomeBeforeTaxes, CashFlowStatement, OtherExpense
from app.schemas.response_schemas import (
    REVENUE_SCHEMA_DESCRIPTION,
    RETURNS_SCHEMA_DESCRIPTION
)

from app.core.database import get_db


def get_terminal_growth_rate_prompt(basic_details):
    return f"""
        Based on the following business details, determine an appropriate long-term (terminal) growth rate assumption for terminal value calculation in a DCF valuation model.

        Company Details:
        - Industry: {basic_details.industry}
        - Country: {basic_details.country}
        - Company Size: {basic_details.company_size}
        - Business Model: {basic_details.business_model}

        Guidelines:
        - The growth rate must reflect long-term sustainable economic growth.
        - Consider industry maturity and long-run market saturation.
        - Change language to - Not exceed long-term nominal GDP growth of the country
        - The terminal growth rate must be conservative and stable.

        IMPORTANT:
        - Return ONLY a single numeric percentage value.

        Example outputs:
        3
        3.5
        4
"""



def get_wacc_prompt(basic_details):
    return f"""
        Based on the following business details, determine a typical weighted average cost of capital (WACC) suitable for valuation purposes.

        Company Details:
        - Industry: {basic_details.industry}
        - Country: {basic_details.country}
        - Company Size: {basic_details.company_size}
        - Business Model: {basic_details.business_model}

        Guidelines:
        - Assume the business is a private, operating company (not publicly listed).
        - Assume a reasonable, normalized debt–equity ratio typical for similar businesses in this industry and size category.
        - Consider typical cost of equity and cost of debt for similar businesses.
        - Account for industry risk, business volatility, operating leverage, and country risk.
        - The WACC should be realistic, conservative, and suitable for long-term DCF modeling.
        - The WACC should reasonably exceed long-term terminal growth assumptions.

        IMPORTANT:
        - Return ONLY a single numeric percentage value.
        - The output should reflect market-consistent assumptions for the specified industry, geography, and company profile. Avoid artificially constraining the result to a predefined range — determine the value logically based on the inputs.

        Example outputs:
        10
        12.5
        15
"""


def get_ai_insights_prompt(basic_details):

    return  f""" 
    You are a financial analyst explaining a business valuation to a non-finance business owner. Your goal is to clearly explain what their business is worth, why it is worth that amount, and what realistically influences its value over time. The explanation must feel specific to the user’s business, not generic or theoretical.

    Company Details:
    - Industry: {basic_details.industry}
    - Country: {basic_details.country}
    - Company Size: {basic_details.company_size}
    - Business Model: {basic_details.business_model}

    Valuation Inputs:
    - Estimated valuation
    - Valuation range (low–high)
    - Valuation approaches used: Relative valuation and Discounted Cash Flow
    - Revenue and EBITDA (Y1–Y5)
    - WACC and terminal growth assumptions

    Begin with a plain-English summary of the valuation outcome. Explain 2–3 key drivers by clearly linking cause to impact (for example: higher margins increase value because future profits scale faster). Highlight 1–2 meaningful risks or sensitivities that could change the valuation. Provide specific, realistic actions the user can take to improve business value over time. If some inputs are estimated or limited, briefly acknowledge uncertainty without using disclaimers.

    Use clear, business-friendly language. Speak directly to the user (“your business”). Be confident, neutral, and supportive. Do not mention formulas, models, or academic finance terminology. Avoid generic phrases like “optimize capital structure.”

    Keep the response between 100–140 words. Use short paragraphs or light bullet formatting. Do not include legal or advisory disclaimers.

    Structure the response using the following headings:

    Valuation Summary
    What’s driving your valuation
    What could change this value
    How you can improve it over time

    
    """

def get_ev_revenue_multiple_prompt(basic_details):

    return  f""" 
    You are a valuation analyst estimating an appropriate EV / Revenue multiple for a private business where profitability is limited, volatile, or still emerging. The goal is to produce a disciplined, downside-aware multiple that reflects how investors price future earning potential, not just revenue growth.

    Company Details:
    - Industry: {basic_details.industry}
    - Country: {basic_details.country}
    - Company Size: {basic_details.company_size}
    - Business Model: {basic_details.business_model}

    Financial Data:
    - Revenue, Gross Margin, and EBITDA (Y1–Y5)

    Instructions:
    - Anchor the analysis to private-market EV / Revenue benchmarks relevant to the company’s industry, geography, and size.
    - Adjust the multiple strictly based on fundamental drivers, including revenue growth sustainability, gross margin strength and scalability, operating leverage and reinvestment needs, overall business risk, and earnings predictability.
    - Automatically apply downward adjustment (multiple compression) if gross margins are weak, growth is slowing or volatile, or long-term profitability visibility is low.
    - Perform a logical cross-check to ensure that the implied EV / EBITDA multiple (assuming margins normalize over time) remains realistic and investor-consistent.
    - Return only a single numeric EV / Revenue multiple.

    
    """