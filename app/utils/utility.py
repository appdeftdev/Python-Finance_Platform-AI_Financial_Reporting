from fastapi import HTTPException, Header, Depends
import json
from typing import Optional
from app.core.database import get_db
from sqlalchemy.orm import Session
from app.models.models import PNLStatement, UserProgress, UserBasicDetails, RevenueStream, Return, COGS, OperatingExpenses, DepreciationNAmortisation, Skipped, OtherIncome, BalanceSheet, WorkingCapital, Inventory, InterestExpense, IncomeBeforeTaxes, CashFlowStatement, OtherExpense, Valuation, BSRecords
from app.core.config import settings
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.hash import bcrypt
from app.prompts.pnl import get_spelling_correction_prompt
from app.utils.openai_client import get_openai_completion
from app.models.admin_models import Admin
ALGORITHM = "HS256"
REFRESH_TOKEN_EXPIRE_DAYS = 7

# SPELLING_FIELDS = ["industry", "city", "country", "competitors"]


# def analyze_and_prepare_basic_details(payload: dict) -> tuple[dict, dict]:
#     """
#     Returns:
#     - corrected_json (dict) → for JSONB column
#     - final_column_values (dict) → values to store in DB columns
#     """

#     corrected_json = {}
#     final_column_values = {}

#     for key, value in payload.items():
#         corrected_json[key] = {
#             "input": value.strip() if isinstance(value, str) else value,
#             "corrected": ""
#         }
#         final_column_values[key] = value

#     ai_payload = {
#         key: corrected_json[key]["input"]
#         for key in SPELLING_FIELDS
#         if key in corrected_json
#         and isinstance(corrected_json[key]["input"], str)
#         and corrected_json[key]["input"]
#     }

#     if not ai_payload:
#         return corrected_json, final_column_values

#     prompt = get_spelling_correction_prompt(ai_payload)

#     try:
#         ai_response = get_openai_completion(
#             prompt,
#             {"temperature": 0, "max_tokens": 300}
#         )

#         ai_corrected = json.loads(ai_response)

#         for key, corrected_value in ai_corrected.items():
#             if key in corrected_json:
#                 corrected_json[key]["corrected"] = corrected_value
#                 final_column_values[key] = corrected_value   

#     except Exception:
#         pass

#     return corrected_json, final_column_values



def create_access_token(user_data: dict):
    to_encode = user_data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_data: dict):
    to_encode = user_data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user_from_token(token: str):
    payload = decode_token(token)
    user_data = {
        "id": payload.get("sub"),
        "email": payload.get("email"),
        "name": payload.get("name")
    }
    return user_data

def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is required")
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authorization scheme")
        
        user_data = get_current_user_from_token(token)
        return user_data
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


def get_current_admin_from_token(token: str):
    payload = decode_token(token)

    admin_data = {
        "id": payload.get("sub"),
        "email": payload.get("email"),
        "name": payload.get("name")
    }

    return admin_data


def get_current_admin(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is required")

    try:
        scheme, token = authorization.split()

        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authorization scheme")

        admin_data = get_current_admin_from_token(token)

        admin_id = admin_data.get("id")
        if not admin_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        # 🔐 Verify admin exists in DB
        admin = db.query(Admin).filter(Admin.id == admin_id).first()
        if not admin:
            raise HTTPException(status_code=401, detail="Admin not found")

        return {
            "id": admin.id,
            "email": admin.email,
            "name": admin.name
        }

    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def get_topic_record_id(subject: str, topic: str, current_user: dict, db: Session) -> int:
    """
    Get the record ID for a specific subject and topic for the current user.
    
    Args:
        subject: Currently only "pnl" (extensible for future subjects)
        topic: One of the PNL topics (revenue, returns, cogs, operating expenses, other income, depreciation and amortisation)
        current_user: Current authenticated user data
        db: Database session
    
    Returns:
        int: The ID of the topic record
        
    Raises:
        HTTPException: If subject/topic not found or invalid
    """
    user_id = int(current_user["id"])
    
    # Get user's PNL statement
    pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
    if not pnl_statement:
        raise HTTPException(status_code=404, detail="PNL statement not found for user")
    
    pnl_id = pnl_statement.id
    
    # Map topics to their respective models and table names
    topic_mapping = {
        "revenue": (RevenueStream, "revenue"),
        "returns": (Return, "returns"),
        "cogs": (COGS, "cogs"),
        "operating expenses": (OperatingExpenses, "operating_expenses"),
        "other income": (OtherIncome, "other_income"),
        "other expense": (OtherExpense, "other_expense"),
        "depreciation and amortisation": (DepreciationNAmortisation, "depreciation_n_amortisation")
    }
    
    # Validate subject
    if subject.lower() != "pnl":
        raise HTTPException(status_code=400, detail=f"Invalid subject: {subject}. Currently only 'pnl' is supported.")
    
    # Validate topic
    if topic.lower() not in topic_mapping:
        raise HTTPException(status_code=400, detail=f"Invalid topic: {topic}. Valid topics are: {list(topic_mapping.keys())}")
    
    # Get the model and table name for the topic
    model_class, table_name = topic_mapping[topic.lower()]
    
    # Query the appropriate table to get the record for this PNL statement
    record = db.query(model_class).filter(model_class.pnl_id == pnl_id).first()
    
    if not record:
        raise HTTPException(status_code=404, detail=f"{topic} record not found for user")
    
    return record.id


def create_all_pnl_records(current_user: dict, db: Session) -> dict:
    """
    Create all PNL statement's table records and Balance Sheet records for the current user.
    Creates empty records for revenue, returns, cogs, operating expenses, other income, depreciation and amortisation, and balance sheet.
    
    Args:
        current_user: Current authenticated user data
        db: Database session
    
    Returns:
        dict: Dictionary containing all created record IDs
        
    Raises:
        HTTPException: If PNL statement not found or creation fails
    """
    user_id = int(current_user["id"])
    
    # Get user's PNL statement
    pnl_statement = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
    if not pnl_statement:
        raise HTTPException(status_code=404, detail="PNL statement not found for user")
    
    pnl_id = pnl_statement.id
    current_time = datetime.utcnow()
    
    created_records = {}
    
    try:
        # Create RevenueStream record if it doesn't exist
        revenue_record = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_id).first()
        if not revenue_record:
            revenue_record = RevenueStream(
                pnl_id=pnl_id,
                data_json={},
                projected_titles=[],
                selected_titles=[],
                created_at=current_time,
                updated_at=current_time
            )
            db.add(revenue_record)
            created_records["revenue"] = "created"
        else:
            created_records["revenue"] = "already_exists"
        
        # Create Return record if it doesn't exist
        return_record = db.query(Return).filter(Return.pnl_id == pnl_id).first()
        if not return_record:
            return_record = Return(
                pnl_id=pnl_id,
                data_json={},
                projected_titles=[],
                created_at=current_time,
                updated_at=current_time
            )
            db.add(return_record)
            created_records["returns"] = "created"
        else:
            created_records["returns"] = "already_exists"
        
        # Create COGS record if it doesn't exist
        cogs_record = db.query(COGS).filter(COGS.pnl_id == pnl_id).first()
        if not cogs_record:
            cogs_record = COGS(
                pnl_id=pnl_id,
                data_json={},
                projected_titles=[],
                selected_titles=[],
                created_at=current_time,
                updated_at=current_time
            )
            db.add(cogs_record)
            created_records["cogs"] = "created"
        else:
            created_records["cogs"] = "already_exists"
        
        # Create OperatingExpenses record if it doesn't exist
        operating_expenses_record = db.query(OperatingExpenses).filter(OperatingExpenses.pnl_id == pnl_id).first()
        if not operating_expenses_record:
            operating_expenses_record = OperatingExpenses(
                pnl_id=pnl_id,
                data_json={},
                projected_titles=[],
                selected_titles=[],
                created_at=current_time,
                updated_at=current_time
            )
            db.add(operating_expenses_record)
            created_records["operating_expenses"] = "created"
        else:
            created_records["operating_expenses"] = "already_exists"
        
        # Create OtherIncome record if it doesn't exist
        other_income_record = db.query(OtherIncome).filter(OtherIncome.pnl_id == pnl_id).first()
        if not other_income_record:
            other_income_record = OtherIncome(
                pnl_id=pnl_id,
                data_json={},
                projected_titles=[],
                selected_titles=[],
                created_at=current_time,
                updated_at=current_time
            )
            db.add(other_income_record)
            created_records["other_income"] = "created"
        else:
            created_records["other_income"] = "already_exists"

        # Create OtherExpense record if it doesn't exist
        other_expense_record = db.query(OtherExpense).filter(OtherExpense.pnl_id == pnl_id).first()
        if not other_expense_record:
            other_expense_record = OtherExpense(
                pnl_id=pnl_id,
                data_json={},
                projected_titles=[],
                selected_titles=[],
                created_at=current_time,
                updated_at=current_time
            )
            db.add(other_expense_record)
            created_records["other_expense"] = "created"
        else:
            created_records["other_expense"] = "already_exists"
        
        # Create DepreciationNAmortisation record if it doesn't exist
        depreciation_record = db.query(DepreciationNAmortisation).filter(DepreciationNAmortisation.pnl_id == pnl_id).first()
        if not depreciation_record:
            depreciation_record = DepreciationNAmortisation(
                pnl_id=pnl_id,
                assets_input={},
                data_json={},
                created_at=current_time,
                updated_at=current_time
            )
            db.add(depreciation_record)
            created_records["depreciation_and_amortisation"] = "created"
        else:
            created_records["depreciation_and_amortisation"] = "already_exists"
        
        # Create InterestExpense record if it doesn't exist
        interest_expense_record = db.query(InterestExpense).filter(InterestExpense.pnl_id == pnl_id).first()
        if not interest_expense_record:
            interest_expense_record = InterestExpense(
                pnl_id=pnl_id,
                data_json={},
                created_at=current_time,
                updated_at=current_time
            )
            db.add(interest_expense_record)
            created_records["interest_expense"] = "created"
        else:
            created_records["interest_expense"] = "already_exists"
        
        # Create IncomeBeforeTaxes record if it doesn't exist
        income_before_taxes_record = db.query(IncomeBeforeTaxes).filter(IncomeBeforeTaxes.pnl_id == pnl_id).first()
        if not income_before_taxes_record:
            income_before_taxes_record = IncomeBeforeTaxes(
                pnl_id=pnl_id,
                data_json={},
                created_at=current_time,
                updated_at=current_time
            )
            db.add(income_before_taxes_record)
            created_records["income_before_taxes"] = "created"
        else:
            created_records["income_before_taxes"] = "already_exists"
        
        # Commit PnL records first
        db.commit()
        
        # Create Balance Sheet records separately
        # balance_sheet_result = create_balance_sheet_records(user_id, db)
        
        return {
            "success": True,
            "message": "PNL and Balance Sheet records processed successfully",
            "pnl_id": pnl_id,
            "created_records": created_records,
            # "balance_sheet_records": balance_sheet_result,
            "created_at": current_time.isoformat()
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create PNL and Balance Sheet records: {str(e)}")


def create_balance_sheet_records(user_id: int, db: Session) -> dict:
    """
    Create all Balance Sheet table records for the current user.
    Creates empty records for working capital and inventory.
    
    Args:
        user_id: User ID
        db: Database session
    
    Returns:
        dict: Dictionary containing all created record IDs
        
    Raises:
        HTTPException: If Balance Sheet not found or creation fails
    """
    current_time = datetime.utcnow()
    created_records = {}
    
    try:
        # Create BalanceSheet record if it doesn't exist
        balance_sheet_record = db.query(BalanceSheet).filter(BalanceSheet.user_id == user_id).first()
        if not balance_sheet_record:
            balance_sheet_record = BalanceSheet(
                user_id=user_id,
                working_capital=False,
                inventory=False,
                bs_records=False,
                cash_flow_statement=False,
                created_at=current_time,
                updated_at=current_time
            )
            db.add(balance_sheet_record)
            db.commit()
            db.refresh(balance_sheet_record)
            created_records["balance_sheet"] = "created"
        else:
            created_records["balance_sheet"] = "already_exists"
        
        balance_sheet_id = balance_sheet_record.id
        
        # Create WorkingCapital record if it doesn't exist
        working_capital_record = db.query(WorkingCapital).filter(WorkingCapital.balance_sheet_id == balance_sheet_id).first()
        if not working_capital_record:
            working_capital_record = WorkingCapital(
                balance_sheet_id=balance_sheet_id,
                data_json={},
                created_at=current_time,
                updated_at=current_time
            )
            db.add(working_capital_record)
            created_records["working_capital"] = "created"
        else:
            created_records["working_capital"] = "already_exists"
        
        # Create Inventory record if it doesn't exist
        inventory_record = db.query(Inventory).filter(Inventory.balance_sheet_id == balance_sheet_id).first()
        if not inventory_record:
            inventory_record = Inventory(
                balance_sheet_id=balance_sheet_id,
                data_json={},
                created_at=current_time,
                updated_at=current_time
            )
            db.add(inventory_record)
            created_records["inventory"] = "created"
        else:
            created_records["inventory"] = "already_exists"
        
        # Create BSRecords record if it doesn't exist
        bs_records_record = db.query(BSRecords).filter(BSRecords.balance_sheet_id == balance_sheet_id).first()
        if not bs_records_record:
            # Get user basic details to extract base_year and projections
            from app.models.models import UserBasicDetails
            user_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
            
            if user_details:
                # Create structured bs_records data using utility function
                bs_records_data = create_bs_records_data_json(
                    base_year=user_details.base_year or str(datetime.now().year),
                    projections=user_details.projections or 5
                )
            else:
                # Fallback to default structure if user details not found
                bs_records_data = create_bs_records_data_json(
                    base_year=str(datetime.now().year),
                    projections=5
                )
            
            bs_records_record = BSRecords(
                balance_sheet_id=balance_sheet_id,
                data_json=bs_records_data,
                created_at=current_time,
                updated_at=current_time
            )
            db.add(bs_records_record)
            created_records["bs_records"] = "created"
        else:
            created_records["bs_records"] = "already_exists"

        # Create cashflow record if it doesn't exist
        cashflow_record = db.query(CashFlowStatement).filter(CashFlowStatement.balance_sheet_id == balance_sheet_id).first()
        if not cashflow_record:
            cashflow_record = CashFlowStatement(
                balance_sheet_id=balance_sheet_id,
                data_json={},
                created_at=current_time,
                updated_at=current_time
            )
            db.add(cashflow_record)
            created_records["cashflow"] = "created"
        else:
            created_records["cashflow"] = "already_exists"

        # Commit all changes
        db.commit()
        
        return {
            "success": True,
            "message": "Balance Sheet records processed successfully",
            "balance_sheet_id": balance_sheet_id,
            "created_records": created_records,
            "created_at": current_time.isoformat()
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create Balance Sheet records: {str(e)}")


def create_valuation_record(user_id: int, db: Session) -> dict:
    """
    Create an empty Valuation record for the user if it does not exist.
    """

    current_time = datetime.utcnow()

    try:
        valuation_record = db.query(Valuation).filter(
            Valuation.user_id == user_id
        ).first()

        if not valuation_record:
            valuation_record = Valuation(
                user_id=user_id,
                data_json={},
                projected_titles={},
                selected_titles={},
                created_at=current_time,
                updated_at=current_time
            )

            db.add(valuation_record)
            db.commit()
            db.refresh(valuation_record)

            return {
                "success": True,
                "message": "Valuation record created successfully",
                "valuation_id": valuation_record.id,
                "status": "created",
                "created_at": current_time.isoformat()
            }

        return {
            "success": True,
            "message": "Valuation record already exists",
            "valuation_id": valuation_record.id,
            "status": "already_exists",
            "created_at": valuation_record.created_at.isoformat() if valuation_record.created_at else None
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create valuation record: {str(e)}"
        )


def create_bs_records_data_json(base_year: str, projections: int) -> dict:
    """
    Create the initial JSON structure for bs_records data_json field.
    Generates years array based on base_year and projections.
    
    Args:
        base_year: Base year as string (e.g., "2025")
        projections: Number of projection years
    
    Returns:
        dict: Structured bs_records data with years array and empty sections
    """
    try:
        # Convert base_year to integer and generate years array
        start_year = int(base_year)
        years = [str(start_year + i) for i in range(projections)]
        
        # Create the structured bs_records data
        bs_records_data = {
            "Years": years,
            "Assets": {
                "CurrentAssets": {},
                "FixedAssets": {}
            },
            "Liabilities": {
                "ShortTermLiabilities": {},
                "LongTermLiabilities": {}
            },
            "ShareholdersEquity": {
                "ShareCapital": {},
                "RetainedEarnings": {}
            },
            "LiabilitiesAndEquity": {
                "TotalLiabilitiesAndEquity": {},
                "Check": {}
            }
        }
        
        return bs_records_data
        
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to create bs_records data structure: {str(e)}")
        # Return default structure with generic years if base_year is invalid
        years = [f"Y{i+1}" for i in range(projections)]
        return {
            "Years": years,
            "Assets": {
                "CurrentAssets": {},
                "FixedAssets": {}
            },
            "Liabilities": {
                "ShortTermLiabilities": {},
                "LongTermLiabilities": {}
            },
            "ShareholdersEquity": {
                "ShareCapital": {},
                "RetainedEarnings": {}
            },
            "LiabilitiesAndEquity": {
                "TotalLiabilitiesAndEquity": {},
                "Check": {}
            }
        }


def merge_bs_records_data(existing_data: dict, new_data: dict) -> dict:
    """
    Merge new bs_records data with existing data based on root keys.
    Supports selective updates for Assets, Liabilities, ShareholdersEquity, LiabilitiesAndEquity.
    
    Args:
        existing_data: Current bs_records data from database
        new_data: New data to merge (can contain any root keys)
    
    Returns:
        dict: Merged bs_records data
    """
    try:
        # Start with existing data
        merged_data = existing_data.copy() if existing_data else {}
        
        # Ensure Years is always updated if provided
        if "Years" in new_data:
            merged_data["Years"] = new_data["Years"]
        
        # Define the root keys that can be updated
        root_keys = ["Assets", "Liabilities", "ShareholdersEquity", "LiabilitiesAndEquity"]
        
        # Merge each root key if present in new_data
        for root_key in root_keys:
            if root_key in new_data:
                if root_key not in merged_data:
                    merged_data[root_key] = {}
                
                # Merge the sub-sections within each root key
                for sub_key, sub_data in new_data[root_key].items():
                    merged_data[root_key][sub_key] = sub_data
        
        return merged_data
        
    except Exception as e:
        logger.error(f"Failed to merge bs_records data: {str(e)}")
        # Return existing data if merge fails
        return existing_data if existing_data else {}


## TEST working on it

def create_cashflow_data_json() -> dict:
    """
    Create a structured template for Cashflow data.
    Divides cashflow into three sections:
    - Operating activities
    - Investing activities
    - Financing activities
    
    Returns:
        dict: JSON structure with placeholders for all key cashflow items.
    """
    try:
        return {
            "cashflow_from_operating_activities": {
                "net_income": "",                        # From P&L
                "depreciation_and_amortisation": "",     # From P&L
                "taxes_payable": "",                     # From P&L
                "accounts_payable": "",                  # From Working Capital
                "accrued_liabilities": "",               # From Balance Sheet (short + long term)
                "accounts_receivable": "",               # From Working Capital
                "change_in_inventory": "",               # From Inventory
                "prepaid_expenses": ""                   # User input (client fills)
            },
            "cashflow_from_investing_activities": {
                "gross_fixed_assets": ""                 # From CAPEX / Balance Sheet
            },
            "cashflow_from_financing_activities": {
                "issuance_of_share_capital": "",         # User input (client fills)
                "short_term_debt": "",                   # From Debt Repayment Schedule
                "long_term_debt": ""                     # From Debt Repayment Schedule
            }
        }

    except Exception as e:
        raise Exception(f"Failed to create cashflow data JSON: {str(e)}")


def create_working_capital_data_json(
    receivable_days: int,
    credit_sales_percentage: str,
    projections: int = 5
) -> dict:
    """
    Create the consolidated JSON structure for working capital data_json field.
    Contains both receivables and payables calculations with only AI-generated fields filled.
    
    Args:
        receivable_days: Number of receivable days (DSO) from AI
        credit_sales_percentage: Percentage of sales on credit from AI (e.g., "50%")
        projections: Number of projection years (default 5)
    
    Returns:
        dict: Working capital data_json structure with AI fields populated
    """
    return {
        "ReceivablesCalculation": {
            "years": [],  # Empty - not filled by AI
            "NumberOfReceivableDays": [receivable_days] * projections,  # AI generated
            "PercentageOfSalesOnCredit": [credit_sales_percentage] * projections,  # AI generated
            "ClosingTradeDebtorsTradeReceivables": [],  # Empty - not filled by AI
            "TotalNumberOfDaysInYear": []  # Empty - not filled by AI
        },
        "PayablesCalculation": {
            "Years": [],  # Empty - not filled by AI
            "NumberOfPayableDays": [],  # Empty - not filled by AI
            "ClosingTradePayablesCreditors": []  # Empty - not filled by AI
        }
    }


def merge_working_capital_data(
    existing_data: dict,
    new_section: str,
    new_data: dict
) -> dict:
    """
    Merge new section data into existing working capital data_json.
    Preserves existing sections while updating the specified section.
    
    Args:
        existing_data: Existing data_json from database
        new_section: Section to update ("ReceivablesCalculation" or "PayablesCalculation")
        new_data: New data to merge for the specified section
    
    Returns:
        dict: Updated data_json with merged section
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"merge_working_capital_data called with:")
    logger.info(f"  existing_data: {existing_data}")
    logger.info(f"  new_section: {new_section}")
    logger.info(f"  new_data: {new_data}")
    
    # Start with existing data or create new structure
    if not existing_data:
        existing_data = {
            "ReceivablesCalculation": {},
            "PayablesCalculation": {}
        }
        logger.info("Created new structure with empty sections")
    
    # Ensure both sections exist
    if "ReceivablesCalculation" not in existing_data:
        existing_data["ReceivablesCalculation"] = {}
        logger.info("Added empty ReceivablesCalculation section")
    if "PayablesCalculation" not in existing_data:
        existing_data["PayablesCalculation"] = {}
        logger.info("Added empty PayablesCalculation section")
    
    # Update the specified section
    existing_data[new_section] = new_data
    logger.info(f"Updated {new_section} section with new data")
    logger.info(f"Final merged data: {existing_data}")
    
    return existing_data

def update_bs_cash_from_beginning_cash(
    bs_records_record,
    beginning_cash: dict
) -> dict:
    """
    Update BS Records -> Assets -> CurrentAssets -> CashOrBankBalance
    using Beginning Cash as an OBJECT (Y1, Y2, ...).

    Example:
    "CashOrBankBalance": {"Y1": 1000, "Y2": 2000}
    """
    existing_bs = bs_records_record.data_json or {}
    updated_bs = existing_bs.copy()
    updated_bs.setdefault("Assets", {})
    updated_bs["Assets"].setdefault("CurrentAssets", {})
    updated_bs["Assets"]["CurrentAssets"]["CashOrBankBalance"] = beginning_cash
    return updated_bs