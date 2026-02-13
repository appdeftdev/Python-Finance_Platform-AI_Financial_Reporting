from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.schemas.user import UserRegister, UserLogin, UserOut, UserBasicDetailsCreate, UserBasicDetailsOut, StandardResponse, ResetProgressRequest, SkipTopicRequest, UserBasicDetailsUpdate, CompanyUpdateRequest
from app.services.user_service import register_user, authenticate_user, create_user_basic_details, update_user_basic_details_progress
from app.models.models import Base, UserProgress, Return, RevenueStream, PNLStatement, COGS, OperatingExpenses, DepreciationNAmortisation, Skipped, OtherIncome, InterestExpense, IncomeBeforeTaxes, BalanceSheet, WorkingCapital, Inventory, BSRecords, CashFlowStatement, OtherExpense, Valuation
from app.core.database import get_db
from typing import Optional
from app.utils.utility import get_current_user, get_current_user_from_token, create_all_pnl_records, create_valuation_record, create_balance_sheet_records
from app.utils.response_utils import success_response, error_response, unauthorized_error, not_found_error, bad_request_error, bad_request_response, internal_server_error_response
from datetime import datetime
router = APIRouter()

@router.post('/register', response_model=StandardResponse)
def register(user: UserRegister, db: Session = Depends(get_db)):
    try:
        db_user = register_user(db, user.name, user.email, user.password)
        return success_response(
            message="User registered successfully",
            data={
                "id": db_user.id,
                "name": db_user.name,
                "email": db_user.email
            }
        )
    except HTTPException as e:
        # Handle specific HTTP exceptions (like duplicate user)
        if e.status_code == 400:
            return bad_request_response(
                message=e.detail
            )
        else:
            # Re-raise other HTTP exceptions to get proper status codes
            raise e
    except Exception as e:
        # For other exceptions, return 500 status code
        return internal_server_error_response(
            message=f"Registration failed: {str(e)}"
        )

@router.post('/login', response_model=StandardResponse)
def login(user: UserLogin, db: Session = Depends(get_db)):
    try:
        db_user, access_token, refresh_token = authenticate_user(db, user.email, user.password)
        if not db_user:
            unauthorized_error("Invalid credentials")
        
        return success_response(
            message="Login successful",
            data={
                "id": db_user.id,
                "name": db_user.name,
                "email": db_user.email,
                "access_token": access_token,
                "refresh_token": refresh_token
            }
        )
    except HTTPException:
        # Re-raise HTTP exceptions (like 401 for invalid credentials)
        raise
    except Exception as e:
        return error_response(
            message=f"Login failed: {str(e)}"
        )

@router.post('/basic-details', response_model=StandardResponse)
@router.post('/basic-details/', response_model=StandardResponse)
def create_basic_details(
    basic_details: UserBasicDetailsCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Get user ID from token (convert to int since token stores it as string)
        user_id = int(current_user["id"])
        basic_details_data = basic_details.dict()
        company_name = basic_details_data.get("company_name")

        if not company_name or not company_name.strip():
            basic_details_data["company_name"] = f"CMP_{user_id}"
        else:
            basic_details_data["company_name"] = company_name.strip()

        created_details = create_user_basic_details(db, user_id, basic_details_data)
        
        # Create all PNL records for the user

        # 1. Create PNL records
        pnl_records_result = create_all_pnl_records(current_user, db)

        # 2. Create Balance Sheet records
        try:
            balance_sheet_result = create_balance_sheet_records(user_id, db)
        except Exception as e:
            return error_response(
                message=f"Balance sheet failed: {str(e)}"
            )

        # 3. Create Valuation records
        try:
            valuation_result = create_valuation_record(user_id, db)
        except Exception as e:
            return error_response(
                message=f"Valuation failed: {str(e)}"
            )

        # try:
        #     pnl_records_result = create_all_pnl_records(current_user, db)
        #     balance_sheet_result = create_balance_sheet_records(user_id, db)
        #     valuation_result = create_valuation_record(user_id, db)
        # except HTTPException as pnl_error:
        #     return error_response(
        #         message=f"Basic details exist, but valuation failed: {pnl_error.detail}"
        #     )
        # except Exception as pnl_error:
        #     return error_response(
        #         message=f"Basic details exist, but valuation failed: {str(pnl_error)}"
        #     )
        
        return success_response(
            message="Basic details created successfully with AI-generated financial details and PNL records initialized",
            data={
                "basic_details": {
                    "id": created_details.id,
                    "user_id": created_details.user_id,
                    "company_name": created_details.company_name,
                    "industry": created_details.industry,
                    "city": created_details.city,
                    "country": created_details.country,
                    "company_size": created_details.company_size,
                    "competitors": created_details.competitors,
                    "business_model": created_details.business_model,
                    "fin_year": created_details.fin_year,
                    "projections": created_details.projections,
                    "currency": created_details.currency,
                    "base_year": created_details.base_year
                },
                "pnl_records": pnl_records_result,
                "balance_sheet":balance_sheet_result,
                "valuation":valuation_result 
            }
        )
    except HTTPException as e:
        # Check if this is the "already exist" error
        if e.detail == "Basic details already exist for this user":
            # Get the existing record
            from app.models.models import UserBasicDetails
            existing_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
            
            # Try to create PNL records even if basic details already exist
            try:
                pnl_records_result = create_all_pnl_records(current_user, db)
                balance_sheet_result = create_balance_sheet_records(user_id, db)
                valuation_result = create_valuation_record(existing_details.user_id, db)
                pnl_message = "PNL records processed"
            except HTTPException as pnl_error:
                return error_response(
                    message=f"Basic details exist, but valuation failed: {pnl_error.detail}"
                )
            except Exception as pnl_error:
                return error_response(
                    message=f"Basic details exist, but valuation failed: {str(pnl_error)}"
                )
            
            return success_response(
                message=f"{e.detail}. {pnl_message}.",
                data={
                    "basic_details": {
                        "id": existing_details.id,
                        "user_id": existing_details.user_id,
                        "company_name": existing_details.company_name,
                        "industry": existing_details.industry,
                        "city": existing_details.city,
                        "country": existing_details.country,
                        "company_size": existing_details.company_size,
                        "competitors": existing_details.competitors,
                        "business_model": existing_details.business_model,
                        "fin_year": existing_details.fin_year,
                        "projections": existing_details.projections,
                        "currency": existing_details.currency,
                        "base_year": existing_details.base_year
                    },
                    "pnl_records": pnl_records_result,
                    "balance_sheet":balance_sheet_result,
                    "valuation":valuation_result    
                }
            )
        else:
            return error_response(
                message=e.detail
            )
    except Exception as e:
        return error_response(
            message=f"Internal server error: {str(e)}"
        ) 

@router.get('/basic-details', response_model=StandardResponse)
@router.get('/basic-details/', response_model=StandardResponse)
def get_basic_details(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user_id = int(current_user["id"])
        
        # Get the existing record
        from app.models.models import UserBasicDetails
        existing_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        
        if not existing_details:
            not_found_error("Basic details not found for this user")

        business_model = existing_details.business_model

        if isinstance(business_model, list):
            business_model = business_model
        elif isinstance(business_model, str):
            business_model = [
                item.strip()
                for item in business_model.split(",")
                if item.strip()
            ]
        else:
            business_model = []
        
        return success_response(
            message="Basic details retrieved successfully",
            data={
                "id": existing_details.id,
                "user_id": existing_details.user_id,
                "company_name": existing_details.company_name,
                "industry": existing_details.industry,
                "city": existing_details.city,
                "country": existing_details.country,
                "company_size": existing_details.company_size,
                "competitors": existing_details.competitors,
                "business_model": business_model,
                "fin_year": existing_details.fin_year,
                "projections": existing_details.projections,
                "currency": existing_details.currency,
                "base_year": existing_details.base_year
            }
        )
    except Exception as e:
        return error_response(
            message=f"Failed to retrieve basic details: {str(e)}"
        )

@router.put('/basic-details/company', response_model=StandardResponse)
@router.put('/basic-details/company/', response_model=StandardResponse)
def update_company_and_competitors(
    payload: CompanyUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user_id = int(current_user["id"])

        from app.models.models import UserBasicDetails

        basic_details = (
            db.query(UserBasicDetails)
            .filter(UserBasicDetails.user_id == user_id)
            .first()
        )

        if not basic_details:
            return not_found_response(
                message="Basic details not found for this user",
                data=None
            )

        # Update company name
        if payload.company_name is not None:
            if payload.company_name.strip():
                basic_details.company_name = payload.company_name.strip()
            else:
                basic_details.company_name = f"CMP_{user_id}"

        # Update competitors
        if payload.competitors is not None:
            if isinstance(payload.competitors, list):
                basic_details.competitors = ", ".join(payload.competitors)
            else:
                basic_details.competitors = payload.competitors

        db.commit()
        db.refresh(basic_details)

        return success_response(
            message="Company name and competitors updated successfully",
            data={
                "id": basic_details.id,
                "user_id": basic_details.user_id,
                "company_name": basic_details.company_name,
                "competitors": basic_details.competitors
            }
        )

    except Exception as e:
        return error_response(
            message=f"Internal server error: {str(e)}"
        )


@router.post('/reset-progress', response_model=StandardResponse)
def reset_user_progress(
    request: ResetProgressRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user_id = int(current_user["id"])
        topic = request.topic.lower()
        subject = request.subject.lower()
        
        # Get user progress
        user_progress = db.query(UserProgress).filter(UserProgress.user_id == user_id).first()
        if not user_progress:
            not_found_error("User progress not found")
        
        # Get PNL statement for this user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        
        # Get Balance sheet for this user
        balance_sheet = db.query(BalanceSheet).filter(BalanceSheet.user_id == user_id).first()

        valuation = db.query(Valuation).filter(Valuation.user_id == user_id).first()

        
        # Reset based on topic and subject parameters
        if topic == "all" and subject == "all":
            # Reset all progress stages
            user_progress.pnl_statements = False
            user_progress.balance_sheet = False
            user_progress.valuation = False
            user_progress.charts_n_insights = False
            if balance_sheet:
                balance_sheet.cash_flow_statement = False

            
            # Clear all PNL-related data but keep records
            if pnl_statement:
                # Reset PNL statement flags
                pnl_statement.revenue = False
                pnl_statement.cogs = False
                pnl_statement.returns = False
                pnl_statement.operating_expenses = False
                pnl_statement.depreciation_n_amortisation = False
                pnl_statement.other_income = False
                pnl_statement.other_expense = False
                pnl_statement.interest_expense = False
                pnl_statement.income_before_taxes = False
                
                # Clear revenue streams data but keep records
                revenue_streams = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).all()
                for revenue_stream in revenue_streams:
                    revenue_stream.data_json = None
                    revenue_stream.projected_titles = None
                    revenue_stream.selected_titles = None
                    
                    # Clear returns data but keep records
                    returns = db.query(Return).filter(Return.pnl_id == pnl_statement.id).all()
                    for return_item in returns:
                        return_item.data_json = None
                        return_item.projected_titles = None
                
                # Clear COGS data but keep records
                cogs_items = db.query(COGS).filter(COGS.pnl_id == pnl_statement.id).all()
                for cogs_item in cogs_items:
                    cogs_item.data_json = None
                    cogs_item.projected_titles = None
                    cogs_item.selected_titles = None
                
                # Clear operating expenses data but keep records
                operating_expenses_items = db.query(OperatingExpenses).filter(OperatingExpenses.pnl_id == pnl_statement.id).all()
                for expense_item in operating_expenses_items:
                    expense_item.data_json = None
                    expense_item.projected_titles = None
                    expense_item.selected_titles = None
                
                # Clear depreciation and amortisation data but keep records
                depreciation_items = db.query(DepreciationNAmortisation).filter(DepreciationNAmortisation.pnl_id == pnl_statement.id).all()
                for dep_item in depreciation_items:
                    dep_item.data_json = None
                    dep_item.assets_input = None
                    dep_item.projected_titles = None
                    dep_item.selected_titles = None
                
                # Clear other income data but keep records
                other_income_items = db.query(OtherIncome).filter(OtherIncome.pnl_id == pnl_statement.id).all()
                for other_income_item in other_income_items:
                    other_income_item.data_json = None
                    other_income_item.projected_titles = None
                    other_income_item.selected_titles = None

                other_expense_items = db.query(OtherExpense).filter(OtherExpense.pnl_id == pnl_statement.id).all()
                for other_expense_item in other_expense_items:
                    other_expense_item.data_json = None
                    other_expense_item.projected_titles = None
                    other_expense_item.selected_titles = None
                
                # Clear interest expense data but keep records
                interest_expense_items = db.query(InterestExpense).filter(InterestExpense.pnl_id == pnl_statement.id).all()
                for interest_expense_item in interest_expense_items:
                    interest_expense_item.data_json = None
                
                # Clear income before taxes data but keep records
                income_before_taxes_items = db.query(IncomeBeforeTaxes).filter(IncomeBeforeTaxes.pnl_id == pnl_statement.id).all()
                for income_before_taxes_item in income_before_taxes_items:
                    income_before_taxes_item.data_json = None
                    income_before_taxes_item.tax = ""

                valuation = db.query(Valuation).filter(Valuation.user_id == user_id).first()
                if valuation:
                    valuation.data_json = None
                    valuation.projected_titles = None
                    valuation.selected_titles = None
                
                # Reset skipped flags
                skipped_record = db.query(Skipped).filter(Skipped.user_id == user_id).first()
                if skipped_record:
                    skipped_record.returns = False
                    skipped_record.depreciation_and_amortisation = False
                    skipped_record.interest_expense = False
            
            # Clear balance sheet data but keep records
            if balance_sheet:
                # Reset balance sheet flags
                balance_sheet.working_capital = False
                balance_sheet.inventory = False
                balance_sheet.bs_records = False
                
                # Clear working capital data but keep records
                working_capital_items = db.query(WorkingCapital).filter(WorkingCapital.balance_sheet_id == balance_sheet.id).all()
                for working_capital_item in working_capital_items:
                    working_capital_item.data_json = None
                
                # Clear inventory data but keep records
                inventory_items = db.query(Inventory).filter(Inventory.balance_sheet_id == balance_sheet.id).all()
                for inventory_item in inventory_items:
                    inventory_item.data_json = None
                
                # Clear bs_records data but keep records
                bs_records_items = db.query(BSRecords).filter(BSRecords.balance_sheet_id == balance_sheet.id).all()
                for bs_records_item in bs_records_items:
                    bs_records_item.data_json = None
                
                # Clear cashflow data but keep records
                cashflow_items = db.query(CashFlowStatement).filter(CashFlowStatement.balance_sheet_id == balance_sheet.id).all()
                for cashflow_item in cashflow_items:
                    cashflow_item.data_json = None

            message = "All user progress has been reset - data cleared but records preserved"
            
        elif topic == "pnl" and subject == "all":
            # Reset all PNL-related progress
            user_progress.pnl_statements = False
            
            # Clear all PNL-related data but keep records
            if pnl_statement:
                pnl_statement.revenue = False
                pnl_statement.cogs = False
                pnl_statement.returns = False
                pnl_statement.operating_expenses = False
                pnl_statement.depreciation_n_amortisation = False
                pnl_statement.other_income = False
                pnl_statement.other_expense = False
                pnl_statement.interest_expense = False
                pnl_statement.income_before_taxes = False
                
                # Clear all child data
                revenue_streams = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).all()
                for revenue_stream in revenue_streams:
                    revenue_stream.data_json = None
                    revenue_stream.projected_titles = None
                    revenue_stream.selected_titles = None
                    
                    returns = db.query(Return).filter(Return.pnl_id == pnl_statement.id).all()
                    for return_item in returns:
                        return_item.data_json = None
                        return_item.projected_titles = None
                
                cogs_items = db.query(COGS).filter(COGS.pnl_id == pnl_statement.id).all()
                for cogs_item in cogs_items:
                    cogs_item.data_json = None
                    cogs_item.projected_titles = None
                    cogs_item.selected_titles = None
                
                operating_expenses_items = db.query(OperatingExpenses).filter(OperatingExpenses.pnl_id == pnl_statement.id).all()
                for expense_item in operating_expenses_items:
                    expense_item.data_json = None
                    expense_item.projected_titles = None
                    expense_item.selected_titles = None
                
                # Clear depreciation and amortisation data
                depreciation_items = db.query(DepreciationNAmortisation).filter(DepreciationNAmortisation.pnl_id == pnl_statement.id).all()
                for dep_item in depreciation_items:
                    dep_item.data_json = None
                    dep_item.assets_input = None
                    dep_item.projected_titles = None
                    dep_item.selected_titles = None
                
                # Clear other income data
                other_income_items = db.query(OtherIncome).filter(OtherIncome.pnl_id == pnl_statement.id).all()
                for other_income_item in other_income_items:
                    other_income_item.data_json = None
                    other_income_item.projected_titles = None
                    other_income_item.selected_titles = None
                
                other_expense_items = db.query(OtherExpense).filter(OtherExpense.pnl_id == pnl_statement.id).all()
                for other_expense_item in other_expense_items:
                    other_expense_item.data_json = None
                    other_expense_item.projected_titles = None
                    other_expense_item.selected_titles = None
                
                # Clear interest expense data
                interest_expense_items = db.query(InterestExpense).filter(InterestExpense.pnl_id == pnl_statement.id).all()
                for interest_expense_item in interest_expense_items:
                    interest_expense_item.data_json = None
                
                # Clear income before taxes data
                income_before_taxes_items = db.query(IncomeBeforeTaxes).filter(IncomeBeforeTaxes.pnl_id == pnl_statement.id).all()
                for income_before_taxes_item in income_before_taxes_items:
                    income_before_taxes_item.data_json = None
                    income_before_taxes_item.tax = ""
                
                # Reset skipped flags
                skipped_record = db.query(Skipped).filter(Skipped.user_id == user_id).first()
                if skipped_record:
                    skipped_record.returns = False
                    skipped_record.depreciation_and_amortisation = False
                    skipped_record.interest_expense = False
            
            message = "All PNL-related progress has been reset - data cleared but records preserved"
            
        elif topic == "pnl" and subject == "revenue":
            # Reset only revenue progress
            
            # Clear revenue-related data but keep records
            if pnl_statement:
                pnl_statement.revenue = False
                
                revenue_streams = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).all()
                for revenue_stream in revenue_streams:
                    revenue_stream.data_json = None
                    revenue_stream.projected_titles = None
                    revenue_stream.selected_titles = None
                    
                    # Also clear returns data since it's related to revenue
                    returns = db.query(Return).filter(Return.pnl_id == pnl_statement.id).all()
                    for return_item in returns:
                        return_item.data_json = None
                        return_item.projected_titles = None
            
            message = "Revenue progress has been reset - data cleared but records preserved"
            
        elif topic == "pnl" and subject == "returns":
            # Reset only returns progress
            
            # Clear returns-related data but keep records
            if pnl_statement:
                pnl_statement.returns = False
                
                revenue_streams = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).all()
                for revenue_stream in revenue_streams:
                    returns = db.query(Return).filter(Return.pnl_id == pnl_statement.id).all()
                    for return_item in returns:
                        return_item.data_json = None
                        return_item.projected_titles = None
            
            message = "Returns progress has been reset - data cleared but records preserved"
            
        elif topic == "pnl" and subject == "cogs":
            # Reset only COGS progress
            
            # Clear COGS-related data but keep records
            if pnl_statement:
                pnl_statement.cogs = False
                
                cogs_items = db.query(COGS).filter(COGS.pnl_id == pnl_statement.id).all()
                for cogs_item in cogs_items:
                    cogs_item.data_json = None
                    cogs_item.projected_titles = None
                    cogs_item.selected_titles = None
            
            message = "COGS progress has been reset - data cleared but records preserved"
            
        elif topic == "pnl" and subject == "expenses":
            # Reset only operating expenses progress
            
            # Clear operating expenses-related data but keep records
            if pnl_statement:
                pnl_statement.operating_expenses = False
                
                operating_expenses_items = db.query(OperatingExpenses).filter(OperatingExpenses.pnl_id == pnl_statement.id).all()
                for expense_item in operating_expenses_items:
                    expense_item.data_json = None
                    expense_item.projected_titles = None
                    expense_item.selected_titles = None
            
            message = "Operating expenses progress has been reset - data cleared but records preserved"
            
        elif topic == "pnl" and subject == "depreciation_and_amortisation":
            # Reset only depreciation and amortisation progress
            
            # Clear depreciation and amortisation related data but keep records
            if pnl_statement:
                pnl_statement.depreciation_n_amortisation = False
                
                depreciation_items = db.query(DepreciationNAmortisation).filter(DepreciationNAmortisation.pnl_id == pnl_statement.id).all()
                for dep_item in depreciation_items:
                    dep_item.data_json = None
                    dep_item.assets_input = None
                    dep_item.projected_titles = None
                    dep_item.selected_titles = None
                
                # Reset skipped flag for depreciation and amortisation
                skipped_record = db.query(Skipped).filter(Skipped.user_id == user_id).first()
                if skipped_record:
                    skipped_record.depreciation_and_amortisation = False
            
            message = "Depreciation and Amortisation progress has been reset - data cleared but records preserved"
            
        elif topic == "pnl" and subject == "other_income":
            # Reset only other income progress
            
            # Clear other income related data but keep records
            if pnl_statement:
                pnl_statement.other_income = False
                
                other_income_items = db.query(OtherIncome).filter(OtherIncome.pnl_id == pnl_statement.id).all()
                for other_income_item in other_income_items:
                    other_income_item.data_json = None
                    other_income_item.projected_titles = None
                    other_income_item.selected_titles = None
            
            message = "Other income progress has been reset - data cleared but records preserved"

        elif topic == "pnl" and subject == "other_expense":
            # Reset only other income progress
            
            # Clear other income related data but keep records
            if pnl_statement:
                pnl_statement.other_expense = False
                
                other_expense_items = db.query(OtherExpense).filter(OtherExpense.pnl_id == pnl_statement.id).all()
                for other_expense_item in other_expense_items:
                    other_expense_item.data_json = None
                    other_expense_item.projected_titles = None
                    other_expense_item.selected_titles = None
            
            message = "Other expense progress has been reset - data cleared but records preserved"

        elif topic == "pnl" and subject == "interest_expense":
            # Reset only interest expense progress
            
            # Clear interest expense-related data but keep records
            if pnl_statement:
                pnl_statement.interest_expense = False
                
                interest_expense_items = db.query(InterestExpense).filter(InterestExpense.pnl_id == pnl_statement.id).all()
                for interest_expense_item in interest_expense_items:
                    interest_expense_item.data_json = None
            
            message = "Interest expense progress has been reset - data cleared but records preserved"
            
        elif topic == "pnl" and subject == "income_before_taxes":
            # Reset only income before taxes progress
            
            # Clear income before taxes-related data but keep records
            if pnl_statement:
                pnl_statement.income_before_taxes = False
                
                income_before_taxes_items = db.query(IncomeBeforeTaxes).filter(IncomeBeforeTaxes.pnl_id == pnl_statement.id).all()
                for income_before_taxes_item in income_before_taxes_items:
                    income_before_taxes_item.data_json = None
            
            message = "Income before taxes progress has been reset - data cleared but records preserved"
            
        elif topic == "balance sheet" and subject == "all":
            # Reset only balance sheet progress
            user_progress.balance_sheet = False
            
            # Clear balance sheet data but keep records
            if balance_sheet:
                balance_sheet.working_capital = False
                balance_sheet.inventory = False
                balance_sheet.bs_records = False
                
                # Clear working capital data but keep records
                working_capital_items = db.query(WorkingCapital).filter(WorkingCapital.balance_sheet_id == balance_sheet.id).all()
                for working_capital_item in working_capital_items:
                    working_capital_item.data_json = None
                
                # Clear inventory data but keep records
                inventory_items = db.query(Inventory).filter(Inventory.balance_sheet_id == balance_sheet.id).all()
                for inventory_item in inventory_items:
                    inventory_item.data_json = None
                
                # Clear bs_records data but keep records
                bs_records_items = db.query(BSRecords).filter(BSRecords.balance_sheet_id == balance_sheet.id).all()
                for bs_records_item in bs_records_items:
                    bs_records_item.data_json = None
            
            message = "Balance sheet progress has been reset - data cleared but records preserved"
            
        elif topic == "balance sheet" and subject == "working_capital":
            # Reset only working capital progress
            
            # Clear working capital data but keep records
            if balance_sheet:
                balance_sheet.working_capital = False
                
                working_capital_items = db.query(WorkingCapital).filter(WorkingCapital.balance_sheet_id == balance_sheet.id).all()
                for working_capital_item in working_capital_items:
                    working_capital_item.data_json = None
            
            message = "Working capital progress has been reset - data cleared but records preserved"
            
        elif topic == "balance sheet" and subject == "inventory":
            # Reset only inventory progress
            
            # Clear inventory data but keep records
            if balance_sheet:
                balance_sheet.inventory = False
                
                inventory_items = db.query(Inventory).filter(Inventory.balance_sheet_id == balance_sheet.id).all()
                for inventory_item in inventory_items:
                    inventory_item.data_json = None
            
            message = "Inventory progress has been reset - data cleared but records preserved"
            
        elif topic == "balance sheet" and subject == "bs_records":
            # Reset only bs_records progress
            
            # Clear bs_records data but keep records
            if balance_sheet:
                balance_sheet.bs_records = False
                
                bs_records_items = db.query(BSRecords).filter(BSRecords.balance_sheet_id == balance_sheet.id).all()
                for bs_records_item in bs_records_items:
                    bs_records_item.data_json = None
            
            message = "BS Records progress has been reset - data cleared but records preserved"
            
        elif topic == "balance sheet" and subject == "cash flow":
            # Reset only cash flow progress
            if balance_sheet:
                balance_sheet.cash_flow_statement = False

            
            # Clear cash flow data but keep records
            if balance_sheet:
                cashflow_items = db.query(CashFlowStatement).filter(CashFlowStatement.balance_sheet_id == balance_sheet.id).all()
                for cashflow_item in cashflow_items:
                    cashflow_item.data_json = None

            message = "Cash flow progress has been reset - data cleared but records preserved"
            
        else:
            return bad_request_error(f"Invalid topic/subject combination: topic='{topic}', subject='{subject}'. Valid combinations are: topic='all' subject='all', topic='pnl' subject='all/revenue/returns/cogs/expenses/depreciation_and_amortisation/other_income/interest_expense/income_before_taxes', topic='balance sheet' subject='all/working_capital/inventory/bs_records/cash flow'")
        
        db.commit()
        
        # Prepare response data based on topic
        response_data = {
            "user_id": user_id,
            "topic": topic,
            "subject": subject,
            "progress": {
                "pnl_statements": user_progress.pnl_statements,
                "balance_sheet": user_progress.balance_sheet,
                "cash_flow_statement": balance_sheet.cash_flow_statement if balance_sheet else False,
                "valuation": user_progress.valuation,
                "charts_n_insights": user_progress.charts_n_insights,
            }
        }
        
        # Add PnL statement details if topic is pnl and pnl_statement exists
        if topic == "pnl" and pnl_statement:
            response_data["pnl_details"] = {
                "revenue": pnl_statement.revenue,
                "cogs": pnl_statement.cogs,
                "returns": pnl_statement.returns,
                "operating_expenses": pnl_statement.operating_expenses,
                "depreciation_and_amortisation": pnl_statement.depreciation_n_amortisation,
                "other_income": pnl_statement.other_income,
                "other_expense": pnl_statement.other_expense,
                "interest_expense": pnl_statement.interest_expense,
                "income_before_taxes": pnl_statement.income_before_taxes
            }
            
            # Add skipped details if skipped record exists
            skipped_record = db.query(Skipped).filter(Skipped.user_id == user_id).first()
            if skipped_record:
                response_data["skipped_details"] = {
                    "returns": skipped_record.returns,
                    "depreciation_and_amortisation": skipped_record.depreciation_and_amortisation,
                    "interest_expense": skipped_record.interest_expense
                }
        
        # Add Balance sheet details if topic is balance sheet and balance_sheet exists
        if topic == "balance sheet" and balance_sheet:
            response_data["balance_sheet_details"] = {
                "working_capital": balance_sheet.working_capital,
                "inventory": balance_sheet.inventory,
                "bs_records": balance_sheet.bs_records,
                "cash_flow_statement": balance_sheet.cash_flow_statement if balance_sheet else False,

            }
        
        return success_response(
            message=message,
            data=response_data
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset progress: {str(e)}"
        )


@router.post('/skip-topic', response_model=StandardResponse)
def skip_topic(
    request: SkipTopicRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark a topic as skipped for the user
    """
    try:
        user_id = int(current_user["id"])
        topic = request.topic.lower()
        
        # Get or create skipped record
        skipped_record = db.query(Skipped).filter(Skipped.user_id == user_id).first()
        
        if not skipped_record:
            # Create new skipped record
            skipped_record = Skipped(
                user_id=user_id,
                returns=False,
                other_income=False,
                other_expense=False,
                depreciation_and_amortisation=False,
                interest_expense=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(skipped_record)
        
        # Update the specific topic to skipped
        if topic == "returns":
            skipped_record.returns = True
        elif topic == "other_income":
            skipped_record.other_income = True
        elif topic == "other_expense":
            skipped_record.other_expense = True
        elif topic == "depreciation_and_amortisation":
            skipped_record.depreciation_and_amortisation = True
        elif topic == "interest_expense":
            skipped_record.interest_expense = True
        else:
            return bad_request_error(f"Invalid topic: '{topic}'. Valid topics are: returns, other_income, depreciation_and_amortisation, interest_expense")
        
        skipped_record.updated_at = datetime.utcnow()
        db.commit()
        
        return success_response(
            message=f"Topic '{topic}' marked as skipped successfully",
            data={
                "user_id": user_id,
                "topic": topic,
                "skipped": True
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to skip topic: {str(e)}"
        )


@router.post('/unskip-topic', response_model=StandardResponse)
def unskip_topic(
    request: SkipTopicRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark a topic as unskipped for the user
    """
    try:
        user_id = int(current_user["id"])
        topic = request.topic.lower()
        
        # Get skipped record
        skipped_record = db.query(Skipped).filter(Skipped.user_id == user_id).first()
        
        if not skipped_record:
            return not_found_error("No skipped topics found for this user")
        
        # Update the specific topic to unskipped
        if topic == "returns":
            skipped_record.returns = False
        elif topic == "other_income":
            skipped_record.other_income = False
        elif topic == "other_expense":
            skipped_record.other_expense = False
        elif topic == "depreciation_and_amortisation":
            skipped_record.depreciation_and_amortisation = False
        elif topic == "interest_expense":
            skipped_record.interest_expense = False
        else:
            return bad_request_error(f"Invalid topic: '{topic}'. Valid topics are: returns, other_income, depreciation_and_amortisation, interest_expense")
        
        skipped_record.updated_at = datetime.utcnow()
        db.commit()
        
        return success_response(
            message=f"Topic '{topic}' marked as unskipped successfully",
            data={
                "user_id": user_id,
                "topic": topic,
                "skipped": False
            }
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unskip topic: {str(e)}"
        ) 


