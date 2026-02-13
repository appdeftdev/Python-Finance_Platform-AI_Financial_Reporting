import logging
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.schemas.pnl import RevenueStreamCreate, RevenueStreamOut, StandardResponse, ReturnCreate, ReturnsSaveRequest, CogsSaveRequest, BaseYearRequest, BaseYearResponse, BaseYearGetResponse, InterestExpenseSaveRequest, InterestExpenseSaveResponse, IncomeBeforeTaxesSaveRequest, IncomeBeforeTaxesSaveResponse, ConceptRecordsRequest
from app.services.pnl_service import create_revenue_stream, update_or_create_revenue_stream, update_revenue_stream_by_id, ensure_pnl_stage_records_exist, update_return_by_id, update_cogs_by_id, update_operating_expenses_by_id, set_base_year, get_base_year, save_interest_expense, get_interest_expense, generate_tax_rate, save_income_before_taxes, get_income_before_taxes
from app.core.database import get_db
from app.utils.utility import get_current_user, get_topic_record_id
from app.utils.response_utils import success_response, error_response, not_found_error, success_response_with_status, error_response_with_status, not_found_response, bad_request_response, internal_server_error_response
from app.models.models import PNLStatement, UserProgress, UserBasicDetails, RevenueStream, Return, COGS, OperatingExpenses, DepreciationNAmortisation, Skipped, OtherIncome, BalanceSheet, WorkingCapital, Inventory, InterestExpense, IncomeBeforeTaxes, CashFlowStatement, OtherExpense
from app.utils.openai_client import get_openai_completion
from app.services.user_service import generate_terminal_growth_rate_with_ai, generate_wacc_with_ai
from typing import Optional
import json
from datetime import datetime

router = APIRouter()

logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

@router.post('/terminal-growth-rate', response_model=StandardResponse)
def generate_terminal_growth_rate(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user_id = int(current_user["id"])
        result = generate_terminal_growth_rate_with_ai(db, user_id)
        return StandardResponse(
            success=result["success"],
            message=result["message"],
            data={
                "terminal_growth_rate": result["terminal_growth_rate"]
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        return error_response(
            message=f"Failed to generate terminal growth rate: {str(e)}",
            data=None
        )

@router.post('/generate-wacc', response_model=StandardResponse)
def generate_wacc(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user_id = int(current_user["id"])
        result = generate_wacc_with_ai(db, user_id)
        return StandardResponse(
            success=result["success"],
            message=result["message"],
            data={
                "wacc": result["wacc"]
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        return error_response(
            message=f"Failed to generate WACC: {str(e)}",
            data=None
        )
