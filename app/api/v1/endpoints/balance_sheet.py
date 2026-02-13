import traceback
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.core.database import get_db
from app.models.models import UserBasicDetails, BalanceSheet, WorkingCapital, RevenueStream, COGS, Inventory, BSRecords, CashFlowStatement
from app.utils.utility import get_current_user, create_working_capital_data_json, merge_working_capital_data, merge_bs_records_data, update_bs_cash_from_beginning_cash
from app.utils.response_utils import success_response, error_response, not_found_response, bad_request_response, error_response_with_status
from app.utils.openai_client import get_openai_completion
from typing import Dict, Any

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

def _extract_dso_from_ai_response(response_text: str) -> int | None:
    """
    Extract DSO from AI response with improved parsing.
    If AI fails to provide valid response, return None.
    
    Args:
        response_text: Raw AI response text
    
    Returns:
        int | None: DSO in days if valid, None if AI failed
    """
    import re
    
    try:
        # Clean the response text
        response_text = str(response_text).strip()
        
        # If response is just a number, use it directly
        if response_text.isdigit():
            dso = int(response_text)
            if 1 <= dso <= 365:
                return dso
        
        # Try to find numbers in the response
        numbers = re.findall(r'\d+', response_text)
        
        if not numbers:
            return None
        
        # Try each number found, prioritizing smaller numbers (more likely to be DSO)
        for num_str in sorted(numbers, key=int):
            try:
                dso = int(num_str)
                if 1 <= dso <= 365:
                    return dso
            except (ValueError, TypeError):
                continue
        
        # If no valid number found, try the original method as fallback
        dso = int(''.join(filter(str.isdigit, response_text)))
        if 1 <= dso <= 365:
            return dso
        else:
            return None  # Invalid range
            
    except (ValueError, TypeError):
        return None  # AI failed to provide valid number


def _extract_credit_sales_percentage_from_ai_response(response_text: str) -> int | None:
    """
    Extract credit sales percentage from AI response with improved parsing.
    If AI fails to provide valid response, return None.
    
    Args:
        response_text: Raw AI response text
    
    Returns:
        int | None: Credit sales percentage if valid, None if AI failed
    """
    import re
    
    try:
        # Clean the response text
        response_text = str(response_text).strip()
        
        # If response is just a number, use it directly
        if response_text.isdigit():
            credit_percent = int(response_text)
            if 0 <= credit_percent <= 100:
                return credit_percent
        
        # Try to find numbers in the response
        numbers = re.findall(r'\d+', response_text)
        
        if not numbers:
            return None
        
        # Try each number found, prioritizing numbers in the 0-100 range
        for num_str in numbers:
            try:
                credit_percent = int(num_str)
                if 0 <= credit_percent <= 100:
                    return credit_percent
            except (ValueError, TypeError):
                continue
        
        # If no valid number found, try the original method as fallback
        credit_percent = int(''.join(filter(str.isdigit, response_text)))
        if 0 <= credit_percent <= 100:
            return credit_percent
        else:
            return None  # Invalid range
            
    except (ValueError, TypeError):
        return None  # AI failed to provide valid number


@router.post('/working-capital/generate-receivables-details')
def generate_receivables_details(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate receivables calculation details using AI based on user's business context.
    Uses two sequential AI prompts to get DSO and credit sales percentage.
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
        from app.prompts.balance_sheet import get_generate_recievables_dso_prompt, get_generate_recievables_credit_sales
        # Prompt 1: Generate DSO (Days Sales Outstanding)
        dso_prompt = get_generate_recievables_dso_prompt(user_details)
        
        # Prompt 2: Generate Credit Sales Percentage
        credit_sales_prompt = get_generate_recievables_credit_sales(user_details)
        
        # Get AI responses sequentially
        try:
            logger.info(f"Generating DSO for user {user_id} with industry: {user_details.industry}")
            dso_response = get_openai_completion(dso_prompt)
            if not dso_response:
                logger.error(f"AI returned empty DSO response for user {user_id}")
                return error_response_with_status(
                    message="AI failed to provide DSO response. Please try again.",
                    data=None,
                    status_code=500
                )
            logger.info(f"AI DSO response for user {user_id}: {dso_response}")
        except Exception as e:
            logger.error(f"AI DSO generation failed for user {user_id}: {str(e)}")
            return error_response_with_status(
                message=f"Failed to get DSO recommendation from AI: {str(e)}",
                data=None,
                status_code=500
            )
        
        try:
            logger.info(f"Generating credit sales percentage for user {user_id}")
            credit_sales_response = get_openai_completion(credit_sales_prompt)
            if not credit_sales_response:
                logger.error(f"AI returned empty credit sales response for user {user_id}")
                return error_response_with_status(
                    message="AI failed to provide credit sales percentage response. Please try again.",
                    data=None,
                    status_code=500
                )
            logger.info(f"AI credit sales response for user {user_id}: {credit_sales_response}")
        except Exception as e:
            logger.error(f"AI credit sales generation failed for user {user_id}: {str(e)}")
            return error_response_with_status(
                message=f"Failed to get credit sales percentage recommendation from AI: {str(e)}",
                data=None,
                status_code=500
            )
        
        # Extract DSO from AI response
        dso_text = str(dso_response).strip()
        dso = _extract_dso_from_ai_response(dso_text)
        if dso is None:
            logger.error(f"Failed to extract DSO from AI response for user {user_id}. Response: '{dso_text}'")
            return error_response_with_status(
                message=f"AI failed to provide valid DSO (Days Sales Outstanding). AI response: '{dso_text}'. Please try again.",
                data=None,
                status_code=422
            )
        logger.info(f"Successfully extracted DSO: {dso} for user {user_id}")
        
        # Extract credit sales percentage from AI response
        credit_sales_text = str(credit_sales_response).strip()
        credit_sales_percent = _extract_credit_sales_percentage_from_ai_response(credit_sales_text)
        if credit_sales_percent is None:
            logger.error(f"Failed to extract credit sales percentage from AI response for user {user_id}. Response: '{credit_sales_text}'")
            return error_response_with_status(
                message=f"AI failed to provide valid credit sales percentage. AI response: '{credit_sales_text}'. Please try again.",
                data=None,
                status_code=422
            )
        logger.info(f"Successfully extracted credit sales percentage: {credit_sales_percent}% for user {user_id}")
        
        # Get projections for array length
        projections = user_details.projections or 5
        
        # Log successful generation
        logger.info(f"Successfully generated working capital details for user {user_id}: DSO={dso}, CreditSales={credit_sales_percent}%, Projections={projections}")
        
        # Return the AI-generated fields
        return success_response(
            message="Working capital details generated successfully using AI",
            data={
                "NumberOfReceivableDays": [dso] * projections,
                "PercentageOfSalesOnCredit": [f"{credit_sales_percent}%"] * projections
            }
        )
        
    except Exception as e:
        return error_response(
            message=f"Failed to generate working capital details: {str(e)}",
            data=None
        )

@router.post('/working-capital/save-receivables')
def save_receivables_data(
    receivables_data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save receivables calculation data to the working capital table.
    Updates the ReceivablesCalculation section in the data_json field.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get the receivables calculation data
        receivables_calc = receivables_data.get("ReceivablesCalculation", receivables_data)
        
        # Get balance sheet record
        balance_sheet = db.query(BalanceSheet).filter(BalanceSheet.user_id == user_id).first()
        if not balance_sheet:
            return not_found_response(
                message="Balance sheet not found. Please complete your balance sheet setup first.",
                data=None
            )
        
        # Get or create working capital record
        working_capital = db.query(WorkingCapital).filter(WorkingCapital.balance_sheet_id == balance_sheet.id).first()
        
        if working_capital:
            # Update existing working capital record using merge function
            existing_data = working_capital.data_json or {}
            updated_data = merge_working_capital_data(existing_data, "ReceivablesCalculation", receivables_calc)
            
            # Force SQLAlchemy to detect the change by creating a new dict
            working_capital.data_json = dict(updated_data)
            working_capital.updated_at = datetime.utcnow()
            
            # Mark the field as modified to ensure SQLAlchemy detects the change
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(working_capital, "data_json")
        else:
            # Create new working capital record using merge function
            updated_data = merge_working_capital_data({}, "ReceivablesCalculation", receivables_calc)
            working_capital = WorkingCapital(
                balance_sheet_id=balance_sheet.id,
                data_json=updated_data,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(working_capital)
        
        # Check if both receivables and payables are completed before updating balance sheet status
        final_data = working_capital.data_json or {}
        has_receivables = "ReceivablesCalculation" in final_data and final_data.get("ReceivablesCalculation")
        has_payables = "PayablesCalculation" in final_data and final_data.get("PayablesCalculation")
        
        if has_receivables and has_payables:
            # Both sections are complete, update balance sheet working_capital status to True
            if not balance_sheet.working_capital:
                balance_sheet.working_capital = True
                logger.info(f"Updated balance sheet working_capital to True for user {user_id} (both receivables and payables completed)")
        else:
            # Ensure working_capital is False if not both are complete
            if balance_sheet.working_capital:
                balance_sheet.working_capital = False
                logger.info(f"Set balance sheet working_capital to False for user {user_id} (not all sections completed)")
        
        try:
            db.commit()
            logger.info("Database commit successful")
            
            # Force a fresh query to see what's actually in the database
            db.flush()  # Ensure all changes are sent to database
            fresh_record = db.query(WorkingCapital).filter(WorkingCapital.id == working_capital.id).first()
            logger.info(f"Fresh database query result: {fresh_record.data_json if fresh_record else 'Record not found'}")
            
            logger.info(f"Final working capital data_json after commit: {working_capital.data_json}")
        except Exception as commit_error:
            logger.error(f"Database commit failed: {str(commit_error)}")
            db.rollback()
            raise commit_error
        
        logger.info(f"Successfully saved receivables data for user {user_id}")
        
        return success_response(
            message="Receivables data saved successfully",
            data={
                "working_capital_id": working_capital.id,
                "data_json": working_capital.data_json
            }
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save receivables data for user {user_id}: {str(e)}")
        return error_response(
            message=f"Failed to save receivables data: {str(e)}",
            data=None
        )


@router.post('/working-capital/save-payables')
def save_payables_data(
    payables_data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save payables calculation data to the working capital table.
    Updates the PayablesCalculation section in the data_json field.
    """
    try:
        user_id = int(current_user["id"])
        
        logger.info(f"Starting save payables for user {user_id}")
        logger.info(f"Received payables data: {payables_data}")
        
        # Get the payables calculation data
        payables_calc = payables_data.get("PayablesCalculation", payables_data)
        logger.info(f"Extracted payables calculation: {payables_calc}")
        
        # Get balance sheet record
        balance_sheet = db.query(BalanceSheet).filter(BalanceSheet.user_id == user_id).first()
        if not balance_sheet:
            return not_found_response(
                message="Balance sheet not found. Please complete your balance sheet setup first.",
                data=None
            )
        
        # Get or create working capital record
        working_capital = db.query(WorkingCapital).filter(WorkingCapital.balance_sheet_id == balance_sheet.id).first()
        logger.info(f"Found existing working capital: {working_capital is not None}")
        
        if working_capital:
            # Update existing working capital record using merge function
            existing_data = working_capital.data_json or {}
            logger.info(f"Existing data before merge: {existing_data}")
            updated_data = merge_working_capital_data(existing_data, "PayablesCalculation", payables_calc)
            logger.info(f"Updated data after merge: {updated_data}")
            
            # Force SQLAlchemy to detect the change by creating a new dict
            working_capital.data_json = dict(updated_data)
            working_capital.updated_at = datetime.utcnow()
            logger.info("Updated existing working capital record")
            
            # Mark the field as modified to ensure SQLAlchemy detects the change
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(working_capital, "data_json")
            logger.info("Flagged data_json as modified")
        else:
            # Create new working capital record using merge function
            updated_data = merge_working_capital_data({}, "PayablesCalculation", payables_calc)
            logger.info(f"Creating new working capital with data: {updated_data}")
            working_capital = WorkingCapital(
                balance_sheet_id=balance_sheet.id,
                data_json=updated_data,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(working_capital)
            logger.info("Added new working capital record to database")
        
        # Check if both receivables and payables are completed before updating balance sheet status
        final_data = working_capital.data_json or {}
        has_receivables = "ReceivablesCalculation" in final_data and final_data.get("ReceivablesCalculation")
        has_payables = "PayablesCalculation" in final_data and final_data.get("PayablesCalculation")
        
        if has_receivables and has_payables:
            # Both sections are complete, update balance sheet working_capital status to True
            if not balance_sheet.working_capital:
                balance_sheet.working_capital = True
                logger.info(f"Updated balance sheet working_capital to True for user {user_id} (both receivables and payables completed)")
        else:
            # Ensure working_capital is False if not both are complete
            if balance_sheet.working_capital:
                balance_sheet.working_capital = False
                logger.info(f"Set balance sheet working_capital to False for user {user_id} (not all sections completed)")
        
        logger.info("Committing database changes...")
        try:
            db.commit()
            logger.info("Database commit successful")
            
            # Force a fresh query to see what's actually in the database
            db.flush()  # Ensure all changes are sent to database
            fresh_record = db.query(WorkingCapital).filter(WorkingCapital.id == working_capital.id).first()
            logger.info(f"Fresh database query result: {fresh_record.data_json if fresh_record else 'Record not found'}")
            
            logger.info(f"Final working capital data_json after commit: {working_capital.data_json}")
        except Exception as commit_error:
            logger.error(f"Database commit failed: {str(commit_error)}")
            db.rollback()
            raise commit_error
        
        logger.info(f"Successfully saved payables data for user {user_id}")
        
        return success_response(
            message="Payables data saved successfully",
            data={
                "working_capital_id": working_capital.id,
                "data_json": working_capital.data_json
            }
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save payables data for user {user_id}: {str(e)}")
        return error_response(
            message=f"Failed to save payables data: {str(e)}",
            data=None
        )


@router.post('/working-capital/generate-payables-details')
def generate_payables_details(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate payables calculation details using AI based on user's business context.
    Uses AI prompt to get DPO (Days Payable Outstanding).
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
        from app.prompts.balance_sheet import get_generate_payables_dpo_prompt
        # Generate DPO (Days Payable Outstanding) prompt
        dpo_prompt = get_generate_payables_dpo_prompt(user_details)
        
        # Get AI response
        try:
            logger.info(f"Generating DPO for user {user_id} with industry: {user_details.industry}")
            dpo_response = get_openai_completion(dpo_prompt)
            if not dpo_response:
                logger.error(f"AI returned empty DPO response for user {user_id}")
                return error_response_with_status(
                    message="AI failed to provide DPO response. Please try again.",
                    data=None,
                    status_code=500
                )
            logger.info(f"AI DPO response for user {user_id}: {dpo_response}")
        except Exception as e:
            logger.error(f"AI DPO generation failed for user {user_id}: {str(e)}")
            return error_response_with_status(
                message=f"Failed to get DPO recommendation from AI: {str(e)}",
                data=None,
                status_code=500
            )
        
        # Extract DPO from AI response
        dpo_text = str(dpo_response).strip()
        dpo = _extract_dpo_from_ai_response(dpo_text)
        if dpo is None:
            logger.error(f"Failed to extract DPO from AI response for user {user_id}. Response: '{dpo_text}'")
            return error_response_with_status(
                message=f"AI failed to provide valid DPO (Days Payable Outstanding). AI response: '{dpo_text}'. Please try again.",
                data=None,
                status_code=422
            )
        logger.info(f"Successfully extracted DPO: {dpo} for user {user_id}")
        
        # Get projections for array length
        projections = user_details.projections or 5
        
        # Log successful generation
        logger.info(f"Successfully generated payables details for user {user_id}: DPO={dpo}, Projections={projections}")
        
        # Return the AI-generated fields
        return success_response(
            message="Payables details generated successfully using AI",
            data={
                "NumberOfPayableDays": [dpo] * projections
            }
        )
        
    except Exception as e:
        return error_response(
            message=f"Failed to generate payables details: {str(e)}",
            data=None
        )


@router.get('/working-capital')
def get_working_capital_details(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve complete working capital details from the database.
    Returns both receivables and payables calculations.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get balance sheet record
        balance_sheet = db.query(BalanceSheet).filter(BalanceSheet.user_id == user_id).first()
        if not balance_sheet:
            return not_found_response(
                message="Balance sheet not found. Please complete your balance sheet setup first.",
                data=None
            )
        
        # Get working capital record
        working_capital = db.query(WorkingCapital).filter(WorkingCapital.balance_sheet_id == balance_sheet.id).first()
        if not working_capital:
            return not_found_response(
                message="Working capital record not found. Please complete your working capital setup first.",
                data=None
            )
        
        # Get complete working capital data
        working_capital_data = working_capital.data_json or {}
        
        if not working_capital_data:
            return bad_request_response(
                message="No working capital details found. Please generate working capital details first using POST /working-capital/generate-receivables-details",
                data=None
            )
        
        return success_response(
            message="Working capital details retrieved successfully",
            data={
                "working_capital_id": working_capital.id,
                "working_capital_data": working_capital_data
            }
        )
        
    except Exception as e:
        return error_response(
            message=f"Failed to retrieve working capital details: {str(e)}",
            data=None
        )


@router.post('/inventory/generate-closing-inventory')
def generate_closing_inventory(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate closing inventory values using AI based on user's revenue and COGS data.
    Extracts total revenue and COGS from PNL data and uses AI to calculate closing inventory.
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
        from app.models.models import PNLStatement
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        if not pnl_statement:
            return not_found_response(
                message="PNL statement not found. Please complete your PNL setup first.",
                data=None
            )
        
        # Get revenue data
        revenue_stream = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_statement.id).first()
        if not revenue_stream or not revenue_stream.data_json:
            return not_found_response(
                message="Revenue data not found. Please complete your revenue setup first.",
                data=None
            )
        
        # Get COGS data
        cogs_record = db.query(COGS).filter(COGS.pnl_id == pnl_statement.id).first()
        if not cogs_record or not cogs_record.data_json:
            return not_found_response(
                message="COGS data not found. Please complete your COGS setup first.",
                data=None
            )
        
        # Extract revenue and COGS data
        revenue_data = revenue_stream.data_json.get("data", {})
        cogs_data = cogs_record.data_json.get("data", {})
        
        total_revenue = revenue_data.get("total_revenue", [])
        total_cogs = cogs_data.get("total_cogs", [])
        
        if not total_revenue or not total_cogs:
            return bad_request_response(
                message="Revenue or COGS data is incomplete. Please ensure both have total values.",
                data=None
            )
        
        # Get projections for array length
        projections = user_details.projections or 5
        
        # Create AI prompt
        from app.prompts.balance_sheet import get_generate_closing_inventory

        inventory_prompt = get_generate_closing_inventory(user_details,total_revenue,total_cogs,projections)
        # Get AI response
        try:
            logger.info(f"Generating closing inventory for user {user_id} with revenue: {total_revenue}, COGS: {total_cogs}")
            inventory_response = get_openai_completion(inventory_prompt)
            if not inventory_response:
                logger.error(f"AI returned empty inventory response for user {user_id}")
                return error_response_with_status(
                    message="AI failed to provide inventory response. Please try again.",
                    data=None,
                    status_code=500
                )
            logger.info(f"AI inventory response for user {user_id}: {inventory_response}")
        except Exception as e:
            logger.error(f"AI inventory generation failed for user {user_id}: {str(e)}")
            return error_response_with_status(
                message=f"Failed to get inventory recommendation from AI: {str(e)}",
                data=None,
                status_code=500
            )
        
        # Extract closing inventory from AI response
        inventory_text = str(inventory_response).strip()
        closing_inventory = _extract_inventory_from_ai_response(inventory_text)
        if closing_inventory is None:
            logger.error(f"Failed to extract closing inventory from AI response for user {user_id}. Response: '{inventory_text}'")
            return error_response_with_status(
                message=f"AI failed to provide valid closing inventory values. AI response: '{inventory_text}'. Please try again.",
                data=None,
                status_code=422
            )
        
        # Return exactly what AI provided - no calculations on our end
        
        logger.info(f"Successfully extracted closing inventory: {closing_inventory} for user {user_id}")
        
        # Return the AI-generated closing inventory values
        return success_response(
            message="Closing inventory generated successfully using AI",
            data={
                "ClosingInventory": closing_inventory
            }
        )
        
    except Exception as e:
        return error_response(
            message=f"Failed to generate closing inventory: {str(e)}",
            data=None
        )


@router.post('/inventory/save')
def save_inventory_data(
    inventory_data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save inventory data to the inventory table.
    Updates the balance sheet inventory status to True.
    """
    try:
        user_id = int(current_user["id"])
        
        logger.info(f"Starting save inventory for user {user_id}")
        logger.info(f"Received inventory data: {inventory_data}")
        
        # Get the inventory records data
        inventory_records = inventory_data.get("data_json", {}).get("InventoryRecords", inventory_data.get("InventoryRecords", inventory_data))
        logger.info(f"Extracted inventory records: {inventory_records}")
        
        # Get balance sheet record
        balance_sheet = db.query(BalanceSheet).filter(BalanceSheet.user_id == user_id).first()
        if not balance_sheet:
            return not_found_response(
                message="Balance sheet not found. Please complete your balance sheet setup first.",
                data=None
            )
        
        # Get or create inventory record
        inventory_record = db.query(Inventory).filter(Inventory.balance_sheet_id == balance_sheet.id).first()
        
        if inventory_record:
            # Update existing inventory record
            inventory_record.data_json = inventory_records
            inventory_record.updated_at = datetime.utcnow()
            logger.info("Updated existing inventory record")
        else:
            # Create new inventory record
            inventory_record = Inventory(
                balance_sheet_id=balance_sheet.id,
                data_json=inventory_records,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(inventory_record)
            logger.info("Added new inventory record to database")
        
        # Update balance sheet inventory status to True
        if not balance_sheet.inventory:
            balance_sheet.inventory = True
            logger.info(f"Updated balance sheet inventory to True for user {user_id}")
        
        try:
            db.commit()
            logger.info("Database commit successful")
        except Exception as commit_error:
            logger.error(f"Database commit failed: {str(commit_error)}")
            db.rollback()
            raise commit_error
        
        logger.info(f"Successfully saved inventory data for user {user_id}")
        
        return success_response(
            message="Inventory data saved successfully",
            data={
                "inventory_id": inventory_record.id,
                "data_json": inventory_record.data_json
            }
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save inventory data for user {user_id}: {str(e)}")
        return error_response(
            message=f"Failed to save inventory data: {str(e)}",
            data=None
        )


@router.get('/inventory')
def get_inventory_data(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve inventory data from the database.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get balance sheet record
        balance_sheet = db.query(BalanceSheet).filter(BalanceSheet.user_id == user_id).first()
        if not balance_sheet:
            return not_found_response(
                message="Balance sheet not found. Please complete your balance sheet setup first.",
                data=None
            )
        
        # Get inventory record
        inventory_record = db.query(Inventory).filter(Inventory.balance_sheet_id == balance_sheet.id).first()
        if not inventory_record:
            return not_found_response(
                message="Inventory record not found. Please save inventory data first.",
                data=None
            )
        
        # Get inventory data
        inventory_data = inventory_record.data_json or {}
        
        if not inventory_data:
            return bad_request_response(
                message="No inventory data found. Please save inventory data first.",
                data=None
            )
        
        return success_response(
            message="Inventory data retrieved successfully",
            data={
                "inventory_id": inventory_record.id,
                "inventory_data": inventory_data
            }
        )
        
    except Exception as e:
        return error_response(
            message=f"Failed to retrieve inventory data: {str(e)}",
            data=None
        )


def _extract_dpo_from_ai_response(response_text: str) -> int | None:
    """
    Extract DPO from AI response with improved parsing.
    If AI fails to provide valid response, return None.
    
    Args:
        response_text: Raw AI response text
    
    Returns:
        int | None: DPO in days if valid, None if AI failed
    """
    import re
    
    try:
        # Clean the response text
        response_text = str(response_text).strip()
        
        # If response is just a number, use it directly
        if response_text.isdigit():
            dpo = int(response_text)
            if 1 <= dpo <= 365:
                return dpo
        
        # Try to find numbers in the response
        numbers = re.findall(r'\d+', response_text)
        
        if not numbers:
            return None
        
        # Try each number found, prioritizing smaller numbers (more likely to be DPO)
        for num_str in sorted(numbers, key=int):
            try:
                dpo = int(num_str)
                if 1 <= dpo <= 365:
                    return dpo
            except (ValueError, TypeError):
                continue
        
        # If no valid number found, try the original method as fallback
        dpo = int(''.join(filter(str.isdigit, response_text)))
        if 1 <= dpo <= 365:
            return dpo
        else:
            return None  # Invalid range
            
    except (ValueError, TypeError):
        return None  # AI failed to provide valid number


def _extract_inventory_from_ai_response(response_text: str) -> list | None:
    """
    Extract closing inventory array from AI response.
    If AI fails to provide valid response, return None.
    
    Args:
        response_text: Raw AI response text
    
    Returns:
        list | None: List of closing inventory values if valid, None if AI failed
    """
    import re
    import json
    
    try:
        # Clean the response text
        response_text = str(response_text).strip()
        
        # Try to find array pattern in the response (look for $X, $Y, $Z format)
        array_pattern = r'\[\$[\d\s,\.]+\]'
        array_match = re.search(array_pattern, response_text)
        
        if array_match:
            array_str = array_match.group(0)
            # Remove $ signs and parse
            clean_array = array_str.replace('$', '')
            try:
                inventory_values = json.loads(clean_array)
                if isinstance(inventory_values, list) and all(isinstance(x, (int, float)) for x in inventory_values):
                    return [int(x) for x in inventory_values]
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Try to find array pattern without $ signs
        array_pattern = r'\[[\d\s,\.]+\]'
        array_match = re.search(array_pattern, response_text)
        
        if array_match:
            array_str = array_match.group(0)
            try:
                inventory_values = json.loads(array_str)
                if isinstance(inventory_values, list) and all(isinstance(x, (int, float)) for x in inventory_values):
                    return [int(x) for x in inventory_values]
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Look for "closing inventory" or "inventory" followed by array
        inventory_pattern = r'(?:closing inventory|inventory).*?(\[[\d\s,\.\$]+\])'
        inventory_match = re.search(inventory_pattern, response_text, re.IGNORECASE)
        
        if inventory_match:
            array_str = inventory_match.group(1).replace('$', '')
            try:
                inventory_values = json.loads(array_str)
                if isinstance(inventory_values, list) and all(isinstance(x, (int, float)) for x in inventory_values):
                    return [int(x) for x in inventory_values]
            except (json.JSONDecodeError, ValueError):
                pass
        
        return None
        
    except Exception:
        return None  # AI failed to provide valid array


@router.post('/bs-records/save')
def save_bs_records_data(
    bs_records_data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save bs_records data to the bs_records table with selective updates.
    Supports updating specific root keys: Assets, Liabilities, ShareholdersEquity, LiabilitiesAndEquity.
    Also updates Years if provided.
    
    Request body examples:
    1. Update only Assets:
    {
      "data_json": {
        "Assets": {
          "CurrentAssets": {
            "CashOrBankBalance": [5000, 10000, 15000, 20000, 25000],
            "TradeReceivables": [1000, 1500, 2000, 2500, 3000]
          }
        }
      }
    }
    
    2. Update only Liabilities:
    {
      "data_json": {
        "Liabilities": {
          "ShortTermLiabilities": {
            "TradePayablesCreditors": [500, 700, 900, 1100, 1300]
          }
        }
      }
    }
    
    3. Update all sections:
    {
      "data_json": {
        "Years": ["2025", "2026", "2027", "2028", "2029"],
        "Assets": { ... },
        "Liabilities": { ... },
        "ShareholdersEquity": { ... },
        "LiabilitiesAndEquity": { ... }
      }
    }
    """
    try:
        user_id = int(current_user["id"])
        
        logger.info(f"Starting save bs_records for user {user_id}")
        logger.info(f"Received bs_records data: {bs_records_data}")
        
        # Extract the data_json from request
        data_to_save = bs_records_data.get("data_json", bs_records_data)
        logger.info(f"Extracted data to save: {data_to_save}")
        
        # Validate that at least one root key is provided
        root_keys = ["Assets", "Liabilities", "ShareholdersEquity", "LiabilitiesAndEquity"]
        has_valid_root_key = any(key in data_to_save for key in root_keys) or "Years" in data_to_save
        
        if not has_valid_root_key:
            return bad_request_response(
                message="Invalid data format. Must contain at least one of: Assets, Liabilities, ShareholdersEquity, LiabilitiesAndEquity, or Years",
                data=None
            )
        
        # Get balance sheet record
        balance_sheet = db.query(BalanceSheet).filter(BalanceSheet.user_id == user_id).first()
        if not balance_sheet:
            return not_found_response(
                message="Balance sheet not found. Please complete your balance sheet setup first.",
                data=None
            )
        
        # Get or create bs_records record
        bs_records_record = db.query(BSRecords).filter(BSRecords.balance_sheet_id == balance_sheet.id).first()
        
        if bs_records_record:
            # Update existing bs_records record using merge function
            existing_data = bs_records_record.data_json or {}
            logger.info(f"Existing data before merge: {existing_data}")
            
            merged_data = merge_bs_records_data(existing_data, data_to_save)
            logger.info(f"Merged data after merge: {merged_data}")
            
            # Update the record
            bs_records_record.data_json = merged_data
            bs_records_record.updated_at = datetime.utcnow()
            logger.info("Updated existing bs_records record")
            
            # Mark the field as modified to ensure SQLAlchemy detects the change
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(bs_records_record, "data_json")
        else:
            # Create new bs_records record
            bs_records_record = BSRecords(
                balance_sheet_id=balance_sheet.id,
                data_json=data_to_save,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(bs_records_record)
            logger.info("Added new bs_records record to database")
        
        # Update balance sheet bs_records status to True
        if not balance_sheet.bs_records:
            balance_sheet.bs_records = True
            logger.info(f"Updated balance sheet bs_records to True for user {user_id}")
        
        try:
            db.commit()
            logger.info("Database commit successful")
        except Exception as commit_error:
            logger.error(f"Database commit failed: {str(commit_error)}")
            db.rollback()
            raise commit_error
        
        logger.info(f"Successfully saved bs_records data for user {user_id}")
        
        return success_response(
            message="BS Records data saved successfully",
            data={
                "bs_records_id": bs_records_record.id,
                "data_json": bs_records_record.data_json
            }
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save bs_records data for user {user_id}: {str(e)}")
        return error_response_with_status(
            message=f"Failed to save bs_records data: {str(e)}",
            data=None,
            status_code=500
        )


@router.get('/bs-records')
def get_bs_records_data(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve bs_records data from the database.
    """
    try:
        user_id = int(current_user["id"])
        
        # Get balance sheet record
        balance_sheet = db.query(BalanceSheet).filter(BalanceSheet.user_id == user_id).first()
        if not balance_sheet:
            return not_found_response(
                message="Balance sheet not found. Please complete your balance sheet setup first.",
                data=None
            )
        
        # Get bs_records record
        bs_records_record = db.query(BSRecords).filter(BSRecords.balance_sheet_id == balance_sheet.id).first()
        if not bs_records_record:
            return not_found_response(
                message="BS Records not found. Please save bs_records data first.",
                data=None
            )
        
        # Get bs_records data
        bs_records_data = bs_records_record.data_json or {}
        
        if not bs_records_data:
            return bad_request_response(
                message="No bs_records data found. Please save bs_records data first.",
                data=None
            )
        
        return success_response(
            message="BS Records data retrieved successfully",
            data={
                "bs_records_id": bs_records_record.id,
                "bs_records_data": bs_records_data
            }
        )
        
    except Exception as e:
        return error_response_with_status(
            message=f"Failed to retrieve bs_records data: {str(e)}",
            data=None,
            status_code=500
        )





### CashFlow Api 

@router.post("/cashflow/generate")
def generate_cashflow_statement(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a Cash Flow Statement automatically using interdependent data:
    - Pulls from PNL (net income, depreciation)
    - Pulls from Working Capital (receivables/payables)
    - Pulls from Inventory (change in inventory)
    - Pulls from BS Records (assets, liabilities, equity)
    """
    try:
        user_id = int(current_user["id"])
        from app.models.models import (
            PNLStatement, DepreciationNAmortisation, IncomeBeforeTaxes,
            WorkingCapital, Inventory, BSRecords, CashFlowStatement
        )

        # --- Fetch base models ---
        balance_sheet = db.query(BalanceSheet).filter(BalanceSheet.user_id == user_id).first()
        if not balance_sheet:
            return not_found_response(message="Balance sheet not found.", data=None)

        pnl = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        wc = db.query(WorkingCapital).filter(WorkingCapital.balance_sheet_id == balance_sheet.id).first()
        inv = db.query(Inventory).filter(Inventory.balance_sheet_id == balance_sheet.id).first()
        bsr = db.query(BSRecords).filter(BSRecords.balance_sheet_id == balance_sheet.id).first()

        # --- Create base JSON ---
        cashflow_data = {
            "cashflow_from_operating_activities": {},
            "cashflow_from_investing_activities": {},
            "cashflow_from_financing_activities": {}
        }

        # ---------- OPERATING ACTIVITIES ----------
        # 1️⃣ Net income (from PNL)
        net_income_data = {}
        income_before_tax = db.query(IncomeBeforeTaxes).filter(IncomeBeforeTaxes.pnl_id == pnl.id).first() if pnl else None
        if income_before_tax and income_before_tax.data_json:
            net_income_data = income_before_tax.data_json
        cashflow_data["cashflow_from_operating_activities"]["net_income"] = net_income_data or "From PNL"

        # 2️⃣ Depreciation & Amortisation (from PNL)
        dep_data = db.query(DepreciationNAmortisation).filter(DepreciationNAmortisation.pnl_id == pnl.id).first() if pnl else None
        cashflow_data["cashflow_from_operating_activities"]["depreciation_and_amortisation"] = dep_data.data_json if dep_data else "From PNL"

        # 3️⃣ Taxes payable
        cashflow_data["cashflow_from_operating_activities"]["taxes_payable"] = "From PNL or BSRecords"

        # 4️⃣ Accounts receivable / payable (from working capital)
        if wc and wc.data_json:
            wc_data = wc.data_json
            cashflow_data["cashflow_from_operating_activities"]["accounts_receivable"] = wc_data.get("ReceivablesCalculation", {})
            cashflow_data["cashflow_from_operating_activities"]["accounts_payable"] = wc_data.get("PayablesCalculation", {})
        else:
            cashflow_data["cashflow_from_operating_activities"]["accounts_receivable"] = "From Working Capital"
            cashflow_data["cashflow_from_operating_activities"]["accounts_payable"] = "From Working Capital"

        # 5️⃣ Change in inventory
        cashflow_data["cashflow_from_operating_activities"]["change_in_inventory"] = inv.data_json if inv else "From Inventory"

        # 6️⃣ Prepaid expenses (manual)
        cashflow_data["cashflow_from_operating_activities"]["prepaid_expenses"] = "User Input"

        # ---------- INVESTING ACTIVITIES ----------
        # Gross fixed assets (from BS Records)
        if bsr and bsr.data_json:
            assets = bsr.data_json.get("Assets", {})
            cashflow_data["cashflow_from_investing_activities"]["gross_fixed_assets"] = assets.get("FixedAssets", {})
        else:
            cashflow_data["cashflow_from_investing_activities"]["gross_fixed_assets"] = "From BS Records"

        # ---------- FINANCING ACTIVITIES ----------
        if bsr and bsr.data_json:
            liabs = bsr.data_json.get("Liabilities", {})
            equity = bsr.data_json.get("ShareholdersEquity", {})
            cashflow_data["cashflow_from_financing_activities"]["short_term_debt"] = liabs.get("ShortTermLiabilities", {})
            cashflow_data["cashflow_from_financing_activities"]["long_term_debt"] = liabs.get("LongTermLiabilities", {})
            cashflow_data["cashflow_from_financing_activities"]["issuance_of_share_capital"] = equity
        else:
            cashflow_data["cashflow_from_financing_activities"] = {
                "short_term_debt": "From BS Records",
                "long_term_debt": "From BS Records",
                "issuance_of_share_capital": "From BS Records"
            }

        # ---------- SAVE OR UPDATE ----------
        cashflow_record = db.query(CashFlowStatement).filter(CashFlowStatement.balance_sheet_id == balance_sheet.id).first()
        if cashflow_record:
            cashflow_record.data_json = cashflow_data
            cashflow_record.updated_at = datetime.utcnow()
        else:
            cashflow_record = CashFlowStatement(
                balance_sheet_id=balance_sheet.id,
                data_json=cashflow_data,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(cashflow_record)

        balance_sheet.cash_flow_statement = True
        db.commit()

        return success_response(
            message="Cash Flow Statement generated successfully using linked data",
            data={"cashflow_id": cashflow_record.id, "data_json": cashflow_record.data_json}
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to generate cash flow statement: {str(e)}")
        return error_response(message=f"Failed to generate cash flow statement: {str(e)}")


#### ================beggining cash ============####
@router.post("/cashflow/beginning-cash")
def update_beginning_cash(
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        data_block = payload.get("data")

        if not isinstance(data_block, dict):
            raise HTTPException(status_code=400, detail="data object is required")

        data_json = data_block.get("Beginning_cash")

        if not isinstance(data_json, dict):
            raise HTTPException(status_code=400, detail="Beginning_cash is required")

        user_id = int(current_user["id"])

        # Get balance sheet
        balance_sheet = db.query(BalanceSheet).filter(
            BalanceSheet.user_id == user_id
        ).first()

        if not balance_sheet:
            raise HTTPException(status_code=404, detail="Balance Sheet not found")

        # Get cashflow
        cashflow = db.query(CashFlowStatement).filter(
            CashFlowStatement.balance_sheet_id == balance_sheet.id
        ).first()

        if not cashflow:
            raise HTTPException(status_code=404, detail="Cash Flow record not found")

        # Get BS records
        bs_records_record = (
            db.query(BSRecords)
            .filter(BSRecords.balance_sheet_id == balance_sheet.id)
            .first()
        )
        if not bs_records_record:
            raise HTTPException(status_code=404, detail="BS Records not found")

        cashflow.beginning_cash = data_block

        if not balance_sheet.cash_flow_statement:
            balance_sheet.cash_flow_statement = True

        updated_bs = update_bs_cash_from_beginning_cash(
            bs_records_record,
            data_json
        )

        bs_records_record.data_json = updated_bs
        flag_modified(bs_records_record, "data_json")

        db.commit()
        db.refresh(cashflow)

        return {
            "success": True,
            "message": "Starting cash updated successfully",
            "beginning_cash": cashflow.beginning_cash
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Error in adding_starting_cash: %s", str(e))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal Server Error")



@router.get("/cashflow/beginning-cash")
def get_beginning_cash(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user_id = int(current_user["id"])

        # Get balance sheet
        balance_sheet = db.query(BalanceSheet).filter(
            BalanceSheet.user_id == user_id
        ).first()

        if not balance_sheet:
            raise HTTPException(status_code=404, detail="Balance Sheet not found")

        # Get cashflow record
        cashflow = db.query(CashFlowStatement).filter(
            CashFlowStatement.balance_sheet_id == balance_sheet.id
        ).first()

        if not cashflow:
            raise HTTPException(status_code=404, detail="Cash Flow record not found")

        return {
            "success": True,
            "beginning_cash": cashflow.beginning_cash
        }

    except Exception as e:
        logger.error("Error in getting_beginning_cash: %s", str(e))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))



