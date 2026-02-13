from sqlalchemy.orm import Session
from app.models.models import PNLStatement, RevenueStream, Return, COGS, OperatingExpenses, InterestExpense, IncomeBeforeTaxes, UserBasicDetails
from fastapi import HTTPException
from datetime import datetime

def create_revenue_stream(db: Session, pnl_id: int, revenue_data: dict):
    # Check if PNLStatement exists
    pnl = db.query(PNLStatement).filter(PNLStatement.id == pnl_id).first()
    if not pnl:
        raise HTTPException(status_code=404, detail="P&L statement not found")
    
    # Handle both response_json and data_json for backward compatibility
    data_json = revenue_data.get("data_json") or revenue_data.get("response_json", {})
    
    # Extract product names for selected_titles
    selected_titles = []
    if data_json and isinstance(data_json, dict):
        products = data_json.get("data", {}).get("products", [])
        if isinstance(products, list):
            selected_titles = [product.get("name") for product in products if isinstance(product, dict) and product.get("name")]
    
    revenue_stream = RevenueStream(
        pnl_id=pnl_id,
        data_json=data_json,
        selected_titles=selected_titles,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(revenue_stream)
    db.commit()
    db.refresh(revenue_stream)
    return revenue_stream

def update_or_create_revenue_stream(db: Session, pnl_id: int, revenue_data: dict):
    """
    Update an existing revenue stream for the given pnl_id, or create a new one if not found.
    """
    # Try to find an existing revenue stream
    revenue_stream = db.query(RevenueStream).filter(
        RevenueStream.pnl_id == pnl_id
    ).first()
    
    # Handle both response_json and data_json for backward compatibility
    data_json = revenue_data.get("data_json") or revenue_data.get("response_json", {})
    
    # Extract product names for selected_titles
    selected_titles = []
    if data_json and isinstance(data_json, dict):
        products = data_json.get("data", {}).get("products", [])
        if isinstance(products, list):
            selected_titles = [product.get("name") for product in products if isinstance(product, dict) and product.get("name")]
    
    now = datetime.utcnow()
    if revenue_stream:
        # Update fields
        revenue_stream.data_json = data_json
        revenue_stream.selected_titles = selected_titles
        revenue_stream.updated_at = now
        db.commit()
        db.refresh(revenue_stream)
        return revenue_stream
    else:
        # Create new revenue stream
        revenue_stream = RevenueStream(
            pnl_id=pnl_id,
            data_json=data_json,
            selected_titles=selected_titles,
            created_at=now,
            updated_at=now
        )
        db.add(revenue_stream)
        db.commit()
        db.refresh(revenue_stream)
        return revenue_stream

def update_revenue_stream_by_id(db: Session, revenue_stream_id: int, revenue_data: dict):
    """
    Update an existing revenue stream by its id. Raise 404 if not found.
    """
    revenue_stream = db.query(RevenueStream).filter(RevenueStream.id == revenue_stream_id).first()
    if not revenue_stream:
        raise HTTPException(status_code=404, detail="Revenue stream not found")
    
    # Handle both response_json and data_json for backward compatibility
    data_json = revenue_data.get("data_json") or revenue_data.get("response_json", {})
    
    # Extract product names for selected_titles
    selected_titles = []
    if data_json and isinstance(data_json, dict):
        products = data_json.get("data", {}).get("products", [])
        if isinstance(products, list):
            selected_titles = [product.get("name") for product in products if isinstance(product, dict) and product.get("name")]
    
    now = datetime.utcnow()
    # Update data_json and selected_titles fields
    revenue_stream.data_json = data_json
    revenue_stream.selected_titles = selected_titles
    revenue_stream.updated_at = now
    db.commit()
    db.refresh(revenue_stream)
    return revenue_stream

def create_return(db: Session, revenue_id: int, return_data: dict):
    # Check if RevenueStream exists
    revenue_stream = db.query(RevenueStream).filter(RevenueStream.id == revenue_id).first()
    if not revenue_stream:
        raise HTTPException(status_code=404, detail="Revenue stream not found")
    
    # Handle both response_json and data_json for backward compatibility
    data_json = return_data.get("data_json") or return_data.get("response_json", {})
    
    return_record = Return(
        revenue_id=revenue_id,
        data_json=data_json,
        projected_titles=return_data.get("projected_titles"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(return_record)
    db.commit()
    db.refresh(return_record)
    return return_record

def update_return_by_id(db: Session, return_id: int, return_data: dict):
    """
    Update an existing return by its id. Raise 404 if not found.
    """
    return_record = db.query(Return).filter(Return.id == return_id).first()
    if not return_record:
        raise HTTPException(status_code=404, detail="Return record not found")
    
    # Handle both response_json and data_json for backward compatibility
    data_json = return_data.get("data_json") or return_data.get("response_json", {})
    
    now = datetime.utcnow()
    # Update data_json field
    return_record.data_json = data_json
    if "projected_titles" in return_data:
        return_record.projected_titles = return_data.get("projected_titles")
    return_record.updated_at = now
    db.commit()
    db.refresh(return_record)
    return return_record 

def ensure_pnl_stage_records_exist(db: Session, pnl_id: int):
    """
    Ensure that all PnL statement stage records exist for the given pnl_id.
    Creates empty records for revenue, returns, cogs, and operating expenses if they don't exist.
    This function should be called after the revenue-titles-suggestions API completes successfully.
    
    Args:
        db: Database session
        pnl_id: ID of the PNLStatement record
        
    Returns:
        dict: Status of each stage record creation
    """
    try:
        # Check if PNLStatement exists
        pnl = db.query(PNLStatement).filter(PNLStatement.id == pnl_id).first()
        if not pnl:
            raise HTTPException(status_code=404, detail="P&L statement not found")
        
        now = datetime.utcnow()
        status = {
            "revenue": {"created": False, "exists": False},
            "returns": {"created": False, "exists": False},
            "cogs": {"created": False, "exists": False},
            "operating_expenses": {"created": False, "exists": False}
        }
        
        # Check and create RevenueStream record if it doesn't exist
        revenue_stream = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_id).first()
        if revenue_stream:
            status["revenue"]["exists"] = True
        else:
            # Create empty revenue stream record
            revenue_stream = RevenueStream(
                pnl_id=pnl_id,
                data_json={},
                projected_titles={},
                created_at=now,
                updated_at=now
            )
            db.add(revenue_stream)
            try:
                db.commit()
                db.refresh(revenue_stream)
                status["revenue"]["created"] = True
                status["revenue"]["exists"] = True
            except Exception as commit_error:
                db.rollback()
                raise Exception(f"Failed to create revenue stream: {str(commit_error)}")
        
        # Check and create COGS record if it doesn't exist
        cogs_record = db.query(COGS).filter(COGS.pnl_id == pnl_id).first()
        if cogs_record:
            status["cogs"]["exists"] = True
        else:
            # Create empty COGS record
            cogs_record = COGS(
                pnl_id=pnl_id,
                data_json={},
                projected_titles={},
                created_at=now,
                updated_at=now
            )
            db.add(cogs_record)
            db.commit()
            db.refresh(cogs_record)
            status["cogs"]["created"] = True
            status["cogs"]["exists"] = True
        
        # Check and create OperatingExpenses record if it doesn't exist
        operating_expenses_record = db.query(OperatingExpenses).filter(
            OperatingExpenses.pnl_id == pnl_id
        ).first()
        if operating_expenses_record:
            status["operating_expenses"]["exists"] = True
        else:
            # Create empty OperatingExpenses record
            operating_expenses_record = OperatingExpenses(
                pnl_id=pnl_id,
                data_json={},
                projected_titles={},
                created_at=now,
                updated_at=now
            )
            db.add(operating_expenses_record)
            db.commit()
            db.refresh(operating_expenses_record)
            status["operating_expenses"]["created"] = True
            status["operating_expenses"]["exists"] = True
        
        # Check and create Return record if it doesn't exist
        # Note: Returns are linked to revenue_id, so we need the revenue_stream id
        if revenue_stream:
            return_record = db.query(Return).filter(Return.revenue_id == revenue_stream.id).first()
            if return_record:
                status["returns"]["exists"] = True
            else:
                # Create empty Return record
                return_record = Return(
                    revenue_id=revenue_stream.id,
                    data_json={},
                    projected_titles={},
                    created_at=now,
                    updated_at=now
                )
                db.add(return_record)
                db.commit()
                db.refresh(return_record)
                status["returns"]["created"] = True
                status["returns"]["exists"] = True
        
        # Note: We don't update PNLStatement flags - they remain as they were
        # Only creating the actual records for missing stages
        
        return {
            "success": True,
            "message": "All PnL stage records have been ensured",
            "status": status,
            "pnl_id": pnl_id
        }
        
    except Exception as e:
        db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in ensure_pnl_stage_records_exist for pnl_id {pnl_id}: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        raise HTTPException(status_code=500, detail=f"Failed to ensure PnL stage records: {str(e)}") 


def update_cogs_by_id(db: Session, cogs_id: int, data: dict) -> dict:
    """
    Update an existing COGS record by ID with new data.
    """
    try:
        # Get the COGS record
        cogs_record = db.query(COGS).filter(COGS.id == cogs_id).first()
        
        if not cogs_record:
            raise HTTPException(status_code=404, detail=f"COGS record with ID {cogs_id} not found")
        
        # Handle both response_json and data_json for backward compatibility
        data_json = data.get("data_json") or data.get("response_json", {})
        
        # Extract product names for selected_titles
        selected_titles = []
        if data_json and isinstance(data_json, dict):
            products = data_json.get("data", {}).get("products", [])
            if isinstance(products, list):
                selected_titles = [product.get("name") for product in products if isinstance(product, dict) and product.get("name")]
        
        # Update data_json and selected_titles fields
        cogs_record.data_json = data_json
        cogs_record.selected_titles = selected_titles
        cogs_record.updated_at = datetime.utcnow()
        
        # Commit changes
        db.commit()
        db.refresh(cogs_record)
        
        return {
            "success": True,
            "message": "COGS data updated successfully",
            "cogs_id": cogs_record.id,
            "data_json": cogs_record.data_json,
            "updated_at": cogs_record.updated_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update COGS record: {str(e)}")


def update_operating_expenses_by_id(db: Session, operating_expenses_id: int, data: dict) -> dict:
    """
    Update an existing operating expenses record by ID with new data.
    """
    try:
        # Get the operating expenses record
        operating_expenses_record = db.query(OperatingExpenses).filter(OperatingExpenses.id == operating_expenses_id).first()
        
        if not operating_expenses_record:
            raise HTTPException(status_code=404, detail=f"Operating expenses record with ID {operating_expenses_id} not found")
        
        # Handle both response_json and data_json for backward compatibility
        data_json = data.get("data_json") or data.get("response_json", {})
        
        # Extract product names for selected_titles
        selected_titles = []
        if data_json and isinstance(data_json, dict):
            products = data_json.get("data", {}).get("products", [])
            if isinstance(products, list):
                selected_titles = [product.get("name") for product in products if isinstance(product, dict) and product.get("name")]
        
        # Update data_json and selected_titles fields
        operating_expenses_record.data_json = data_json
        operating_expenses_record.selected_titles = selected_titles
        operating_expenses_record.updated_at = datetime.utcnow()
        
        # Commit changes
        db.commit()
        db.refresh(operating_expenses_record)
        
        return {
            "success": True,
            "message": "Operating expenses data updated successfully",
            "operating_expenses_id": operating_expenses_record.id,
            "data_json": operating_expenses_record.data_json,
            "updated_at": operating_expenses_record.updated_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update operating expenses record: {str(e)}") 
    """

    Ensure that all PnL statement stage records exist for the given pnl_id.

    Creates empty records for revenue, returns, cogs, and operating expenses if they don't exist.

    This function should be called after the revenue-titles-suggestions API completes successfully.

    

    Args:

        db: Database session

        pnl_id: ID of the PNLStatement record

        

    Returns:

        dict: Status of each stage record creation

    """

    try:

        # Check if PNLStatement exists

        pnl = db.query(PNLStatement).filter(PNLStatement.id == pnl_id).first()

        if not pnl:

            raise HTTPException(status_code=404, detail="P&L statement not found")

        

        now = datetime.utcnow()

        status = {

            "revenue": {"created": False, "exists": False},

            "returns": {"created": False, "exists": False},

            "cogs": {"created": False, "exists": False},

            "operating_expenses": {"created": False, "exists": False}

        }

        

        # Check and create RevenueStream record if it doesn't exist

        revenue_stream = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_id).first()

        if revenue_stream:

            status["revenue"]["exists"] = True

        else:

            # Create empty revenue stream record

            revenue_stream = RevenueStream(

                pnl_id=pnl_id,

                data_json={},

                projected_titles={},

                created_at=now,

                updated_at=now

            )

            db.add(revenue_stream)

            db.commit()

            db.refresh(revenue_stream)

            status["revenue"]["created"] = True

            status["revenue"]["exists"] = True

        

        # Check and create COGS record if it doesn't exist

        cogs_record = db.query(COGS).filter(COGS.pnl_id == pnl_id).first()

        if cogs_record:

            status["cogs"]["exists"] = True

        else:

            # Create empty COGS record

            cogs_record = COGS(

                pnl_id=pnl_id,

                data_json={},

                projected_titles={},

                created_at=now,

                updated_at=now

            )

            db.add(cogs_record)

            db.commit()

            db.refresh(cogs_record)

            status["cogs"]["created"] = True

            status["cogs"]["exists"] = True

        

        # Check and create OperatingExpenses record if it doesn't exist

        operating_expenses_record = db.query(OperatingExpenses).filter(

            OperatingExpenses.pnl_id == pnl_id

        ).first()

        if operating_expenses_record:

            status["operating_expenses"]["exists"] = True

        else:

            # Create empty OperatingExpenses record

            operating_expenses_record = OperatingExpenses(

                pnl_id=pnl_id,

                data_json={},

                projected_titles={},

                created_at=now,

                updated_at=now

            )

            db.add(operating_expenses_record)

            db.commit()

            db.refresh(operating_expenses_record)

            status["operating_expenses"]["created"] = True

            status["operating_expenses"]["exists"] = True

        

        # Check and create Return record if it doesn't exist

        # Note: Returns are linked to revenue_id, so we need the revenue_stream id

        if revenue_stream:

            return_record = db.query(Return).filter(Return.revenue_id == revenue_stream.id).first()

            if return_record:

                status["returns"]["exists"] = True

            else:

                # Create empty Return record

                return_record = Return(

                    revenue_id=revenue_stream.id,

                    data_json={},

                    projected_titles={},

                    created_at=now,

                    updated_at=now

                )

                db.add(return_record)

                db.commit()

                db.refresh(return_record)

                status["returns"]["created"] = True

                status["returns"]["exists"] = True

        

        # Note: We don't update PNLStatement flags - they remain as they were

        # Only creating the actual records for missing stages

        

        return {

            "success": True,

            "message": "All PnL stage records have been ensured",

            "status": status,

            "pnl_id": pnl_id

        }

        

    except Exception as e:

        db.rollback()

        raise HTTPException(status_code=500, detail=f"Failed to ensure PnL stage records: {str(e)}") 


def set_base_year(db: Session, user_id: int, base_year: int):
    """
    Set the base year for a user's basic details and update fin_year accordingly
    """
    try:
        # Find the user's basic details
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        
        if not user_details:
            raise HTTPException(status_code=404, detail="User basic details not found for this user")
        
        # Get current base_year to calculate the difference
        old_base_year = int(user_details.base_year) if user_details.base_year else base_year
        year_difference = base_year - old_base_year
        
        # Update the base_year
        user_details.base_year = str(base_year)
        
        # Update fin_year if it exists and year_difference is not zero
        if user_details.fin_year and year_difference != 0:
            try:
                # Parse the fin_year format: "01 Apr 2025 - 31 Mar 2026"
                from datetime import datetime
                import re
                
                # Split the fin_year string into start and end parts
                parts = user_details.fin_year.split(" - ")
                if len(parts) == 2:
                    start_date_str = parts[0].strip()
                    end_date_str = parts[1].strip()
                    
                    # Parse the dates (format: "DD MMM YYYY")
                    start_date = datetime.strptime(start_date_str, "%d %b %Y")
                    end_date = datetime.strptime(end_date_str, "%d %b %Y")
                    
                    # Add the year difference to both dates
                    new_start_date = start_date.replace(year=start_date.year + year_difference)
                    new_end_date = end_date.replace(year=end_date.year + year_difference)
                    
                    # Reconstruct the fin_year string with updated years
                    new_fin_year = f"{new_start_date.strftime('%d %b %Y')} - {new_end_date.strftime('%d %b %Y')}"
                    user_details.fin_year = new_fin_year
                    
            except (ValueError, AttributeError) as e:
                # If parsing fails, log the error but don't fail the entire operation
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to update fin_year when changing base year: {str(e)}. fin_year format may be invalid: {user_details.fin_year}")
        
        user_details.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(user_details)
        
        return {
            "success": True,
            "message": f"Base year set to {base_year} successfully",
            "base_year": base_year,
            "fin_year": user_details.fin_year,
            "user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to set base year: {str(e)}")


def get_base_year(db: Session, user_id: int):
    """
    Get the base year for a user's basic details
    """
    try:
        # Find the user's basic details
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        
        if not user_details:
            raise HTTPException(status_code=404, detail="User basic details not found for this user")
        
        base_year = user_details.base_year
        
        return {
            "success": True,
            "message": "Base year retrieved successfully",
            "base_year": int(base_year) if base_year else None,
            "user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get base year: {str(e)}")


def save_interest_expense(db: Session, user_id: int, interest_expense_data: dict):
    """
    Save interest expense data for a user's PNL statement
    """
    try:
        # Find the PNL statement for the user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        
        if not pnl_statement:
            raise HTTPException(status_code=404, detail="P&L statement not found for this user")
        
        # Get or create InterestExpense record
        interest_expense_record = db.query(InterestExpense).filter(InterestExpense.pnl_id == pnl_statement.id).first()
        
        if not interest_expense_record:
            # Create new record
            interest_expense_record = InterestExpense(
                pnl_id=pnl_statement.id,
                data_json=interest_expense_data,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(interest_expense_record)
        else:
            # Update existing record
            interest_expense_record.data_json = interest_expense_data
            interest_expense_record.updated_at = datetime.utcnow()
        
        # Update PNL statement flag
        pnl_statement.interest_expense = True
        pnl_statement.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(interest_expense_record)
        
        return {
            "success": True,
            "message": "Interest expense data saved successfully",
            "interest_expense_id": interest_expense_record.id,
            "data": interest_expense_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save interest expense: {str(e)}")


def get_interest_expense(db: Session, user_id: int):
    """
    Get interest expense data for a user's PNL statement
    """
    try:
        # Find the PNL statement for the user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        
        if not pnl_statement:
            raise HTTPException(status_code=404, detail="P&L statement not found for this user")
        
        # Get InterestExpense record
        interest_expense_record = db.query(InterestExpense).filter(InterestExpense.pnl_id == pnl_statement.id).first()
        
        if not interest_expense_record:
            raise HTTPException(status_code=404, detail="Interest expense record not found. Please save interest expense data first.")
        
        return {
            "success": True,
            "message": "Interest expense data retrieved successfully",
            "data": interest_expense_record.data_json,
            "interest_expense_id": interest_expense_record.id,
            "created_at": interest_expense_record.created_at.isoformat() if interest_expense_record.created_at else None,
            "updated_at": interest_expense_record.updated_at.isoformat() if interest_expense_record.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get interest expense: {str(e)}")


def generate_tax_rate(db: Session, user_id: int):
    """
    Generate effective corporate tax rate using AI and save to IncomeBeforeTaxes table
    """
    try:
        # Find the PNL statement for the user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        
        if not pnl_statement:
            raise HTTPException(status_code=404, detail="P&L statement not found for this user")
        
        # Get user basic details for AI context
        user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
        if not user_details:
            raise HTTPException(status_code=404, detail="User basic details not found. Please complete your basic details first.")
        
        # Import prompt function
        from app.prompts.pnl import get_tax_rate_prompt
        
        # Get prompt from prompts module
        ai_prompt = get_tax_rate_prompt(user_details)
        
        # Import OpenAI client
        from app.utils.openai_client import get_openai_completion
        
        # Call AI service
        try:
            ai_response = get_openai_completion(ai_prompt, {
                "max_tokens": 50,
                "temperature": 0.1  # Low temperature for consistent tax rate
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"AI service failed: {str(e)}")
        
        if not ai_response:
            raise HTTPException(status_code=500, detail="AI service returned empty response")
        
        # Extract percentage from AI response
        try:
            # Clean the response and extract percentage
            tax_rate_str = ai_response.strip().replace('%', '').replace('percent', '').strip()
            tax_rate = float(tax_rate_str)
            
            # Basic validation - only check if it's a valid number
            if tax_rate < 0:
                raise ValueError("Tax rate cannot be negative")
                
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=500, detail=f"AI returned invalid tax rate format: '{ai_response}'. Error: {str(e)}")
        
        return {
            "success": True,
            "message": f"Tax rate generated successfully: {tax_rate}%",
            "tax_rate": tax_rate
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Tax rate generation failed: {str(e)}")


def save_income_before_taxes(db: Session, user_id: int, income_before_taxes_data: dict):
    """
    Save income before taxes data for a user's PNL statement
    """
    try:
        # Find the PNL statement for the user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        
        if not pnl_statement:
            raise HTTPException(status_code=404, detail="P&L statement not found for this user")
        
        # Get or create IncomeBeforeTaxes record
        income_before_taxes_record = db.query(IncomeBeforeTaxes).filter(IncomeBeforeTaxes.pnl_id == pnl_statement.id).first()
        
        if not income_before_taxes_record:
            # Create new record
            income_before_taxes_record = IncomeBeforeTaxes(
                pnl_id=pnl_statement.id,
                data_json=income_before_taxes_data,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(income_before_taxes_record)
        else:
            # Update existing record
            income_before_taxes_record.data_json = income_before_taxes_data
            income_before_taxes_record.updated_at = datetime.utcnow()
        
        # Update PNL statement flag
        pnl_statement.income_before_taxes = True
        pnl_statement.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(income_before_taxes_record)
        
        return {
            "success": True,
            "message": "Income before taxes data saved successfully",
            "income_before_taxes_id": income_before_taxes_record.id,
            "data": income_before_taxes_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save income before taxes: {str(e)}")


def get_income_before_taxes(db: Session, user_id: int):
    """
    Get income before taxes data for a user's PNL statement
    """
    try:
        # Find the PNL statement for the user
        pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        
        if not pnl_statement:
            raise HTTPException(status_code=404, detail="P&L statement not found for this user")
        
        # Get IncomeBeforeTaxes record
        income_before_taxes_record = db.query(IncomeBeforeTaxes).filter(IncomeBeforeTaxes.pnl_id == pnl_statement.id).first()
        
        if not income_before_taxes_record:
            raise HTTPException(status_code=404, detail="Income before taxes record not found. Please save income before taxes data first.")
        
        return {
            "success": True,
            "message": "Income before taxes data retrieved successfully",
            "data": income_before_taxes_record.data_json,
            "income_before_taxes_id": income_before_taxes_record.id,
            "created_at": income_before_taxes_record.created_at.isoformat() if income_before_taxes_record.created_at else None,
            "updated_at": income_before_taxes_record.updated_at.isoformat() if income_before_taxes_record.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get income before taxes: {str(e)}")