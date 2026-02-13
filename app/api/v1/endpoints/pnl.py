import logging
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.schemas.pnl import RevenueStreamCreate, RevenueStreamOut, StandardResponse, ReturnCreate, ReturnsSaveRequest, CogsSaveRequest, BaseYearRequest, BaseYearResponse, BaseYearGetResponse, InterestExpenseSaveRequest, InterestExpenseSaveResponse, IncomeBeforeTaxesSaveRequest, IncomeBeforeTaxesSaveResponse, ConceptRecordsRequest
from app.services.pnl_service import create_revenue_stream, update_or_create_revenue_stream, update_revenue_stream_by_id, ensure_pnl_stage_records_exist, update_return_by_id, update_cogs_by_id, update_operating_expenses_by_id, set_base_year, get_base_year, save_interest_expense, get_interest_expense, generate_tax_rate, save_income_before_taxes, get_income_before_taxes
from app.core.database import get_db
from app.utils.utility import get_current_user, get_topic_record_id
from app.utils.response_utils import success_response, error_response, not_found_error, success_response_with_status, error_response_with_status, not_found_response, bad_request_response, internal_server_error_response
from app.models.models import PNLStatement, UserProgress, UserBasicDetails, RevenueStream, Return, COGS, OperatingExpenses, DepreciationNAmortisation, Skipped, OtherIncome, BalanceSheet, WorkingCapital, Inventory, InterestExpense, IncomeBeforeTaxes, CashFlowStatement, OtherExpense, Valuation
from app.utils.openai_client import get_openai_completion
from typing import Optional
import json
from datetime import datetime

router = APIRouter()

# Set up logging to app.log (if not already set)
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

@router.post('/revenue-save', response_model=StandardResponse)
def save_revenue(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing revenue stream by revenue_id. Supports updating all fields, including product as a list (multi-product) and multi-year data.
    """
    try:
        user_id = int(current_user["id"])
        # Get revenue_id using get_topic_record_id function
        revenue_id = get_topic_record_id("pnl", "revenue", current_user, db)
        
        # Get user details for validation
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return not_found_response(
                message="User basic details not found",
                data=None
            )
        
        # Validate the data structure manually (simplified validation)
        data_json = data.get("data_json", {})
        if not data_json or not isinstance(data_json, dict):
            return StandardResponse(
                success=False,
                message="data_json is required and must be a dictionary",
                data=None
            )
        
        products = data_json.get("data", {}).get("products", [])
        if not products or not isinstance(products, list):
            return StandardResponse(
                success=False,
                message="data_json.data.products is required and must be a list",
                data=None
            )
        
        # Validate each product has required fields
        for i, product in enumerate(products):
            if not isinstance(product, dict):
                return StandardResponse(
                    success=False,
                    message=f"Product {i} must be a dictionary",
                    data=None
                )
            
            if "name" not in product or "revenue" not in product:
                return StandardResponse(
                    success=False,
                    message=f"Product {i} must have 'name' and 'revenue' fields",
                    data=None
                )
            
            if not isinstance(product["revenue"], list):
                return StandardResponse(
                    success=False,
                    message=f"Product {i} revenue must be a list",
                    data=None
                )
            
            # Validate month_1 field if present
            if "month_1" in product and product["month_1"] is not None:
                if not isinstance(product["month_1"], (int, float)):
                    return StandardResponse(
                        success=False,
                        message=f"Product {i} month_1 must be a number",
                    data=None
                )
        
        # Update revenue stream by id with validated data
        saved_revenue = update_revenue_stream_by_id(db, revenue_id, data)
        
        # Return clean response without extra fields
        return success_response_with_status(
            message="Revenue data saved successfully",
            data={
                "revenue_id": revenue_id,
                "data_json": {
                    "data": {
                        "years": data_json.get("data", {}).get("years"),
                        "products": products,
                        "total_revenue": data_json.get("data", {}).get("total_revenue")
                    }
                }
            },
            status_code=200
        )
        
    except HTTPException as e:
        return error_response_with_status(
            message=e.detail,
            data=None,
            status_code=e.status_code
        )
    except Exception as e:
        return internal_server_error_response(
            message=f"Internal server error: {str(e)}",
            data=None
        ) 


@router.post('/cogs-titles-manual', response_model=StandardResponse)
def add_manual_cogs_product(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a manually provided product to COGS suggestions with AI-calculated growth rate.
    This endpoint appends the new product to existing projected_titles in the database.
    """
    try:
        user_id = int(current_user["id"])
        
        # Extract product name from request
        product_name = data.get("product_name")
        if not product_name:
            return bad_request_response(
                message="Product name is required",
                data=None
            )
        
        # Get user basic details for context
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return not_found_response(
                message="User basic details not found. Please complete your basic details first.",
                data=None
            )
        
        # Get or create COGS record for this user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
    
        # Get existing COGS record
        cogs_record = db.query(COGS).filter(COGS.pnl_id == pnl_statement.id).first()
        if not cogs_record:
            return not_found_response(
                message="COGS record not found. Please generate COGS suggestions first.",
                data=None
            )
        
        # Import the service function
        from app.services.user_service import calculate_cogs_product_growth_rate_with_ai
        
        # Calculate growth rates using AI (preserves exact product name)
        try:
            growth_data = calculate_cogs_product_growth_rate_with_ai(product_name, user_details)
        except Exception as e:
            logging.error(f"AI service failed for COGS product '{product_name}': {str(e)}")
            return internal_server_error_response(
                message=f"Failed to add manual COGS product: Unable to analyze product growth rates. Please check your OpenAI API configuration and try again.",
                data=None
            )
        
        # Create new product suggestion (keeping exact product name)
        new_product = {
            "name": product_name,  # Keep exact name as provided by user
            "percentage_of_revenue": growth_data["percentage_of_revenue"],
            "confidence": growth_data["confidence"],
            "market_trend": growth_data["market_trend"]
        }
        
        # Get existing suggestions
        existing_suggestions = cogs_record.projected_titles or []
        
        # Check if product already exists (case-insensitive)
        existing_names = [s.get("name", "").lower() for s in existing_suggestions if isinstance(s, dict)]
        if product_name.lower() in existing_names:
            return bad_request_response(
                message=f"COGS product '{product_name}' already exists in suggestions",
                data=None
            )
        
        # Append new product to existing suggestions
        updated_suggestions = existing_suggestions + [new_product]
        
        # Update database
        cogs_record.projected_titles = updated_suggestions
        cogs_record.updated_at = datetime.utcnow()
        db.commit()
        
        return success_response_with_status(
            message=f"Successfully added COGS product '{product_name}' with growth rates for {user_details.projections} years",
            data={
                "product_name": product_name,
                "percentage_of_revenue": growth_data["percentage_of_revenue"],
                "confidence": growth_data["confidence"],
                "market_trend": growth_data["market_trend"],
                "total_suggestions": len(updated_suggestions),
                "industry": user_details.industry,
                "company_size": user_details.company_size,
                "business_model": user_details.business_model,
                "projections": user_details.projections
            },
            status_code=200
        )
        
    except Exception as e:
        db.rollback()
        return internal_server_error_response(
            message=f"Failed to add manual COGS product: {str(e)}",
            data=None
        )

@router.post('/operating-expenses-titles-manual', response_model=StandardResponse)
def add_manual_operating_expense(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a manually provided operating expense to suggestions with AI-calculated growth rate.
    This endpoint appends the new expense to existing projected_titles in the database.
    """
    try:
        user_id = int(current_user["id"])
        
        # Extract expense name from request
        expense_name = data.get("expense_name")
        if not expense_name:
            return bad_request_response(
                message="Expense name is required",
                data=None
            )

        expense_name_lower = expense_name.strip().lower()
        # Get user basic details for context
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return not_found_response(
                message="User basic details not found. Please complete your basic details first.",
                data=None
            )
        
        # Get or create operating expenses record for this user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Get existing operating expenses record
        operating_expenses_record = db.query(OperatingExpenses).filter(OperatingExpenses.pnl_id == pnl_statement.id).first()
        if not operating_expenses_record:
            return not_found_response(
                message="Operating expenses record not found. Please generate operating expenses suggestions first.",
                data=None
            )
        
        existing_suggestions = operating_expenses_record.projected_titles or []
        existing_names = [s.get("name", "").lower() for s in existing_suggestions if isinstance(s, dict)]
        
        if expense_name_lower in existing_names:
            return bad_request_response(
                message=f"Operating expense '{expense_name}' already exists in suggestions",
                data=None
            )
        # Import the service function
        from app.services.user_service import calculate_operating_expense_growth_rate_with_ai
        
        # Calculate growth rates using AI (preserves exact expense name)
        try:
            growth_data = calculate_operating_expense_growth_rate_with_ai(expense_name, user_details)
        except Exception as e:
            logging.error(f"AI service failed for operating expense '{expense_name}': {str(e)}")
            return bad_request_response(
                message="Failed to add manual operating expense: Unable to analyze expense growth rates. Please check your OpenAI API configuration and try again.",
                data=None
            )
        
        # Create new expense suggestion (keeping exact expense name)
        new_expense = {
            "name": expense_name,  # Keep exact name as provided by user
            "percentage_of_revenue": growth_data["percentage_of_revenue"],
            "confidence": growth_data["confidence"],
            "market_trend": growth_data["market_trend"]
        }
        
        # Get existing suggestions
        existing_suggestions = operating_expenses_record.projected_titles or []
        
        # Check if expense already exists (case-insensitive)
        existing_names = [s.get("name", "").lower() for s in existing_suggestions if isinstance(s, dict)]
        if expense_name.lower() in existing_names:
            return bad_request_response(
                message=f"Operating expense '{expense_name}' already exists in suggestions",
                data=None
            )
        
        # Append new expense to existing suggestions
        updated_suggestions = existing_suggestions + [new_expense]
        
        # Update database
        operating_expenses_record.projected_titles = updated_suggestions
        operating_expenses_record.updated_at = datetime.utcnow()
        db.commit()
        
        return StandardResponse(
            success=True,
            message=f"Successfully added operating expense '{expense_name}' with growth rates for {user_details.projections} years",
            data={
                "expense_name": expense_name,
                "percentage_of_revenue": growth_data["percentage_of_revenue"],
                "confidence": growth_data["confidence"],
                "market_trend": growth_data["market_trend"],
                "total_suggestions": len(updated_suggestions),
                "industry": user_details.industry,
                "company_size": user_details.company_size,
                "business_model": user_details.business_model,
                "projections": user_details.projections
            }
        )
        
    except Exception as e:
        db.rollback()
        return StandardResponse(
            success=False,
            message=f"Failed to add manual operating expense: {str(e)}",
            data=None
        )        

@router.post('/cogs-save', response_model=StandardResponse)
def save_cogs(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing COGS record by cogs_id. Supports updating all fields, including product as a list (multi-product) and multi-year data.
    """
    try:
        user_id = int(current_user["id"])
        # Get cogs_id using get_topic_record_id function
        cogs_id = get_topic_record_id("pnl", "cogs", current_user, db)
        
        # Get user details for validation
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return StandardResponse(
                success=False,
                message="User basic details not found",
                data=None
            )
        
        # Validate the data structure manually (simplified validation)
        data_json = data.get("data_json", {})
        if not data_json or not isinstance(data_json, dict):
            return StandardResponse(
                success=False,
                message="data_json is required and must be a dictionary",
                data=None
            )
        
        products = data_json.get("data", {}).get("products", [])
        if not products or not isinstance(products, list):
            return StandardResponse(
                success=False,
                message="data_json.data.products is required and must be a list",
                data=None
            )
        
        # Validate each product has required fields
        for i, product in enumerate(products):
            if not isinstance(product, dict):
                return StandardResponse(
                    success=False,
                    message=f"Product {i} must be a dictionary",
                    data=None
                )
            
            if "name" not in product or "cogs" not in product:
                return StandardResponse(
                    success=False,
                    message=f"Product {i} must have 'name' and 'cogs' fields",
                    data=None
                )
            
            if not isinstance(product["cogs"], list):
                return StandardResponse(
                    success=False,
                    message=f"Product {i} cogs must be a list",
                    data=None
                )
            
            # Validate optional fields if present
            if "units_sold" in product and product["units_sold"] is not None:
                if not isinstance(product["units_sold"], (int, float)):
                    return StandardResponse(
                        success=False,
                        message=f"Product {i} units_sold must be a number",
                        data=None
                    )
            
            if "average_price" in product and product["average_price"] is not None:
                if not isinstance(product["average_price"], (int, float)):
                    return StandardResponse(
                        success=False,
                        message=f"Product {i} average_price must be a number",
                        data=None
                    )
            
            if "month_1" in product and product["month_1"] is not None:
                if not isinstance(product["month_1"], (int, float)):
                    return StandardResponse(
                        success=False,
                        message=f"Product {i} month_1 must be a number",
                        data=None
                    )
        
        # Update COGS record by id with validated data
        saved_cogs = update_cogs_by_id(db, cogs_id, data)
        
        # Return clean response without extra fields
        return StandardResponse(
            success=True,
            message="COGS data saved successfully",
            data={
                "cogs_id": cogs_id,
                "data_json": {
                    "data": {
                        "years": data_json.get("data", {}).get("years"),
                        "products": products,
                        "total_cogs": data_json.get("data", {}).get("total_cogs")
                    }
                }
            }
        )
        
    except HTTPException as e:
        return StandardResponse(
            success=False,
            message=e.detail,
            data=None
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Internal server error: {str(e)}",
            data=None
        )

@router.post('/returns/calculate-projections', response_model=StandardResponse)
def calculate_returns_projections(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Calculate projections for a specific returns row based on Y1 data.
    Returns projections without saving to database.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user details for context
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return StandardResponse(
                success=False,
                message="User basic details not found",
                data=None
            )
        
        # Extract data from request
        row_data = data.get("row_data", {})
        
        product_name = row_data.get("product_name")
        y1_returns = row_data.get("y1_returns")
        y0_units_returned = row_data.get("y0_units_returned")  # Base return units
        y0_price = row_data.get("y0_price")  # Base return price
        
        # Validate row data fields
        if not all([product_name, y1_returns is not None, y0_units_returned is not None, y0_price is not None]):
            return StandardResponse(
                success=False,
                message="All row_data fields are required: product_name, y1_returns, y0_units_returned, y0_price",
                data=None
            )
        
        # Create a basic structure for the formula service to work with
        existing_returns_data = {
            "data": {
                "products": [
                    {
                        "name": product_name,
                        "returns": [y1_returns, None, None],
                        "units_returned": y0_units_returned,
                        "average_price": y0_price
                    }
                ]
            },
            "projections": user_details.projections or 3
        }
        




        
        # Formula service removed - returning basic response
        projection_result = None
        
        if not projection_result:
            return StandardResponse(
                success=False,
                message="Failed to calculate returns projections",
                data=None
            )
        
        # Extract values from projection result
        returns_array = projection_result.get("returns", [y1_returns])
        y0_units_returned = projection_result.get("units_returned", y0_units_returned)
        y0_price = projection_result.get("average_price", y0_price)
        formula_id = projection_result.get("formula_id")
        
        # Get the return_id from the user's existing returns record
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        return_id = None
        if pnl_statement:
            revenue_stream = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).first()
            if revenue_stream:
                returns_record = db.query(Return).filter(Return.revenue_id == revenue_stream.id).first()
                if returns_record:
                    return_id = returns_record.id
        
        # Log successful calculation
        logging.info(f"Returns projections calculated successfully for user {user_id}, product: {product_name}")
        
        return StandardResponse(
            success=True,
            message=f"Returns projections calculated successfully for product: {product_name} using stored formula",
            data={
                "product_name": product_name,
                "returns": returns_array,
                "units_returned": y0_units_returned,
                "average_price": y0_price,
                "return_id": return_id,
                "formula_id": formula_id
            }
        )
        
    except Exception as e:
        logging.error(f"Error calculating returns projections: {str(e)}")
        return StandardResponse(
            success=False,
            message=f"Internal server error: {str(e)}",
            data=None
        ) 

@router.get('/test-projections', response_model=StandardResponse)
def test_projections(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Test endpoint to verify projection calculation setup.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user details
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return StandardResponse(
                success=False,
                message="User basic details not found",
                data=None
            )
        
        return StandardResponse(
            success=True,
            message="Projection calculation setup is working",
            data={
                "user_id": user_id,
                "projections": user_details.projections,
                "currency": user_details.currency,
                "fin_year": user_details.fin_year,
                "endpoints_available": [
                    "POST /revenue/calculate-projections",
                    "POST /returns/calculate-projections"
                ]
            }
        )
        
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Test failed: {str(e)}",
            data=None
        )

@router.post('/revenue-titles-suggestions', response_model=StandardResponse)
def generate_revenue_title_suggestions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate revenue title suggestions with growth rates using AI based on user's business context.
    Updates the revenue stream table's projected_titles column.
    Includes caching to prevent regeneration.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user basic details
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return not_found_response(
                message="User basic details not found. Please complete your basic details first.",
                data=None
            )
        
        # Get or create revenue stream record for this user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Check if revenue stream exists and has suggestions already
        revenue_stream = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).first()
        if revenue_stream and revenue_stream.projected_titles:
            # Check if suggestions already exist and are in the new format
            existing_suggestions = revenue_stream.projected_titles
            if isinstance(existing_suggestions, list) and len(existing_suggestions) > 0:
                # Check if it's the new format (with growth rates) or old format (just names)
                if isinstance(existing_suggestions[0], dict) and ('growth_rate' in existing_suggestions[0] or 'growth_rates' in existing_suggestions[0]):
                    # Already generated with growth rates - return existing
                    return success_response_with_status(
                        message="Product suggestions already being generated. Retrieved existing suggestions with growth rates.",
                        data={
                            "revenue_id": revenue_stream.id,
                            "suggestions": existing_suggestions,
                            "count": len(existing_suggestions),
                            "industry": user_details.industry,
                            "company_size": user_details.company_size,
                            "business_model": user_details.business_model,
                            "projections": user_details.projections,
                            "last_updated": revenue_stream.updated_at.isoformat() if revenue_stream.updated_at else None
                        },
                        status_code=200
                    )
                else:
                    # Old format - regenerate with growth rates
                    logging.info(f"Converting old format suggestions to new format with growth rates for user {user_id}")
        
        # Import the service function
        from app.services.user_service import generate_revenue_title_suggestions_with_ai
        
        # Generate revenue title suggestions with growth rates using AI
        try:
            suggestions = generate_revenue_title_suggestions_with_ai(user_details)
            logging.info(f"Successfully generated {len(suggestions)} revenue suggestions for user {user_id}")
        except Exception as ai_error:
            logging.error(f"AI service failed for user {user_id}: {str(ai_error)}")
            raise ai_error
        
        # Create or update revenue stream record
        if not revenue_stream:
            # Create a new revenue stream record
            revenue_stream = RevenueStream(
                pnl_id=pnl_statement.id,
                data_json={},  # Empty data for now
                projected_titles=suggestions,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(revenue_stream)
            db.commit()
            db.refresh(revenue_stream)
        else:
            # Update existing revenue stream with new suggestions
            revenue_stream.projected_titles = suggestions
            revenue_stream.updated_at = datetime.utcnow()
            db.commit()
        
        # Update UserProgress.pnl_statements to True if it's currently False
        user_progress = db.query(UserProgress).filter(UserProgress.user_id == user_id).first()
        if user_progress and not user_progress.pnl_statements:
            user_progress.pnl_statements = True
            db.commit()
            logging.info(f"Updated UserProgress.pnl_statements to True for user {user_id}")
        
        # Update PNLStatement.revenue to True if it's currently False
        if not pnl_statement.revenue:
            pnl_statement.revenue = True
            db.commit()
            logging.info(f"Updated PNLStatement.revenue to True for user {user_id}")
        
        return success_response_with_status(
            message=f"Successfully generated {len(suggestions)} revenue title suggestions with growth rates using AI",
            data={
                "revenue_id": revenue_stream.id,
                "suggestions": suggestions,
                "count": len(suggestions),
                "industry": user_details.industry,
                "company_size": user_details.company_size,
                "business_model": user_details.business_model,
                "projections": user_details.projections,
                "last_updated": revenue_stream.updated_at.isoformat() if revenue_stream.updated_at else None
            },
            status_code=200
        )
        
    except HTTPException as http_error:
        db.rollback()
        logging.error(f"HTTP error in revenue title suggestions for user {user_id}: {http_error.detail}")
        return error_response_with_status(
            message=f"Failed to generate revenue title suggestions: {http_error.detail}",
            data=None,
            status_code=http_error.status_code
        )
    except Exception as e:
        db.rollback()
        logging.error(f"Failed to generate revenue title suggestions for user {user_id}: {str(e)}")
        return internal_server_error_response(
            message=f"Failed to generate revenue title suggestions: {str(e)}",
            data=None
        )

@router.get('/revenue-titles-suggestions', response_model=StandardResponse)
def get_revenue_title_suggestions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve stored revenue title suggestions with growth rates from the database.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's revenue stream record
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        revenue_stream = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).first()
        if not revenue_stream:
            return bad_request_response(
                message="No revenue titles found. Please generate suggestions first using POST /revenue-titles-suggestions",
                data=None
            )
        
        suggestions = revenue_stream.projected_titles or []
        
        # Check if suggestions are empty
        if not suggestions or len(suggestions) == 0:
            return bad_request_response(
                message="No revenue title suggestions found. Please generate suggestions first using POST /revenue-titles-suggestions",
                data=None
            )
        
        # Check if suggestions are in the new format (with growth rates)
        has_growth_rates = False
        if suggestions and isinstance(suggestions, list) and len(suggestions) > 0:
            if isinstance(suggestions[0], dict) and ('growth_rate' in suggestions[0] or 'growth_rates' in suggestions[0]):
                has_growth_rates = True
        
        # Get user details for projections
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        
        return success_response_with_status(
            message=f"Retrieved {len(suggestions)} revenue title suggestions{' with growth rates' if has_growth_rates else ''}",
            data={
                "revenue_id": revenue_stream.id,
                "suggestions": suggestions,
                "count": len(suggestions),
                "has_growth_rates": has_growth_rates,
                "projections": user_details.projections if user_details else None,
                "last_updated": revenue_stream.updated_at.isoformat() if revenue_stream.updated_at else None
            },
            status_code=200
        )
        
    except Exception as e:
        return internal_server_error_response(
            message=f"Failed to retrieve revenue title suggestions: {str(e)}",
            data=None
        )

@router.post('/revenue-titles-manual', response_model=StandardResponse)
def add_manual_revenue_product(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a manually provided product to revenue suggestions with AI-calculated growth rate.
    This endpoint appends the new product to existing projected_titles in the database.
    """
    try:
        user_id = int(current_user["id"])
        
        # Extract product name from request
        product_name = data.get("product_name")
        if not product_name:
            return bad_request_response(
                message="Product name is required",
                data=None
            )
        
        # Get user basic details for context
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return not_found_response(
                message="User basic details not found. Please complete your basic details first.",
                data=None
            )
        
        # Get or create revenue stream record for this user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Get existing revenue stream
        revenue_stream = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).first()
        if not revenue_stream:
            return not_found_response(
                message="Revenue stream not found. Please generate revenue suggestions first.",
                data=None
            )
        
        # Import the service function
        from app.services.user_service import calculate_product_growth_rate_with_ai
        
        # Calculate growth rates using AI (preserves exact product name)
        try:
            growth_data = calculate_product_growth_rate_with_ai(product_name, user_details)
        except Exception as e:
            logging.error(f"AI service failed for product '{product_name}': {str(e)}")
            return internal_server_error_response(
                message=f"Failed to add manual product: Unable to analyze product growth rates. Please check your OpenAI API configuration and try again.",
                data=None
            )
        
        # Create new product suggestion (keeping exact product name)
        new_product = {
            "name": product_name,  # Keep exact name as provided by user
            "growth_rates": growth_data["growth_rates"],
            "confidence": growth_data["confidence"],
            "market_trend": growth_data["market_trend"]
        }
        
        # Get existing suggestions
        existing_suggestions = revenue_stream.projected_titles or []
        
        # Check if product already exists (case-insensitive)
        existing_names = [s.get("name", "").lower() for s in existing_suggestions if isinstance(s, dict)]
        if product_name.lower() in existing_names:
            return bad_request_response(
                message=f"Product '{product_name}' already exists in suggestions",
                data=None
            )
        
        # Append new product to existing suggestions
        updated_suggestions = existing_suggestions + [new_product]
        
        # Update database
        revenue_stream.projected_titles = updated_suggestions
        revenue_stream.updated_at = datetime.utcnow()
        db.commit()
        
        return success_response_with_status(
            message=f"Successfully added product '{product_name}' with growth rates for {user_details.projections} years",
            data={
                "product_name": product_name,
                "growth_rates": growth_data["growth_rates"],
                "confidence": growth_data["confidence"],
                "market_trend": growth_data["market_trend"],
                "total_suggestions": len(updated_suggestions),
                "industry": user_details.industry,
                "company_size": user_details.company_size,
                "business_model": user_details.business_model,
                "projections": user_details.projections
            },
            status_code=200
        )
        
    except Exception as e:
        db.rollback()
        return internal_server_error_response(
            message=f"Failed to add manual product: {str(e)}",
            data=None
        )


@router.post('/cogs-titles-suggestions', response_model=StandardResponse)
def generate_cogs_title_suggestions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate COGS title suggestions with growth rates using AI based on user's business context and revenue selected titles.
    Updates the COGS table's projected_titles column.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user basic details
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return not_found_response(
                message="User basic details not found. Please complete your basic details first.",
                data=None
            )
        
        # Get PNL statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Get revenue stream and selected titles
        revenue_stream = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).first()
        if not revenue_stream:
            return not_found_response(
                message="Revenue stream not found. Please complete your revenue setup first.",
                data=None
            )
        
        # Get revenue selected titles
        revenue_selected_titles = revenue_stream.selected_titles or []
        revenue_projected_titles_raw = revenue_stream.projected_titles or []
        revenue_projected_titles = []

        for item in revenue_projected_titles_raw:
            if isinstance(item, dict) and "name" in item:
                revenue_projected_titles.append(item["name"])
            elif isinstance(item, str):
                revenue_projected_titles.append(item)
        if not revenue_selected_titles and not revenue_projected_titles:
            return bad_request_response(
                message="No revenue data found. Please complete your revenue setup first.",
                data=None
            )
        
        # Check if COGS record exists and has suggestions already
        cogs_record = db.query(COGS).filter(COGS.pnl_id == pnl_statement.id).first()
        if cogs_record and cogs_record.projected_titles:
            # Check if suggestions already exist and are in the new format
            existing_suggestions = cogs_record.projected_titles
            if isinstance(existing_suggestions, list) and len(existing_suggestions) > 0:
                # Check if it's the new format (with growth rates) or old format (just names)
                if isinstance(existing_suggestions[0], dict) and ('percentage_of_revenue' in existing_suggestions[0] or 'percentage_of_revenue' in existing_suggestions[0]):
                    # Already generated with growth rates - return existing
                    return success_response_with_status(
                        message="COGS suggestions already being generated. Retrieved existing suggestions with growth rates.",
                        data={
                            "cogs_id": cogs_record.id,
                            "suggestions": existing_suggestions,
                            "count": len(existing_suggestions),
                            "industry": user_details.industry,
                            "company_size": user_details.company_size,
                            "business_model": user_details.business_model,
                            "projections": user_details.projections,
                            # "revenue_products": revenue_selected_titles,
                            # "revenue_projected_titles": revenue_projected_titles,
                            "last_updated": cogs_record.updated_at.isoformat() if cogs_record.updated_at else None
                        },
                        status_code=200
                    )
                else:
                    # Old format - regenerate with growth rates
                    logging.info(f"Converting old format COGS suggestions to new format with growth rates for user {user_id}")
        
        # Import the service function
        from app.services.user_service import generate_cogs_title_suggestions_with_revenue_context
        
        # Generate COGS title suggestions with growth rates using AI and revenue context
        suggestions = generate_cogs_title_suggestions_with_revenue_context(user_details, revenue_selected_titles, revenue_projected_titles)
        
        # Create or update COGS record
        if not cogs_record:
            # Create a new COGS record
            cogs_record = COGS(
                pnl_id=pnl_statement.id,
                data_json={},   
                projected_titles=suggestions,
                selected_titles=[],  
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(cogs_record)
            db.commit()
            db.refresh(cogs_record)
        else:
            # Update existing COGS record with new suggestions
            cogs_record.projected_titles = suggestions
            cogs_record.updated_at = datetime.utcnow()
            db.commit()
        
        # Update PNLStatement.cogs to True if it's currently False
        if not pnl_statement.cogs:
            pnl_statement.cogs = True
            db.commit()
            logging.info(f"Updated PNLStatement.cogs to True for user {user_id}")
        
        return success_response_with_status(
            message=f"Successfully generated {len(suggestions)} COGS title suggestions with growth rates using AI",
            data={
                "cogs_id": cogs_record.id,
                "suggestions": suggestions,
                "count": len(suggestions),
                "industry": user_details.industry,
                "company_size": user_details.company_size,
                "business_model": user_details.business_model,
                "projections": user_details.projections,
                # "revenue_products": revenue_selected_titles,
                # "revenue_projected_titles": revenue_projected_titles,
                "last_updated": cogs_record.updated_at.isoformat() if cogs_record.updated_at else None
            },
            status_code=200
        )
        
    except Exception as e:
        db.rollback()
        return internal_server_error_response(
            message=f"Failed to generate COGS title suggestions: {str(e)}",
            data=None
        )


@router.get('/cogs-titles-suggestions', response_model=StandardResponse)
def get_cogs_title_suggestions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve stored COGS title suggestions with growth rates from the database.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's COGS record
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        cogs_record = db.query(COGS).filter(COGS.pnl_id == pnl_statement.id).first()
        if not cogs_record:
            return bad_request_response(
                message="No COGS titles found. Please generate suggestions first using POST /cogs-titles-suggestions",
                data=None
            )
        
        suggestions = cogs_record.projected_titles or []
        
        # Check if suggestions are empty
        if not suggestions or len(suggestions) == 0:
            return bad_request_response(
                message="No COGS title suggestions found. Please generate suggestions first using POST /cogs-titles-suggestions",
                data=None
            )
        
        # Check if suggestions are in the new format (with growth rates)
        has_growth_rates = False
        if suggestions and isinstance(suggestions, list) and len(suggestions) > 0:
            if isinstance(suggestions[0], dict) and ('growth_rate' in suggestions[0] or 'growth_rates' in suggestions[0]):
                has_growth_rates = True
        
        # Get revenue selected titles for context
        revenue_stream = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).first()
        revenue_products = revenue_stream.selected_titles if revenue_stream else []
        
        # Get user details for projections
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        
        return success_response_with_status(
            message=f"Retrieved {len(suggestions)} COGS title suggestions{' with growth rates' if has_growth_rates else ''}",
            data={
                "cogs_id": cogs_record.id,
                "suggestions": suggestions,
                "count": len(suggestions),
                "has_growth_rates": has_growth_rates,
                "projections": user_details.projections if user_details else None,
                "revenue_products": revenue_products,
                "last_updated": cogs_record.updated_at.isoformat() if cogs_record.updated_at else None
            },
            status_code=200
        )
        
    except Exception as e:
        return internal_server_error_response(
            message=f"Failed to retrieve COGS title suggestions: {str(e)}",
            data=None
        )

@router.get('/revenue-data', response_model=StandardResponse)
def get_revenue_data(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve data_json from the revenue stream table for the current user.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's revenue stream record
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        revenue_stream = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).first()
        if not revenue_stream:
            return bad_request_response(
                message="No revenue data found. Please save revenue data first using POST /revenue-save",
                data=None
            )
        
        data_json = revenue_stream.data_json or {}
        
        # Check if data_json is empty
        if not data_json or (isinstance(data_json, dict) and len(data_json) == 0):
            return bad_request_response(
                message="No revenue data found. Please save revenue data first using POST /revenue-save",
                data=None
            )
        
        
        return success_response_with_status(
            message="Revenue data retrieved successfully",
            data={
                "revenue_id": revenue_stream.id,
                "data_json": data_json,
                "last_updated": revenue_stream.updated_at.isoformat() if revenue_stream.updated_at else None
            },
            status_code=200
        )
        
    except Exception as e:
        return internal_server_error_response(
            message=f"Failed to retrieve revenue data: {str(e)}",
            data=None
        )


@router.get('/cogs-data', response_model=StandardResponse)
def get_cogs_data(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve data_json from the COGS table for the current user.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's COGS record
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        cogs_record = db.query(COGS).filter(COGS.pnl_id == pnl_statement.id).first()
        if not cogs_record:
            return bad_request_response(
                message="No COGS data found. Please save COGS data first using POST /cogs-save",
                data=None
            )
        
        data_json = cogs_record.data_json or {}
        
        # Check if data_json is empty
        if not data_json or (isinstance(data_json, dict) and len(data_json) == 0):
            return bad_request_response(
                message="No COGS data found. Please save COGS data first using POST /cogs-save",
                data=None
            )
        
        
        return success_response_with_status(
            message="COGS data retrieved successfully",
            data={
                "cogs_id": cogs_record.id,
                "data_json": data_json,
                "last_updated": cogs_record.updated_at.isoformat() if cogs_record.updated_at else None
            },
            status_code=200
        )
        
    except Exception as e:
        return internal_server_error_response(
            message=f"Failed to retrieve COGS data: {str(e)}",
            data=None
        )


@router.post('/operating-expenses-titles-suggestions', response_model=StandardResponse)
def generate_operating_expenses_title_suggestions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate operating expenses title suggestions with growth rates using AI based on user's business context.
    Updates the operating expenses table's projected_titles column.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user basic details
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return StandardResponse(
                success=False,
                message="User basic details not found. Please complete your basic details first.",
                data=None
            )
        
        # Get PNL statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return StandardResponse(
                success=False,
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Check if operating expenses record exists and has suggestions already
        operating_expenses_record = db.query(OperatingExpenses).filter(OperatingExpenses.pnl_id == pnl_statement.id).first()
        if operating_expenses_record and operating_expenses_record.projected_titles:
            # Check if suggestions already exist and are in the new format
            existing_suggestions = operating_expenses_record.projected_titles
            if isinstance(existing_suggestions, list) and len(existing_suggestions) > 0:
                # Check if it's the new format (with growth_rates array) or old format (just names)
                if isinstance(existing_suggestions[0], dict) and 'growth_rates' in existing_suggestions[0]:
                    # Already generated with growth rates - return existing
                    return StandardResponse(
                        success=True,
                        message="Operating expenses suggestions already being generated. Retrieved existing suggestions with growth rates.",
                        data={
                            "operating_expenses_id": operating_expenses_record.id,
                            "suggestions": existing_suggestions,
                            "count": len(existing_suggestions),
                            "industry": user_details.industry,
                            "company_size": user_details.company_size,
                            "business_model": user_details.business_model,
                            "last_updated": operating_expenses_record.updated_at.isoformat() if operating_expenses_record.updated_at else None
                        }
                    )
                else:
                    # Old format - regenerate with growth rates
                    logging.info(f"Converting old format operating expenses suggestions to new format with growth rates for user {user_id}")
        
        # Import the service function
        from app.services.user_service import generate_operating_expenses_title_suggestions_with_ai
        
        # Generate operating expenses title suggestions with growth rates using AI
        suggestions = generate_operating_expenses_title_suggestions_with_ai(user_details,user_id,db)
        
        # Create or update operating expenses record
        if not operating_expenses_record:
            # Create a new operating expenses record
            operating_expenses_record = OperatingExpenses(
                pnl_id=pnl_statement.id,
                data_json={},  # Empty data for now
                projected_titles=suggestions,
                selected_titles=[],  # Empty for now, will be populated when user selects
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(operating_expenses_record)
            db.commit()
            db.refresh(operating_expenses_record)
        else:
            # Update existing operating expenses record with new suggestions
            operating_expenses_record.projected_titles = suggestions
            operating_expenses_record.updated_at = datetime.utcnow()
            db.commit()
        
        # Update PNLStatement.operating_expenses to True if it's currently False
        if not pnl_statement.operating_expenses:
            pnl_statement.operating_expenses = True
            db.commit()
            logging.info(f"Updated PNLStatement.operating_expenses to True for user {user_id}")
        
        return StandardResponse(
            success=True,
            message=f"Successfully generated {len(suggestions)} operating expenses title suggestions with growth rates using AI",
            data={
                "operating_expenses_id": operating_expenses_record.id,
                "suggestions": suggestions,
                "count": len(suggestions),
                "industry": user_details.industry,
                "company_size": user_details.company_size,
                "business_model": user_details.business_model
            }
        )
        
    except Exception as e:
        db.rollback()
        return StandardResponse(
            success=False,
            message=f"Failed to generate operating expenses title suggestions: {str(e)}",
            data=None
        )


@router.get('/operating-expenses-titles-suggestions', response_model=StandardResponse)
def get_operating_expenses_title_suggestions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve stored operating expenses title suggestions with growth rates from the database.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's operating expenses record
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        operating_expenses_record = db.query(OperatingExpenses).filter(OperatingExpenses.pnl_id == pnl_statement.id).first()
        if not operating_expenses_record:
            return bad_request_response(
                message="No operating expenses titles found. Please generate suggestions first using POST /operating-expenses-titles-suggestions",
                data=None
            )
        
        suggestions = operating_expenses_record.projected_titles or []
        
        # Check if suggestions are empty
        if not suggestions or len(suggestions) == 0:
            return bad_request_response(
                message="No operating expenses title suggestions found. Please generate suggestions first using POST /operating-expenses-titles-suggestions",
                data=None
            )
        
        # Check if suggestions are in the new format (with growth rates)
        has_growth_rates = False
        if suggestions and isinstance(suggestions, list) and len(suggestions) > 0:
            if isinstance(suggestions[0], dict) and 'growth_rates' in suggestions[0]:
                has_growth_rates = True
        
        return success_response_with_status(
            message=f"Retrieved {len(suggestions)} operating expenses title suggestions",
            data={
                "operating_expenses_id": operating_expenses_record.id,
                "suggestions": suggestions,
                "count": len(suggestions),
                "has_growth_rates": has_growth_rates,
                "last_updated": operating_expenses_record.updated_at.isoformat() if operating_expenses_record.updated_at else None
            },
            status_code=200
        )
        
    except Exception as e:
        return internal_server_error_response(
            message=f"Failed to retrieve operating expenses title suggestions: {str(e)}",
            data=None
        )


@router.post('/operating-expenses-save', response_model=StandardResponse)
def save_operating_expenses(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing operating expenses record by operating_expenses_id. Supports updating all fields, including product as a list (multi-product) and multi-year data.
    """
    try:
        user_id = int(current_user["id"])
        # Get operating_expenses_id using get_topic_record_id function
        operating_expenses_id = get_topic_record_id("pnl", "operating expenses", current_user, db)
        
        # Get user details for validation
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return StandardResponse(
                success=False,
                message="User basic details not found",
                data=None
            )
        
        # Validate the data structure manually (simplified validation)
        data_json = data.get("data_json", {})
        if not data_json or not isinstance(data_json, dict):
            return StandardResponse(
                success=False,
                message="data_json is required and must be a dictionary",
                data=None
            )
        
        products = data_json.get("data", {}).get("products", [])
        if not products or not isinstance(products, list):
            return StandardResponse(
                success=False,
                message="data_json.data.products is required and must be a list",
                data=None
            )
        
        # Validate each product has required fields
        for i, product in enumerate(products):
            if not isinstance(product, dict):
                return StandardResponse(
                    success=False,
                    message=f"Product {i} must be a dictionary",
                    data=None
                )
            
            if "name" not in product or "expenses" not in product:
                return StandardResponse(
                    success=False,
                    message=f"Product {i} must have 'name' and 'expenses' fields",
                    data=None
                )
            
            if not isinstance(product["expenses"], list):
                return StandardResponse(
                    success=False,
                    message=f"Product {i} expenses must be a list",
                    data=None
                )
            
            # Validate optional fields if present
            if "growth_rates" in product and product["growth_rates"] is not None:
                if not isinstance(product["growth_rates"], list):
                    return StandardResponse(
                        success=False,
                        message=f"Product {i} growth_rates must be a list",
                        data=None
                    )
            
            if "month_1" in product and product["month_1"] is not None:
                if not isinstance(product["month_1"], (int, float)):
                    return StandardResponse(
                        success=False,
                        message=f"Product {i} month_1 must be a number",
                        data=None
                    )
        
        # Update operating expenses record by id with validated data
        saved_operating_expenses = update_operating_expenses_by_id(db, operating_expenses_id, data)
        
        # Return clean response without extra fields
        return StandardResponse(
            success=True,
            message="Operating expenses data saved successfully",
            data={
                "operating_expenses_id": operating_expenses_id,
                "data_json": {
                    "data": {
                        "years": data_json.get("data", {}).get("years"),
                        "products": products,
                        "total_operating_expenses": data_json.get("data", {}).get("total_operating_expenses")
                    }
                }
            }
        )
        
    except HTTPException as e:
        return StandardResponse(
            success=False,
            message=e.detail,
            data=None
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Internal server error: {str(e)}",
            data=None
        )   


@router.get('/operating-expenses-data', response_model=StandardResponse)
def get_operating_expenses_data(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve data_json from the operating expenses table for the current user.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's operating expenses record
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        operating_expenses_record = db.query(OperatingExpenses).filter(OperatingExpenses.pnl_id == pnl_statement.id).first()
        if not operating_expenses_record:
            return bad_request_response(
                message="No operating expenses data found. Please save operating expenses data first using POST /operating-expenses-save",
                data=None
            )
        
        data_json = operating_expenses_record.data_json or {}
        
        # Check if data_json is empty
        if not data_json or (isinstance(data_json, dict) and len(data_json) == 0):
            return bad_request_response(
                message="No operating expenses data found. Please save operating expenses data first using POST /operating-expenses-save",
                data=None
            )
        
        
        return success_response_with_status(
            message="Operating expenses data retrieved successfully",
            data={
                "operating_expenses_id": operating_expenses_record.id,
                "data_json": data_json,
                "last_updated": operating_expenses_record.updated_at.isoformat() if operating_expenses_record.updated_at else None
            },
            status_code=200
        )
        
    except Exception as e:
        return internal_server_error_response(
            message=f"Failed to retrieve operating expenses data: {str(e)}",
            data=None
        )


@router.post('/depreciation-n-amortisation-save', response_model=StandardResponse)
def save_depreciation_and_amortisation(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save depreciation and amortisation data to the depreciation_n_amortisation table.
    Similar to revenue-save and cogs-save - saves data_json directly without validation.
    """
    try:
        user_id = int(current_user["id"])
        # Get depreciation_id using get_topic_record_id function
        depreciation_id = get_topic_record_id("pnl", "depreciation and amortisation", current_user, db)
        
        # Get the depreciation_n_amortisation record
        depreciation_record = db.query(DepreciationNAmortisation).filter(DepreciationNAmortisation.id == depreciation_id).first()
        if not depreciation_record:
            return not_found_response(
                message="Depreciation & Amortisation record not found.",
                data=None
            )
        
        # Handle both response_json and data_json for backward compatibility
        data_json = data.get("data_json") or data.get("response_json", data)
        
        # Save data_json directly (like revenue-save and cogs-save)
        depreciation_record.data_json = data_json
        depreciation_record.updated_at = datetime.utcnow()
        
        # Optionally update assets_input if assets exist in data_json
        # This is for backward compatibility with existing assets_input logic
        if isinstance(data_json, dict) and "assets" in data_json:
            assets = data_json.get("assets", [])
            if isinstance(assets, list):
                existing_assets_input = depreciation_record.assets_input or {}
                existing_asset_names = set(existing_assets_input.get("assets", []))
                
                # Get new asset names from the current request
                new_asset_names = [asset.get("asset_name") for asset in assets if isinstance(asset, dict) and asset.get("asset_name")]
                
                # Add only new unique asset names to assets_input
                updated_asset_names = list(existing_asset_names) + [name for name in new_asset_names if name not in existing_asset_names]
                depreciation_record.assets_input = {"assets": updated_asset_names}
        
        db.commit()
        
        # Update PNLStatement.depreciation_n_amortisation to True if it's currently False
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if pnl_statement and not pnl_statement.depreciation_n_amortisation:
            pnl_statement.depreciation_n_amortisation = True
            db.commit()
            logging.info(f"Updated PNLStatement.depreciation_n_amortisation to True for user {user_id}")
        
        return success_response_with_status(
            message="Depreciation & Amortisation data saved successfully",
            data={
                "depreciation_n_amortisation_id": depreciation_id,
                "data_json": data_json
            },
            status_code=200
        )
        
    except HTTPException as e:
        return error_response_with_status(
            message=e.detail,
            data=None,
            status_code=e.status_code
        )
    except Exception as e:
        db.rollback()
        return internal_server_error_response(
            message=f"Failed to save depreciation & amortisation data: {str(e)}",
            data=None
        )


@router.post('/depreciation-n-amortisation-generate-details', response_model=StandardResponse)
def generate_depreciation_and_amortisation_details(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate AI-powered depreciation and amortisation details for assets.
    Returns generated details without saving to database.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get assets from request body
        request_assets = data.get("assets", [])
        
        if not request_assets:
            return StandardResponse(
                success=False,
                message="Assets array is required in request body.",
                data=None
            )
        
        # Validate required fields for each asset
        for i, asset in enumerate(request_assets):
            if not all(key in asset for key in ["asset_name", "purchase_cost", "purchase_year"]):
                return StandardResponse(
                    success=False,
                    message=f"Asset {i+1} is missing required fields: asset_name, purchase_cost, purchase_year are required",
                    data=None
                )
            
            # Validate purchase_year format
            purchase_year = asset.get("purchase_year")
            if not (isinstance(purchase_year, int) or 
                   (isinstance(purchase_year, str) and purchase_year.startswith("Y") and purchase_year[1:].isdigit())):
                return StandardResponse(
                    success=False,
                    message=f"Asset {i+1} purchase_year must be an integer or year string (e.g., 'Y1', 'Y2')",
                    data=None
                )
        
        # Get user basic details for AI context
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return StandardResponse(
                success=False,
                message="User basic details not found. Please complete your basic details first.",
                data=None
            )
        
        # Prepare all assets data for AI (no filtering for duplicates)
        assets_for_ai = []
        for asset in request_assets:
            assets_for_ai.append({
                "asset_name": asset["asset_name"],
                "purchase_year": asset["purchase_year"],
                "purchase_cost": asset["purchase_cost"]
            })
        
         # Import prompt function
        from app.prompts.pnl import get_depreciation_details_prompt
        
        # Get prompt from prompts module
        ai_prompt = get_depreciation_details_prompt(user_details, assets_for_ai)
        
        # Call AI service
        ai_response = get_openai_completion(ai_prompt)
        
        if not ai_response:
            return StandardResponse(
                success=False,
                message="Failed to generate AI response for depreciation details",
                data=None
            )
        
        # Parse AI response - handle both string and dict responses
        try:
            if isinstance(ai_response, str):
                # If response is a string, try to parse it as JSON
                ai_assets = json.loads(ai_response)
            elif isinstance(ai_response, dict):
                # If response is a dict, check for success and get data
                if not ai_response.get("success", True):
                    return StandardResponse(
                        success=False,
                        message="AI service returned error",
                        data=None
                    )
                # Try to get response from different possible keys
                response_text = ai_response.get("data", {}).get("response") or ai_response.get("response") or ai_response.get("data")
                if isinstance(response_text, str):
                    ai_assets = json.loads(response_text)
                else:
                    ai_assets = response_text
            else:
                return StandardResponse(
                    success=False,
                    message="Unexpected AI response format",
                    data=None
                )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            return StandardResponse(
                success=False,
                message=f"Failed to parse AI response: {str(e)}. Response: {str(ai_response)[:200]}",
                data=None
            )
        
        # Validate AI response structure
        if isinstance(ai_assets, dict) and "assets" in ai_assets:
            ai_assets = ai_assets["assets"]
        else:
            return StandardResponse(
                success=False,
                message="AI response missing 'assets' field",
                data=None
            )

        if not isinstance(ai_assets, list) or len(ai_assets) != len(request_assets):
            return StandardResponse(
                success=False,
                message="AI assets count mismatch with input assets",
                data=None
            )
        
        # Combine all assets with AI-generated details
        enhanced_assets = []
        excluded_assets = []
        
        for i, asset in enumerate(request_assets):
            if i < len(ai_assets):
                # Validate that AI provided all required fields
                if not all(key in ai_assets[i] for key in ["asset_type", "useful_life_years",]):
                    return StandardResponse(
                        success=False,
                        message=f"AI response missing required fields for asset {i+1}",
                        data=None
                    )
                
                # Use existing fields if available, otherwise use AI-generated ones
                useful_life_years = asset.get("useful_life_years") or ai_assets[i]["useful_life_years"]
                
                enhanced_asset = {
                    "asset_name": asset["asset_name"],
                    "asset_type": asset.get("asset_type") or ai_assets[i]["asset_type"],
                    "useful_life_years": useful_life_years,
                    "purchase_year": asset["purchase_year"],
                    "purchase_cost": asset["purchase_cost"],
                    
                }
                
                # Check if useful life is 0 - exclude from processing
                if useful_life_years in (0, None):
                    excluded_assets.append({
                        "asset_name": asset["asset_name"],
                        "asset_type": enhanced_asset["asset_type"],
                        
                        "reason": "0 useful years"
                    })
                else:
                    enhanced_assets.append(enhanced_asset)
        
        # Prepare response data
        response_data = {
            "assets": enhanced_assets,
            "total_processed": len(enhanced_assets),
            "assets_saved_to_db": False
        }
        
        # Add exclusion information if there are excluded assets
        if excluded_assets:
            response_data["excluded_assets"] = {
                "message": "These assets have 0 useful years so can't able to continue with that",
                "assets": excluded_assets,
                "count": len(excluded_assets)
            }
        
        return StandardResponse(
            success=True,
            message="Depreciation & Amortisation details generated successfully",
            data=response_data
        )
        
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to generate depreciation & amortisation details: {str(e)}",
            data=None
        )


@router.get('/returns-data', response_model=StandardResponse)
def get_returns_data(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve data_json from the returns table for the current user.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's PNL statement record
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return StandardResponse(
                success=False,
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Get user's revenue stream record (since returns are linked to revenue)
        revenue_stream = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).first()
        if not revenue_stream:
            return StandardResponse(
                success=False,
                message="No revenue data found. Returns are linked to revenue streams.",
                data=None
            )
        
        # Get returns data linked to the revenue stream
        returns_data = db.query(Return).filter(Return.revenue_id == revenue_stream.id).first()
        if not returns_data:
            return StandardResponse(
                success=False,
                message="No returns data found. Please save returns data first using POST /returns-save",
                data=None
            )
        
        data_json = returns_data.data_json or {}
        
        return StandardResponse(
            success=True,
            message="Returns data retrieved successfully",
            data={
                "return_id": returns_data.id,
                "revenue_id": revenue_stream.id,
                "data_json": data_json,
                "last_updated": returns_data.updated_at.isoformat() if returns_data.updated_at else None
            }
        )
        
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"Failed to retrieve returns data: {str(e)}",
            data=None
        )




@router.get('/test-ai', response_model=StandardResponse)
def test_ai_service(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Test endpoint to verify AI service is working properly.
    """
    try:
        from app.utils.openai_client import get_openai_completion
        from app.core.config import settings
        import json
        
        # Test multiple scenarios
        test_results = {}
        
        # Test 1: Simple JSON response
        try:
            test_prompt = "Please respond with a simple JSON: {\"test\": \"success\"}"
            ai_response = get_openai_completion(test_prompt, {
                "max_tokens": 50,
                "temperature": 0.1
            })
            test_results["simple_json"] = {
                "success": True,
                "response": ai_response,
                "length": len(ai_response) if ai_response else 0,
                "is_empty": not ai_response or not ai_response.strip()
            }
        except Exception as e:
            test_results["simple_json"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test 2: Product growth analysis (like the actual endpoint)
        try:
            test_prompt = f"""
            Analyze the growth rate for "Test Product" in the technology industry.
            
            Return JSON format:
            {{
                "corrected_name": "Test Product",
                "growth_rate": 15.0,
                "confidence": 0.8,
                "market_trend": "rising"
            }}
            """
            ai_response = get_openai_completion(test_prompt, {
                "max_tokens": 200,
                "temperature": 0.3
            })
            
            # Try to parse the response
            if ai_response and ai_response.strip():
                response_text = ai_response.strip()
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}')
                
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_text = response_text[start_idx:end_idx + 1].strip()
                    parsed_data = json.loads(json_text)
                    test_results["product_analysis"] = {
                        "success": True,
                        "response": ai_response,
                        "parsed_data": parsed_data,
                        "length": len(ai_response)
                    }
                else:
                    test_results["product_analysis"] = {
                        "success": False,
                        "error": "No valid JSON found in response",
                        "response": ai_response
                    }
            else:
                test_results["product_analysis"] = {
                    "success": False,
                    "error": "Empty response",
                    "response": ai_response
                }
        except Exception as e:
            test_results["product_analysis"] = {
                "success": False,
                "error": str(e)
            }
        
        # Check configuration
        config_info = {
            "openai_model": settings.OPENAI_MODEL,
            "api_key_set": bool(settings.OPENAI_API_KEY),
            "api_key_length": len(settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else 0
        }
        
        # Determine overall success
        overall_success = all(test.get("success", False) for test in test_results.values())
        
        return StandardResponse(
            success=overall_success,
            message="AI service test completed",
            data={
                "overall_success": overall_success,
                "config": config_info,
                "tests": test_results
            }
        )
        
    except Exception as e:
        return StandardResponse(
            success=False,
            message=f"AI service test failed: {str(e)}",
            data=None
        )

@router.get('/revenue-streams', response_model=StandardResponse)
def get_revenue_streams(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all revenue streams for the current user to help debug revenue_id issues.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's PNL statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return StandardResponse(
                success=False,
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Get all revenue streams for this user
        revenue_streams = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).all()
        
        if not revenue_streams:
            return StandardResponse(
                success=False,
                message="No revenue streams found. Please generate revenue suggestions first using POST /revenue-titles-suggestions",
                data=None
            )
        
        # Format the response
        streams_data = []
        for stream in revenue_streams:
            stream_info = {
                "revenue_id": stream.id,
                "pnl_id": stream.pnl_id,
                "has_data_json": stream.data_json is not None,
                "has_projected_titles": stream.projected_titles is not None,
                "created_at": stream.created_at.isoformat() if stream.created_at else None,
                "updated_at": stream.updated_at.isoformat() if stream.updated_at else None
            }
            
            # Add projected titles info if available
            if stream.projected_titles and isinstance(stream.projected_titles, list):
                stream_info["projected_titles_count"] = len(stream.projected_titles)
                stream_info["product_names"] = [
                    product.get("name", "Unknown") 
                    for product in stream.projected_titles 
                    if isinstance(product, dict)
                ]
            else:
                stream_info["projected_titles_count"] = 0
                stream_info["product_names"] = []
            
            streams_data.append(stream_info)
        
        return StandardResponse(
            success=True,
            message=f"Found {len(revenue_streams)} revenue stream(s)",
            data={
                "user_id": user_id,
                "pnl_id": pnl_statement.id,
                "revenue_streams": streams_data
            }
        )
        
    except Exception as e:
        logging.error(f"Error in get_revenue_streams endpoint: {str(e)}")
        return StandardResponse(
            success=False,
            message=f"Internal server error: {str(e)}",
            data=None
        )

# @router.post('/depreciation-n-amortisation-generate-assets', response_model=StandardResponse)
# def generate_depreciation_assets(
#     current_user: dict = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Generate 3 depreciation/amortisation assets using AI based on user's business context.
#     No data is stored in database - just returns generated assets.
#     """
#     try:
#         user_id = int(current_user["id"])
        
#         # Get user basic details for AI context
#         user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
#         if not user_details:
#             return StandardResponse(
#                 success=False,
#                 message="User basic details not found. Please complete your basic details first.",
#                 data=None
#             )
        
#         # Import the service function
#         from app.services.user_service import generate_depreciation_assets_with_ai
        
#         # Generate assets using AI
#         try:
#             assets = generate_depreciation_assets_with_ai(user_details, user_id, db)
#         except Exception as e:
#             logging.error(f"AI service failed for generating assets: {str(e)}")
#             return StandardResponse(
#                 success=False,
#                 message=f"Failed to generate assets: Unable to generate assets using AI. Please check your OpenAI API configuration and try again.",
#                 data=None
#             )
        
#         return StandardResponse(
#             success=True,
#             message=f"Successfully generated {len(assets)} depreciation/amortisation assets",
#             data={
#                 "assets": assets,
#                 "count": len(assets),
#                 "industry": user_details.industry,
#                 "company_size": user_details.company_size,
#                 "business_model": user_details.business_model
#             }
#         )
        
#     except Exception as e:
#         return StandardResponse(
#             success=False,
#             message=f"Failed to generate assets: {str(e)}",
#             data=None
#         )


@router.post('/depreciation-n-amortisation-generate-assets', response_model=StandardResponse)
def generate_depreciation_assets(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate depreciation/amortisation asset suggestions using AI.
    Saves results in depreciation_n_amortisation.projected_titles.
    Uses DB cache to prevent regeneration.
    """
    try:
        user_id = int(current_user["id"])

        # 1️⃣ Get user basic details
        user_details = (
            db.query(UserBasicDetails)
            .filter(UserBasicDetails.user_id == user_id)
            .first()
        )
        if not user_details:
            return not_found_response(
                message="User basic details not found. Please complete your basic details first.",
                data=None
            )

        # 2️⃣ Get PNL statement
        pnl_statement = (
            db.query(PNLStatement)
            .filter(PNLStatement.user_id == user_id)
            .first()
        )
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )

        # 3️⃣ Check if depreciation record exists
        depreciation_record = (
            db.query(DepreciationNAmortisation)
            .filter(DepreciationNAmortisation.pnl_id == pnl_statement.id)
            .first()
        )

        # 4️⃣ CACHE HIT → return existing projected_titles
        if depreciation_record and depreciation_record.projected_titles:
            existing_assets = depreciation_record.projected_titles

            if isinstance(existing_assets, list) and len(existing_assets) > 0:
                return success_response_with_status(
                    message="Depreciation/Amortisation assets already generated. Retrieved from database.",
                    data={
                        "depreciation_id": depreciation_record.id,
                        "assets": existing_assets,
                        "count": len(existing_assets),
                        "industry": user_details.industry,
                        "company_size": user_details.company_size,
                        "business_model": user_details.business_model,
                        "last_updated": depreciation_record.updated_at.isoformat()
                        if depreciation_record.updated_at else None
                    },
                    status_code=200
                )

        # 5️⃣ Import AI service
        from app.services.user_service import generate_depreciation_assets_with_ai

        # 6️⃣ Generate using AI
        try:
            assets = generate_depreciation_assets_with_ai(user_details,user_id, db)
            logging.info(
                f"Successfully generated {len(assets)} depreciation assets for user {user_id}"
            )
        except Exception as ai_error:
            logging.error(
                f"AI service failed for depreciation assets for user {user_id}: {str(ai_error)}"
            )
            raise ai_error

        # 7️⃣ Create or update depreciation record (SAME AS REVENUE)
        if not depreciation_record:
            depreciation_record = DepreciationNAmortisation(
                pnl_id=pnl_statement.id,
                assets_input={},          # optional / future use
                projected_titles=assets,  # 👈 AI output saved here
                selected_titles=None,
                data_json={},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(depreciation_record)
            db.commit()
            db.refresh(depreciation_record)
        else:
            depreciation_record.projected_titles = assets
            depreciation_record.updated_at = datetime.utcnow()
            db.commit()

        # 8️⃣ Update UserProgress (balance_sheet fits depreciation)
        user_progress = (
            db.query(UserProgress)
            .filter(UserProgress.user_id == user_id)
            .first()
        )
        if user_progress and not user_progress.balance_sheet:
            user_progress.balance_sheet = True
            db.commit()
            logging.info(
                f"Updated UserProgress.balance_sheet to True for user {user_id}"
            )

        return success_response_with_status(
            message=f"Successfully generated {len(assets)} depreciation/amortisation assets using AI",
            data={
                "depreciation_id": depreciation_record.id,
                "assets": assets,
                "count": len(assets),
                "industry": user_details.industry,
                "company_size": user_details.company_size,
                "business_model": user_details.business_model,
                "last_updated": depreciation_record.updated_at.isoformat()
                if depreciation_record.updated_at else None
            },
            status_code=200
        )

    except HTTPException as http_error:
        db.rollback()
        logging.error(
            f"HTTP error in depreciation generation for user {user_id}: {http_error.detail}"
        )
        return error_response_with_status(
            message=f"Failed to generate depreciation assets: {http_error.detail}",
            data=None,
            status_code=http_error.status_code
        )

    except Exception as e:
        db.rollback()
        logging.error(
            f"Failed to generate depreciation assets for user {user_id}: {str(e)}"
        )
        return internal_server_error_response(
            message=f"Failed to generate depreciation assets: {str(e)}",
            data=None
        )




@router.get('/depreciation-n-amortisation-assets', response_model=StandardResponse)
def get_depreciation_assets(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve stored depreciation/amortisation data from the database.
    Similar to revenue-data and cogs-data - returns data_json directly.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's PNL statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Get depreciation record
        depreciation_record = db.query(DepreciationNAmortisation).filter(DepreciationNAmortisation.pnl_id == pnl_statement.id).first()
        if not depreciation_record:
            return bad_request_response(
                message="No depreciation & amortisation data found. Please save data first using POST /depreciation-n-amortisation-save",
                data=None
            )
        
        # Get data from data_json column
        data_json = depreciation_record.data_json or {}
        
        # Check if data_json is empty
        if not data_json or (isinstance(data_json, dict) and len(data_json) == 0):
            return bad_request_response(
                message="No depreciation & amortisation data found. Please save data first using POST /depreciation-n-amortisation-save",
                data=None
            )
        
        return success_response_with_status(
            message="Depreciation & Amortisation data retrieved successfully",
            data={
                "depreciation_n_amortisation_id": depreciation_record.id,
                "data_json": data_json,
                "last_updated": depreciation_record.updated_at.isoformat() if depreciation_record.updated_at else None
            },
            status_code=200
        )
        
    except Exception as e:
        return internal_server_error_response(
            message=f"Failed to retrieve depreciation & amortisation data: {str(e)}",
            data=None
        )


@router.get('/progress-tracker', response_model=StandardResponse)
def get_pnl_progress_tracker(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the current progress for the authenticated user including PNL and Balance Sheet stages.
    Returns the status of all PNL stages (revenue, cogs, returns, operating_expenses, depreciation_and_amortisation, other_income, interest_expense, income_before_taxes) and balance sheet stages (working_capital, inventory, bs_records) along with skipped details.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user progress
        user_progress = db.query(UserProgress).filter(UserProgress.user_id == user_id).first()
        if not user_progress:
            return not_found_error("User progress not found")
        
        # Get PNL statement for this user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_error("PNL statement not found. Please complete your PNL setup first.")
        
        # Get Balance sheet for this user
        balance_sheet = db.query(BalanceSheet).filter(BalanceSheet.user_id == user_id).first()
        
        valuation = db.query(Valuation).filter(Valuation.user_id == user_id).first()
        
        # Get WorkingCapital record for this user to check receivables and payables status
        working_capital = None
        if balance_sheet:
            working_capital = db.query(WorkingCapital).filter(WorkingCapital.balance_sheet_id == balance_sheet.id).first()
        
        # Get skipped details for this user
        skipped_record = db.query(Skipped).filter(Skipped.user_id == user_id).first()
        
        # Calculate overall PNL progress - include all 8 stages
        pnl_stages = {
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
        
        # Count completed stages
        completed_stages = sum(1 for stage in pnl_stages.values() if stage)
        total_stages = len(pnl_stages)
        progress_percentage = (completed_stages / total_stages) * 100 if total_stages > 0 else 0
        
        # Determine overall PNL status
        if completed_stages == 0:
            overall_status = "not_started"
        elif completed_stages == total_stages:
            overall_status = "completed"
        else:
            overall_status = "in_progress"
        
        # Prepare skipped details
        skipped_details = {
            "returns": skipped_record.returns if skipped_record else False,
            "depreciation_and_amortisation": skipped_record.depreciation_and_amortisation if skipped_record else False,
            "interest_expense": skipped_record.interest_expense if skipped_record else False
        }
        
        # Count skipped stages
        skipped_count = sum(1 for skipped in skipped_details.values() if skipped)
        
        # Calculate balance sheet progress if balance sheet exists
        balance_sheet_stages = {}
        balance_sheet_progress = 0
        if balance_sheet:
            # Check working capital receivables and payables status from data_json
            receivables_completed = False
            payables_completed = False
            
            if working_capital and working_capital.data_json:
                data_json = working_capital.data_json or {}
                # Check if ReceivablesCalculation exists and is not empty
                receivables_calc = data_json.get("ReceivablesCalculation")
                receivables_completed = receivables_calc is not None and bool(receivables_calc)
                
                # Check if PayablesCalculation exists and is not empty
                payables_calc = data_json.get("PayablesCalculation")
                payables_completed = payables_calc is not None and bool(payables_calc)
            
            balance_sheet_stages = {
                "working_capital": {
                    "receivables": receivables_completed,
                    "payables": payables_completed
                },
                "inventory": balance_sheet.inventory,   
                "bs_records": balance_sheet.bs_records,
                "cashflowstatement": balance_sheet.cash_flow_statement if balance_sheet else False  
            }
            
            # Calculate balance sheet progress
            # working_capital counts as 1 only when both receivables and payables are complete (which matches balance_sheet.working_capital flag)
            working_capital_completed = 1 if balance_sheet.working_capital else 0
            inventory_completed = 1 if balance_sheet.inventory else 0
            bs_records_completed = 1 if balance_sheet.bs_records else 0
            cashflow_completed = 1 if (balance_sheet and balance_sheet.cash_flow_statement) else 0
            balance_sheet_progress = (
                                    working_capital_completed +
                                    inventory_completed +
                                    bs_records_completed +
                                    cashflow_completed
                                )
        
        # Calculate overall progress including balance sheet
        total_all_stages = total_stages + len(balance_sheet_stages)
        total_completed_stages = completed_stages + balance_sheet_progress
        overall_progress_percentage = (total_completed_stages / total_all_stages) * 100 if total_all_stages > 0 else 0
        
        return success_response(
            message="Progress retrieved successfully",
            data={
                "user_id": user_id,
                "pnl_id": pnl_statement.id,
                "balance_sheet_id": balance_sheet.id if balance_sheet else None,
                "valuation_id": valuation.id if valuation else None,
                "overall_status": overall_status,
                "progress_percentage": round(progress_percentage, 2),
                "overall_progress_percentage": round(overall_progress_percentage, 2),
                "completed_stages": completed_stages,
                "total_stages": total_stages,
                "balance_sheet_completed": balance_sheet_progress,
                "balance_sheet_total": len(balance_sheet_stages),
                "total_all_completed": total_completed_stages,
                "total_all_stages": total_all_stages,
                "pnl_stages": pnl_stages,
                "balance_sheet_stages": balance_sheet_stages,
                "skipped_details": skipped_details,
                "skipped_count": skipped_count,
                "last_updated": pnl_statement.updated_at.isoformat() if pnl_statement.updated_at else None
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve PNL progress: {str(e)}"
        )


@router.post('/', response_model=StandardResponse)
def get_concept_records(
    request: ConceptRecordsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get records for a specific PNL concept or all concepts.
    Accepts concept values: revenue, cogs, operating_expenses, 
    depreciation_and_amortisation, other_income, interest_expense, 
    income_before_taxes, or all.
    """
    try:
        user_id = int(current_user["id"])
        concept = request.concept
        
        # Get user's PNL statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_error("PNL statement not found. Please complete your PNL setup first.")
        
        pnl_id = pnl_statement.id
        results = {}
        
        # Helper functions to format responses matching existing GET endpoints
        def format_revenue_response(record):
            if not record:
                return None
            return {
                "revenue_id": record.id,
                "data_json": record.data_json or {},
                "last_updated": record.updated_at.isoformat() if record.updated_at else None
            }
        
        def format_cogs_response(record):
            if not record:
                return None
            return {
                "cogs_id": record.id,
                "data_json": record.data_json or {},
                "last_updated": record.updated_at.isoformat() if record.updated_at else None
            }
        
        def format_operating_expenses_response(record):
            if not record:
                return None
            return {
                "operating_expenses_id": record.id,
                "data_json": record.data_json or {},
                "last_updated": record.updated_at.isoformat() if record.updated_at else None
            }
        
        def format_depreciation_response(record):
            if not record:
                return None
            return {
                "depreciation_n_amortisation_id": record.id,
                "data_json": record.data_json or {},
                "last_updated": record.updated_at.isoformat() if record.updated_at else None
            }
        
        def format_other_income_response(record):
            if not record:
                return None
            return {
                "other_incomes_id": record.id,
                "data_json": record.data_json or {},
                "last_updated": record.updated_at.isoformat() if record.updated_at else None
            }
        
        def format_interest_expense_response(record):
            if not record:
                return None
            return {
                "interest_expense_id": record.id,
                "data": record.data_json or {},
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None
            }
        
        def format_income_before_taxes_response(record):
            if not record:
                return None
            return {
                "income_before_taxes_id": record.id,
                "data": record.data_json or {},
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None
            }
        
        # Query based on concept
        if concept == "all":
            # Get all concepts
            # Revenue
            revenue_record = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_id).first()
            results["revenue"] = format_revenue_response(revenue_record)
            
            # COGS
            cogs_record = db.query(COGS).filter(COGS.pnl_id == pnl_id).first()
            results["cogs"] = format_cogs_response(cogs_record)
            
            # Operating Expenses
            operating_expenses_record = db.query(OperatingExpenses).filter(OperatingExpenses.pnl_id == pnl_id).first()
            results["operating_expenses"] = format_operating_expenses_response(operating_expenses_record)
            
            # Depreciation and Amortisation
            depreciation_record = db.query(DepreciationNAmortisation).filter(DepreciationNAmortisation.pnl_id == pnl_id).first()
            results["depreciation_and_amortisation"] = format_depreciation_response(depreciation_record)
            
            # Other Income
            other_income_record = db.query(OtherIncome).filter(OtherIncome.pnl_id == pnl_id).first()
            results["other_income"] = format_other_income_response(other_income_record)
            
            # Interest Expense
            interest_expense_record = db.query(InterestExpense).filter(InterestExpense.pnl_id == pnl_id).first()
            results["interest_expense"] = format_interest_expense_response(interest_expense_record)
            
            # Income Before Taxes
            income_before_taxes_record = db.query(IncomeBeforeTaxes).filter(IncomeBeforeTaxes.pnl_id == pnl_id).first()
            results["income_before_taxes"] = format_income_before_taxes_response(income_before_taxes_record)
            
        elif concept == "revenue":
            revenue_record = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_id).first()
            return success_response(
                message="Revenue data retrieved successfully",
                data=format_revenue_response(revenue_record)
            )
            
        elif concept == "cogs":
            cogs_record = db.query(COGS).filter(COGS.pnl_id == pnl_id).first()
            return success_response(
                message="COGS data retrieved successfully",
                data=format_cogs_response(cogs_record)
            )
            
        elif concept == "operating_expenses":
            operating_expenses_record = db.query(OperatingExpenses).filter(OperatingExpenses.pnl_id == pnl_id).first()
            return success_response(
                message="Operating expenses data retrieved successfully",
                data=format_operating_expenses_response(operating_expenses_record)
            )
            
        elif concept == "depreciation_and_amortisation":
            depreciation_record = db.query(DepreciationNAmortisation).filter(DepreciationNAmortisation.pnl_id == pnl_id).first()
            if not depreciation_record:
                return success_response(
                    message="No depreciation & amortisation record found",
                    data=None
                )
            data_json = depreciation_record.data_json or {}
            return success_response(
                message="Retrieved depreciation/amortisation data",
                data={
                    "depreciation_n_amortisation_id": depreciation_record.id,
                    "data_json": data_json,
                    "last_updated": depreciation_record.updated_at.isoformat() if depreciation_record.updated_at else None
                }
            )
            
        elif concept == "other_income":
            other_income_record = db.query(OtherIncome).filter(OtherIncome.pnl_id == pnl_id).first()
            return success_response(
                message="Other income data retrieved successfully",
                data=format_other_income_response(other_income_record)
            )
            
        elif concept == "interest_expense":
            interest_expense_record = db.query(InterestExpense).filter(InterestExpense.pnl_id == pnl_id).first()
            return success_response(
                message="Interest expense data retrieved successfully",
                data=format_interest_expense_response(interest_expense_record)
            )
            
        elif concept == "income_before_taxes":
            income_before_taxes_record = db.query(IncomeBeforeTaxes).filter(IncomeBeforeTaxes.pnl_id == pnl_id).first()
            return success_response(
                message="Income before taxes data retrieved successfully",
                data=format_income_before_taxes_response(income_before_taxes_record)
            )
        
        # For "all" concept, return nested results
        return success_response(
            message=f"Records retrieved successfully for concept: {concept}",
            data=results
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve concept records: {str(e)}"
        )


@router.post('/other-income-titles-suggestions', response_model=StandardResponse)
def generate_other_charges_title_suggestions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate other charges/expenses title suggestions with growth rates using AI based on user's business context.
    Updates the other_expenses table's projected_titles column.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user basic details
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return not_found_response(
                message="User basic details not found. Please complete your basic details first.",
                data=None
            )
        
        # Get PNL statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Check if other expenses record exists and has suggestions already
        other_income_record = db.query(OtherIncome).filter(OtherIncome.pnl_id == pnl_statement.id).first()
        if other_income_record and other_income_record.projected_titles:
            # Check if suggestions already exist
            existing_suggestions = other_income_record.projected_titles
            if isinstance(existing_suggestions, list) and len(existing_suggestions) > 0:
                # Check if it's the new format (just names) or old format (objects with growth_rates)
                if isinstance(existing_suggestions[0], str):
                    # New format - already just names
                    return success_response_with_status(
                        message="Other charges suggestions already generated. Retrieved existing suggestions.",
                        data={
                            "other_income_id": other_income_record.id,
                            "suggestions": existing_suggestions,
                            "count": len(existing_suggestions),
                            "industry": user_details.industry,
                            "company_size": user_details.company_size,
                            "business_model": user_details.business_model,
                            "last_updated": other_income_record.updated_at.isoformat() if other_income_record.updated_at else None
                        },
                        status_code=200
                    )
                else:
                    # Old format - regenerate with names only
                    logging.info(f"Converting old format other charges suggestions to new format with names only for user {user_id}")
        
        # Import the service function
        from app.services.user_service import generate_other_charges_title_suggestions_with_ai
        
        # Generate other income title suggestions using AI
        suggestion_names = generate_other_charges_title_suggestions_with_ai(user_details,db,user_id)
        
        # Create or update other expenses record
        if not other_income_record:
            # Create a new other expenses record
            other_income_record = OtherIncome(
                pnl_id=pnl_statement.id,
                data_json={},  # Empty data for now
                projected_titles=suggestion_names,  # Store only names
                selected_titles=[],  # Empty for now, will be populated when user selects
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(other_income_record)
            db.commit()
            db.refresh(other_income_record)
        else:
            # Update existing other expenses record with new suggestions
            other_income_record.projected_titles = suggestion_names  # Store only names
            other_income_record.updated_at = datetime.utcnow()
            db.commit()
        
        # Update PNLStatement.other_income to True if it's currently False
        if not pnl_statement.other_income:
            pnl_statement.other_income = True
            db.commit()
            logging.info(f"Updated PNLStatement.other_income to True for user {user_id}")
        
        return success_response_with_status(
            message=f"Successfully generated {len(suggestion_names)} other charges title suggestions using AI",
            data={
                "other_income_id": other_income_record.id,
                "suggestions": suggestion_names,
                "count": len(suggestion_names),
                "industry": user_details.industry,
                "company_size": user_details.company_size,
                "business_model": user_details.business_model
            },
            status_code=200
        )
        
    except Exception as e:
        db.rollback()
        return internal_server_error_response(
            message=f"Failed to generate other charges title suggestions: {str(e)}",
            data=None
        )


@router.get('/other-income-titles-suggestions', response_model=StandardResponse)
def get_other_charges_title_suggestions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve stored other charges/expenses title suggestions with growth rates from the database.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's other expenses record
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        other_income_record = db.query(OtherIncome).filter(OtherIncome.pnl_id == pnl_statement.id).first()
        if not other_income_record:
            return bad_request_response(
                message="No other charges titles found. Please generate suggestions first using POST /other-income-titles-suggestions",
                data=None
            )
        
        suggestions = other_income_record.projected_titles or []
        
        # Check if suggestions are empty
        if not suggestions or len(suggestions) == 0:
            return bad_request_response(
                message="No other charges title suggestions found. Please generate suggestions first using POST /other-income-titles-suggestions",
                data=None
            )
        
        # Handle suggestions format
        suggestion_names = []
        if suggestions and isinstance(suggestions, list) and len(suggestions) > 0:
            if isinstance(suggestions[0], str):
                # New format - already just names
                suggestion_names = suggestions
            elif isinstance(suggestions[0], dict) and 'name' in suggestions[0]:
                # Old format with objects - extract names
                # suggestion_names = [suggestion.get("name", "") for suggestion in suggestions if suggestion.get("name")]
                suggestion_names = []

                for suggestion in suggestions:
                    if isinstance(suggestion, dict):
                        name = suggestion.get("name")
                        if name:
                            suggestion_names.append(name)
                    elif isinstance(suggestion, str):
                        suggestion_names.append(suggestion)
            else:
                # Fallback - treat as names
                suggestion_names = suggestions
        
        return success_response_with_status(
            message=f"Retrieved {len(suggestion_names)} other charges title suggestions",
            data={
                "other_income_id": other_income_record.id,
                "suggestions": suggestion_names,
                "count": len(suggestion_names),
                "last_updated": other_income_record.updated_at.isoformat() if other_income_record.updated_at else None
            },
            status_code=200
        )
        
    except Exception as e:
        return internal_server_error_response(
            message=f"Failed to retrieve other charges title suggestions: {str(e)}",
            data=None
        )


@router.post('/other-income-save', response_model=StandardResponse)
def save_other_income(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save other income data to the other_income table's data_json column.
    """
    try:
        user_id = int(current_user["id"])
        # Get other_incomes_id using get_topic_record_id function
        other_incomes_id = get_topic_record_id("pnl", "other income", current_user, db)
        data_json = data.get("data_json")
        
        if not data_json:
            return bad_request_response(
                message="data_json is required",
                data=None
            )
        
        # Validate data_json structure
        if not isinstance(data_json, dict):
            return bad_request_response(
                message="data_json must be a dictionary",
                data=None
            )
        
        # Get the other income record
        other_income_record = db.query(OtherIncome).filter(OtherIncome.id == other_incomes_id).first()
        if not other_income_record:
            return not_found_response(
                message="Other income record not found",
                data=None
            )
        
        # Verify the record belongs to the current user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.id == other_income_record.pnl_id).first()
        if not pnl_statement or pnl_statement.user_id != user_id:
            return bad_request_response(
                message="You don't have permission to update this record",
                data=None
            )
        
        # Update the data_json column
        other_income_record.data_json = data_json
        other_income_record.updated_at = datetime.utcnow()
        db.commit()
        
        return success_response_with_status(
            message="Other income data saved successfully",
            data={
                "other_incomes_id": other_income_record.id,
                "data_json": data_json,
                "updated_at": other_income_record.updated_at.isoformat()
            },
            status_code=200
        )
        
    except Exception as e:
        db.rollback()
        return internal_server_error_response(
            message=f"Failed to save other income data: {str(e)}",
            data=None
        )


@router.get('/other-income-data', response_model=StandardResponse)
def get_other_income_data(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve other income data from the other_income table's data_json column for the current user.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's PNL statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Get the other income record for this user
        other_income_record = db.query(OtherIncome).filter(OtherIncome.pnl_id == pnl_statement.id).first()
        if not other_income_record:
            return not_found_response(
                message="Other income record not found. Please generate other income suggestions first.",
                data=None
            )
        
        # Get the data_json
        data_json = other_income_record.data_json or {}
        
        return success_response_with_status(
            message="Other income data retrieved successfully",
            data={
                "other_incomes_id": other_income_record.id,
                "data_json": data_json,
                "last_updated": other_income_record.updated_at.isoformat() if other_income_record.updated_at else None
            },
            status_code=200
        )
        
    except Exception as e:
        return internal_server_error_response(
            message=f"Failed to retrieve other income data: {str(e)}",
            data=None
        )


@router.post('/other-income-titles-manual', response_model=StandardResponse)
def add_manual_other_income_title(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a manual other income title to the projected_titles array.
    If projected_titles already exists, append the new title to it.
    """
    try:
        user_id = int(current_user["id"])
        income_name = data.get("income_name")
        
        if not income_name:
            return bad_request_response(
                message="income_name is required",
                data=None
            )
        
        if not isinstance(income_name, str) or not income_name.strip():
            return bad_request_response(
                message="income_name must be a non-empty string",
                data=None
            )
        
        income_name_lower = income_name.strip().lower()
        # Get user's PNL statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        # Get or create other income record
        other_income_record = db.query(OtherIncome).filter(OtherIncome.pnl_id == pnl_statement.id).first()
        if not other_income_record:
            # Create a new other income record
            other_income_record = OtherIncome(
                pnl_id=pnl_statement.id,
                data_json={},
                projected_titles=[],
                selected_titles=[],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(other_income_record)
            db.commit()
            db.refresh(other_income_record)
        
        # Get existing projected titles and create a new list to avoid reference issues
        existing_titles = list(other_income_record.projected_titles or [])
        
        # Check if the title already exists
        if income_name.strip() in existing_titles:
            return bad_request_response(
                message=f"Other income title '{income_name}' already exists",
                data={
                    "other_incomes_id": other_income_record.id,
                    "projected_titles": existing_titles,
                    "count": len(existing_titles)
                }
            )
        
        # Add the new title to the new list
        new_titles = existing_titles + [income_name.strip()]
        
        # Update the projected_titles with the new list
        other_income_record.projected_titles = new_titles
        other_income_record.updated_at = datetime.utcnow()
        
        # Debug logging
        logging.info(f"Updating other_income record {other_income_record.id} with titles: {new_titles}")
        
        # Commit the changes
        db.commit()
        
        # Verify the update by refreshing from database
        db.refresh(other_income_record)
        logging.info(f"After commit, projected_titles in DB: {other_income_record.projected_titles}")
        
        return success_response_with_status(
            message=f"Successfully added other income title '{income_name}'",
            data={
                "other_incomes_id": other_income_record.id,
                "projected_titles": other_income_record.projected_titles,  # Use the refreshed data from DB
                "count": len(other_income_record.projected_titles),
                "added_title": income_name.strip()
            },
            status_code=200
        )
        
    except Exception as e:
        db.rollback()
        return internal_server_error_response(
            message=f"Failed to add manual other income title: {str(e)}",
            data=None
        )


@router.get('/other-income-debug', response_model=StandardResponse)
def debug_other_income_data(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to check what's actually stored in the database for other income.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user's PNL statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found",
                data=None
            )
        
        # Get other income record
        other_income_record = db.query(OtherIncome).filter(OtherIncome.pnl_id == pnl_statement.id).first()
        if not other_income_record:
            return not_found_response(
                message="Other income record not found",
                data=None
            )
        
        return success_response_with_status(
            message="Debug data retrieved",
            data={
                "other_incomes_id": other_income_record.id,
                "projected_titles": other_income_record.projected_titles,
                "data_json": other_income_record.data_json,
                "selected_titles": other_income_record.selected_titles,
                "created_at": other_income_record.created_at.isoformat() if other_income_record.created_at else None,
                "updated_at": other_income_record.updated_at.isoformat() if other_income_record.updated_at else None
            },
            status_code=200
        )
        
    except Exception as e:
        return internal_server_error_response(
            message=f"Debug failed: {str(e)}",
            data=None
        )


@router.post('/base-year', response_model=BaseYearResponse)
def set_base_year_endpoint(
    base_year_request: BaseYearRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Set the base year for the user's basic details
    """
    try:
        user_id = int(current_user["id"])
        result = set_base_year(db, user_id, base_year_request.base_year)
        
        return BaseYearResponse(
            success=result["success"],
            message=result["message"],
            data={
                "base_year": result["base_year"],
                "user_id": result["user_id"]
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get('/base-year', response_model=BaseYearGetResponse)
def get_base_year_endpoint(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the base year for the user's basic details
    """
    try:
        user_id = int(current_user["id"])
        result = get_base_year(db, user_id)
        
        return BaseYearGetResponse(
            success=result["success"],
            message=result["message"],
            data={
                "base_year": result["base_year"],
                "user_id": result["user_id"]
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put('/base-year', response_model=BaseYearResponse)
def update_base_year_endpoint(
    base_year_request: BaseYearRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the base year for the user's basic details
    """
    try:
        user_id = int(current_user["id"])
        result = set_base_year(db, user_id, base_year_request.base_year)
        
        return BaseYearResponse(
            success=result["success"],
            message=f"Base year updated to {base_year_request.base_year} successfully",
            data={
                "base_year": result["base_year"],
                "fin_year": result.get("fin_year"),
                "user_id": result["user_id"]
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post('/interest-expense-save', response_model=InterestExpenseSaveResponse)
def save_interest_expense_endpoint(
    request: InterestExpenseSaveRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save interest expense data for the user's PNL statement
    """
    try:
        user_id = int(current_user["id"])
        # Extract the nested data structure
        interest_expense_data = request.data_json.get("data", {})
        result = save_interest_expense(db, user_id, interest_expense_data)
        
        return InterestExpenseSaveResponse(
            success=result["success"],
            message=result["message"],
            data=result["data"],
            interest_expense_id=result["interest_expense_id"]
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get('/interest-expense', response_model=StandardResponse)
def get_interest_expense_endpoint(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get interest expense data for the user's PNL statement
    """
    try:
        user_id = int(current_user["id"])
        result = get_interest_expense(db, user_id)
        
        return StandardResponse(
            success=result["success"],
            message=result["message"],
            data={
                "interest_expense_id": result["interest_expense_id"],
                "data": result["data"],
                "created_at": result["created_at"],
                "updated_at": result["updated_at"]
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post('/income-before-taxes', response_model=StandardResponse)
def generate_income_before_taxes_tax_rate(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate effective corporate tax rate using AI and save to IncomeBeforeTaxes table.
    No request body required - uses user's basic details for AI context.
    """
    try:
        user_id = int(current_user["id"])
        result = generate_tax_rate(db, user_id)
        
        return StandardResponse(
            success=result["success"],
            message=result["message"],
            data={
                "tax_rate": result["tax_rate"]
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tax rate generation failed: {str(e)}")


@router.post('/income-before-taxes-save', response_model=IncomeBeforeTaxesSaveResponse)
def save_income_before_taxes_endpoint(
    request: IncomeBeforeTaxesSaveRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save income before taxes data for the user's PNL statement
    """
    try:
        user_id = int(current_user["id"])
        # Extract the nested data structure from the Pydantic model
        income_before_taxes_data = request.data_json.data
        result = save_income_before_taxes(db, user_id, income_before_taxes_data)
        
        return IncomeBeforeTaxesSaveResponse(
            success=result["success"],
            message=result["message"],
            data=result["data"],
            income_before_taxes_id=result["income_before_taxes_id"]
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get('/income-before-taxes-data', response_model=StandardResponse)
def get_income_before_taxes_data_endpoint(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get income before taxes data for the user's PNL statement
    """
    try:
        user_id = int(current_user["id"])
        result = get_income_before_taxes(db, user_id)
        
        return StandardResponse(
            success=result["success"],
            message=result["message"],
            data={
                "income_before_taxes_id": result["income_before_taxes_id"],
                "data": result["data"],
                "created_at": result["created_at"],
                "updated_at": result["updated_at"]
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

#Other Expenses 

@router.post('/other-expense-titles-suggestions', response_model=StandardResponse)
def generate_other_expense_title_suggestions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate other expense title suggestions using AI based on user's business context.
    Updates the other_expenses table's projected_titles column.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get user basic details
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            return not_found_response(
                message="User basic details not found. Please complete your basic details first.",
                data=None
            )
        
        # Get PNL statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Check if other expenses record exists and has suggestions already
        other_expense_record = db.query(OtherExpense).filter(OtherExpense.pnl_id == pnl_statement.id).first()
        if other_expense_record and other_expense_record.projected_titles:
            existing_suggestions = other_expense_record.projected_titles
            if isinstance(existing_suggestions, list) and len(existing_suggestions) > 0:
                # Already generated — return them
                if isinstance(existing_suggestions[0], str):
                    return success_response_with_status(
                        message="Other expense suggestions already generated. Retrieved existing suggestions.",
                        data={
                            "other_expense_id": other_expense_record.id,
                            "suggestions": existing_suggestions,
                            "count": len(existing_suggestions),
                            "industry": user_details.industry,
                            "company_size": user_details.company_size,
                            "business_model": user_details.business_model,
                            "last_updated": other_expense_record.updated_at.isoformat() if other_expense_record.updated_at else None
                        },
                        status_code=200
                    )
                else:
                    logging.info(f"Converting old format other expense suggestions to new format for user {user_id}")
        
        # Import AI service
        from app.services.user_service import generate_other_expense_title_suggestions_with_ai
        
        # Generate AI-based other expense titles
        suggestion_names = generate_other_expense_title_suggestions_with_ai(user_details, current_user["id"], db)
        # Create or update record
        if not other_expense_record:
            other_expense_record = OtherExpense(
                pnl_id=pnl_statement.id,
                data_json={},  # Empty placeholder
                projected_titles=suggestion_names,
                selected_titles=[],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(other_expense_record)
            db.commit()
            db.refresh(other_expense_record)
        else:
            other_expense_record.projected_titles = suggestion_names
            other_expense_record.updated_at = datetime.utcnow()
            db.commit()
        
        # Update PNLStatement.other_expenses flag
        if not pnl_statement.other_expense:
            pnl_statement.other_expense = True
            db.commit()
            logging.info(f"Updated PNLStatement.other_expenses to True for user {user_id}")
        
        return success_response_with_status(
            message=f"Successfully generated {len(suggestion_names)} other expense title suggestions using AI",
            data={
                "other_expense_id": other_expense_record.id,
                "suggestions": suggestion_names,
                "count": len(suggestion_names),
                "industry": user_details.industry,
                "company_size": user_details.company_size,
                "business_model": user_details.business_model
            },
            status_code=200
        )
        
    except Exception as e:
        db.rollback()
        return internal_server_error_response(
            message=f"Failed to generate other expense title suggestions: {str(e)}",
            data=None
        )






@router.get('/other-expense-titles-suggestions', response_model=StandardResponse)
def get_other_expense_title_suggestions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve stored other expense title suggestions with growth rates from the database.
    """
    try:
        user_id = int(current_user["id"])
        
        # 1️⃣ Fetch user's PNL Statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )

        # 2️⃣ Get user's 'Other Expense' record
        other_expense_record = db.query(OtherExpense).filter(OtherExpense.pnl_id == pnl_statement.id).first()
        if not other_expense_record:
            return bad_request_response(
                message="No other expense titles found. Please generate suggestions first using POST /other-expense-titles-suggestions",
                data=None
            )

        # 3️⃣ Extract suggestions
        suggestions = other_expense_record.projected_titles or []

        # 4️⃣ Check if suggestions exist
        if not suggestions or len(suggestions) == 0:
            return bad_request_response(
                message="No other expense title suggestions found. Please generate suggestions first using POST /other-expense-titles-suggestions",
                data=None
            )

        # 5️⃣ Handle different data formats
        suggestion_names = []
        if suggestions and isinstance(suggestions, list) and len(suggestions) > 0:
            if isinstance(suggestions[0], str):
                # New format (list of names)
                suggestion_names = suggestions
            elif isinstance(suggestions[0], dict) and 'name' in suggestions[0]:
                # Old format (list of objects)
                suggestion_names = [s.get("name", "") for s in suggestions if s.get("name")]
            else:
                # Fallback
                suggestion_names = suggestions

        # 6️⃣ Return success response
        return success_response_with_status(
            message=f"Retrieved {len(suggestion_names)} other expense title suggestions",
            data={
                "other_expense_id": other_expense_record.id,
                "suggestions": suggestion_names,
                "count": len(suggestion_names),
                "last_updated": other_expense_record.updated_at.isoformat() if other_expense_record.updated_at else None
            },
            status_code=200
        )

    except Exception as e:
        return internal_server_error_response(
            message=f"Failed to generate other expense title suggestions: {str(e)}",
            data=None
        )


@router.post('/other-expense-save', response_model=StandardResponse)
def save_other_expense(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save other expense data to the other_expense table's data_json column.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get other_expense_id using the helper function
        other_expense_id = get_topic_record_id("pnl", "other expense", current_user, db)
        data_json = data.get("data_json")
        print(f"→ other_expense_id = {other_expense_id}")
        print(f"→ data_json keys = {list(data_json.keys()) if data_json else None}")

        if not data_json:
            return bad_request_response(
                message="data_json is required",
                data=None
            )

        # Validate data_json structure
        if not isinstance(data_json, dict):
            return bad_request_response(
                message="data_json must be a dictionary",
                data=None
            )

        # Fetch the OtherExpense record
        other_expense_record = db.query(OtherExpense).filter(OtherExpense.id == other_expense_id).first()
        if not other_expense_record:
            return not_found_response(
                message="Other expense record not found",
                data=None
            )

        # Verify record belongs to the current user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.id == other_expense_record.pnl_id).first()
        if not pnl_statement or pnl_statement.user_id != user_id:
            return bad_request_response(
                message="You don't have permission to update this record",
                data=None
            )

        # Update and save
        other_expense_record.data_json = data_json
        other_expense_record.updated_at = datetime.utcnow()
        db.commit()

        return success_response_with_status(
            message="Other expense data saved successfully",
            data={
                "other_expense_id": other_expense_record.id,
                "data_json": data_json,
                "updated_at": other_expense_record.updated_at.isoformat()
            },
            status_code=200
        )

    except Exception as e:
        db.rollback()
        return internal_server_error_response(
            message=f"Failed to save other expense data: {str(e)}",
            data=None
        )

@router.post('/other-expense-titles-manual', response_model=StandardResponse)
def add_manual_other_expense_title(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a manual other expense title to the projected_titles array.
    If projected_titles already exists, append the new title to it.
    """
    try:
        user_id = int(current_user["id"])
        expense_name = data.get("expense_name")
        
        if not expense_name:
            return bad_request_response(
                message="expense_name is required",
                data=None
            )
        
        if not isinstance(expense_name, str) or not expense_name.strip():
            return bad_request_response(
                message="expense_name must be a non-empty string",
                data=None
            )
        expense_name_lower = expense_name.strip().lower()

        # ===================== 📌 GET USER'S PNL ===================== #
        pnl_statement = db.query(PNLStatement).filter(
            PNLStatement.user_id == user_id
        ).first()

        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )

        # Get or create other expense record
        other_expense_record = db.query(OtherExpense).filter(OtherExpense.pnl_id == pnl_statement.id).first()
        if not other_expense_record:
            # Create a new other expense record
            other_expense_record = OtherExpense(
                pnl_id=pnl_statement.id,
                data_json={},
                projected_titles=[],
                selected_titles=[],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(other_expense_record)
            db.commit()
            db.refresh(other_expense_record)
        
        # Get existing projected titles and create a new list to avoid reference issues
        existing_titles = list(other_expense_record.projected_titles or [])
        
        # Check if the title already exists
        if expense_name.strip() in existing_titles:
            return bad_request_response(
                message=f"Other expense title '{expense_name}' already exists",
                data={
                    "other_expense_id": other_expense_record.id,
                    "projected_titles": existing_titles,
                    "count": len(existing_titles)
                }
            )
        
        # Add the new title to the new list
        new_titles = existing_titles + [expense_name.strip()]
        
        # Update the projected_titles with the new list
        other_expense_record.projected_titles = new_titles
        other_expense_record.updated_at = datetime.utcnow()
        
        # Debug logging
        logging.info(f"Updating other_expense record {other_expense_record.id} with titles: {new_titles}")
        
        # Commit the changes
        db.commit()
        
        # Verify the update by refreshing from database
        db.refresh(other_expense_record)
        logging.info(f"After commit, projected_titles in DB: {other_expense_record.projected_titles}")
        
        return success_response_with_status(
            message=f"Successfully added other expense title '{expense_name}'",
            data={
                "other_expense_id": other_expense_record.id,
                "projected_titles": other_expense_record.projected_titles,
                "count": len(other_expense_record.projected_titles),
                "added_title": expense_name.strip()
            },
            status_code=200
        )
        
    except Exception as e:
        db.rollback()
        return internal_server_error_response(
            message=f"Failed to add manual other expense title: {str(e)}",
            data=None
        )


@router.get('/other-expense-data', response_model=StandardResponse)
def get_other_expense_data(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve other expense data from the other_expense table's data_json column for the current user.
    """
    try:
        user_id = int(current_user["id"])
        
        # 1️⃣ Get user's PNL statement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # 2️⃣ Get the other expense record for this user
        other_expense_record = db.query(OtherExpense).filter(OtherExpense.pnl_id == pnl_statement.id).first()
        if not other_expense_record:
            return not_found_response(
                message="Other expense record not found. Please generate other expense suggestions first.",
                data=None
            )
        
        # 3️⃣ Get the data_json
        data_json = other_expense_record.data_json or {}

        # 4️⃣ Success response
        return success_response_with_status(
            message="Other expense data retrieved successfully",
            data={
                "other_expense_id": other_expense_record.id,
                "data_json": data_json,
                "last_updated": other_expense_record.updated_at.isoformat() if other_expense_record.updated_at else None
            },
            status_code=200
        )

    except Exception as e:
        import traceback
        traceback.print_exc()  # Optional: see full error in logs
        return internal_server_error_response(
            message=f"Failed to retrieve other expense data: {str(e)}",
            data=None
        )