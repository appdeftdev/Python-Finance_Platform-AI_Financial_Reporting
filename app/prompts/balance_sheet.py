from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Body
from app.models.models import PNLStatement, UserProgress, UserBasicDetails, RevenueStream, Return, COGS, OperatingExpenses, DepreciationNAmortisation, Skipped, OtherIncome, BalanceSheet, WorkingCapital, Inventory, InterestExpense, IncomeBeforeTaxes, CashFlowStatement, OtherExpense
from app.schemas.response_schemas import (
    REVENUE_SCHEMA_DESCRIPTION,
    RETURNS_SCHEMA_DESCRIPTION
)

from app.core.database import get_db



def get_generate_closing_inventory(basic_details,total_revenue,total_cogs, projections: int = None):
    return f"""  
    For the business from USER BASIC DETAILS and given that it has annual revenue of ${total_revenue} and COGS of ${total_cogs}, estimate a reasonable Closing Inventory value for {projections} years. Use common industry benchmarks for inventory turnover to calculate this and only give the closing inventory amount.

    User Details:
    - Industry: {basic_details.industry or 'Not specified'}
    - Company Size: {basic_details.company_size or 'Not specified'}
    - Business Model: {basic_details.business_model or 'Not specified'}
    - Projections: {projections} years

    Revenue Data: {total_revenue}
    COGS Data: {total_cogs}

    Please provide exactly {projections} closing inventory values as an array of numbers (e.g., [800, 704, 246, 389, 190]).

    """
def get_generate_recievables_dso_prompt(basic_details):
    return f"""
    You are a financial modeling expert. Based on the business details below, provide ONLY a single number representing the typical Days Sales Outstanding (DSO) in days for this type of business.

    Business Details:
    - Industry: {basic_details.industry or 'Not specified'}
    - Company Size: {basic_details.company_size or 'Not specified'}
    - Business Model: {basic_details.business_model or 'Not specified'}

    Provide ONLY a number between 1 and 365 (e.g., 30, 45, 60). Do not include any explanation or text.
    """


def get_generate_recievables_credit_sales(basic_details):
    return f"""
        You are a financial modeling expert. Based on the business details below, provide ONLY a single number representing the typical percentage of sales that are made on credit for this type of business.

        Business Details:
        - Industry: {basic_details.industry or 'Not specified'}
        - Company Size: {basic_details.company_size or 'Not specified'}
        - Business Model: {basic_details.business_model or 'Not specified'}

        Provide ONLY a number between 0 and 100 (e.g., 50, 75, 90). Do not include any explanation or text.
    
    """

def get_generate_payables_dpo_prompt(basic_details):
    return f"""
    Based on the following business details, provide a reasonable assumption for:
    Payables Days (Days Payable Outstanding - DPO).
    These should reflect typical credit terms and payment behavior in the relevant industry and location.

    Details:
    Industry/Sector: {basic_details.industry or 'Not specified'}
    Business Model: {basic_details.business_model or 'Not specified'}
    Company Size: {basic_details.company_size or 'Not specified'}
    City, Country: {basic_details.city or 'Not specified'}, {basic_details.country or 'Not specified'}

    Please provide only a number (e.g., 30, 45, 60) representing the DPO in days.
    
    """