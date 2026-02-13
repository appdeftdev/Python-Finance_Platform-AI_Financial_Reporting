from jose import JWTError, jwt
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.models import User,PNLStatement, UserProgress, UserBasicDetails, RevenueStream, Return, COGS, OperatingExpenses, DepreciationNAmortisation, Skipped, OtherIncome, BalanceSheet, WorkingCapital, Inventory, InterestExpense, IncomeBeforeTaxes, CashFlowStatement, OtherExpense,BSRecords
from passlib.hash import bcrypt
from app.core.config import settings
from fastapi import HTTPException
from app.utils.utility import create_access_token, create_refresh_token, get_current_user_from_token
# from app.tasks.formula_generation_tasks import generate_pnl_formulas  # CELERY REMOVED
from app.utils.openai_client import get_openai_completion
from app.prompts.pnl import (
    get_revenue_title_suggestions_prompt,
    get_product_growth_rate_prompt,
    validate_product_name_prompt,
    get_cogs_title_suggestions_prompt,
    validate_cogs_product_name_prompt,
    get_cogs_title_suggestions_with_revenue_context_prompt,
    get_cogs_product_growth_rate_prompt,
    get_operating_expenses_title_suggestions_prompt,
    get_operating_expense_growth_rate_prompt,
    get_depreciation_assets_prompt,
    validate_operating_expense_product_name_prompt,
    get_depreciation_details_prompt,
    get_other_charges_title_suggestions_prompt,
    get_other_expense_title_suggestions_prompt,
    get_tax_rate_prompt,
    NUMBER_OF_SUGGESTIONS
)
import logging
import json

logger = logging.getLogger(__name__)

# Global configuration for AI-generated financial details
NUMBER_OF_PROJECTIONS = 5

def initialize_user_records(db: Session, user_id: int):
    """
    Initialize UserProgress and PNLStatement records for a newly registered user
    All stages are set to False by default
    """
    try:
        # Create UserProgress record with all stages False
        user_progress = UserProgress(
            user_id=user_id,
            user_basic_details=False,
            pnl_statements=False,
            balance_sheet=False,
            # cash_flow_statement=False,
            valuation=False,
            charts_n_insights=False
        )
        db.add(user_progress)
        
        # Create PNLStatement record with all stages False
        pnl_statement = PNLStatement(
            user_id=user_id,
            revenue=False,
            cogs=False,
            returns=False,
            operating_expenses=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(pnl_statement)
        
        
        # Commit all records
        db.commit()
        
        logger.info(f"Successfully initialized UserProgress and PNLStatement records for user {user_id}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to initialize user records for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize user records: {str(e)}")

def update_user_financial_details(db: Session, user_id: int) -> dict:
    """
    Get user basic details and generate/update financial details using AI
    """
    # Check if user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user basic details
    basic_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
    if not basic_details:
        raise HTTPException(status_code=404, detail="Basic details not found for this user")
    
    # Use AI to generate financial details
    financial_details = generate_financial_details_with_ai(basic_details)
    
    # Update the basic details with financial information (when AI provides them)
    basic_details.fin_year = financial_details["fin_year"]
    basic_details.projections = financial_details["projections"]
    basic_details.currency = financial_details["currency"]
    basic_details.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(basic_details)
    
    # Update user progress to mark user_basic_details as completed
    update_user_basic_details_progress(db, user_id)
    
    return {
        "basic_details": {
            "company_name": basic_details.company_name,
            "industry": basic_details.industry,
            "city": basic_details.city,
            "country": basic_details.country,
            "company_size": basic_details.company_size,
            "competitors": basic_details.competitors,
            "business_model": basic_details.business_model
        },
        "financial_details": financial_details,
        "note": "Financial details will be populated by AI based on business context"
    }

def update_user_basic_details_progress(db: Session, user_id: int):
    """
    Update user_basic_details progress to True after financial details are successfully generated
    """
    try:
        # Get user progress record
        user_progress = db.query(UserProgress).filter(UserProgress.user_id == user_id).first()
        if not user_progress:
            raise HTTPException(status_code=404, detail="User progress not found")
        
        # Update the user_basic_details progress to True
        user_progress.user_basic_details = True
        user_progress.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Successfully updated user_basic_details progress to True for user {user_id}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update user_basic_details progress for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update user progress: {str(e)}")

def register_user(db: Session, name: str, email: str, password: str):
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(
                status_code=400, 
                detail="User with this email already exists. Please use a different email or try logging in."
            )
        
        hashed_password = bcrypt.hash(password)
        user = User(name=name, email=email, password=hashed_password)
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Initialize UserProgress and PNLStatement records with all stages False
        initialize_user_records(db, user.id)
        
        return user
    except HTTPException:
        # Re-raise HTTP exceptions (like duplicate user)
        raise
    except Exception as e:
        # If initialization fails, we need to rollback the user creation too
        db.rollback()
        logger.error(f"Failed to register user {email}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if user and bcrypt.verify(password, user.password):
        user_data = {
            "sub": str(user.id),
            "email": user.email,
            "name": user.name
        }
        access_token = create_access_token(user_data)
        refresh_token = create_refresh_token(user_data)
        return user, access_token, refresh_token
    return None, None, None

def create_user_basic_details(db: Session, user_id: int, basic_details_data: dict):
    # Check if user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if basic details already exist for this user
    existing_details = db.query(UserBasicDetails).filter(UserBasicDetails.user_id == user_id).first()
    if existing_details:
        raise HTTPException(status_code=400, detail="Basic details already exist for this user")

    business_model = basic_details_data.get("business_model")

    if isinstance(business_model, list):
        business_model = ", ".join(business_model)  
    
    # Generate financial details using AI before creating the record
    financial_details = generate_financial_details_with_ai_from_data(basic_details_data)
    
    # Create new basic details with AI-generated financial information
    basic_details = UserBasicDetails(
        user_id=user_id,
        company_name=basic_details_data["company_name"],
        industry=basic_details_data["industry"],
        city=basic_details_data["city"],
        country=basic_details_data["country"],
        company_size=basic_details_data["company_size"],
        competitors=basic_details_data["competitors"],
        business_model=business_model,
        fin_year=financial_details["fin_year"],
        projections=financial_details["projections"],
        currency=financial_details["currency"],
        base_year=basic_details_data["base_year"],  # Set base_year to current year by default
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(basic_details)
    db.commit()
    db.refresh(basic_details)
    
    # Update user progress to mark user_basic_details as completed
    update_user_basic_details_progress(db, user_id)
    
    # CELERY REMOVED - Background task to generate PnL formulas
    # try:
    #     logger.info(f"Triggering PnL formula generation for user {user_id}")
    #     generate_pnl_formulas.delay(user_id)
    #     logger.info(f"PnL formula generation task queued successfully for user {user_id}")
    # except Exception as e:
    #     logger.error(f"Failed to queue PnL formula generation task for user {user_id}: {str(e)}")
    #     # Don't fail the basic details creation if Celery task fails
    
    return basic_details

def generate_financial_details_with_ai_from_data(basic_details_data: dict) -> dict:
    """
    Use AI to generate financial details based on basic details data before saving to DB
    """
    try:
        # Get current date for context
        from datetime import datetime
        current_date = datetime.now()
        current_date_str = current_date.strftime("%d %b %Y")
        prompt = f"""
        IMPORTANT: Today's date is {current_date_str}. Generate the CURRENT financial year based on this date.

        Based on the following business details, generate appropriate financial year, projections, and currency:

        Company Details:
        - Industry: {basic_details_data['industry']}
        - Country: {basic_details_data['country']}
        - City: {basic_details_data['city']}
        - Company Size: {basic_details_data['company_size']}
        - Business Model: {basic_details_data['business_model']}

        Please provide the following in JSON format:
        1. fin_year: CURRENT financial year in format "DD MMM YYYY - DD MMM YYYY" (based on today's date: {current_date_str})
        2. projections: Number of years for projections (default: {NUMBER_OF_PROJECTIONS} years)
        3. currency: Appropriate currency code (ISO 3-letter code like USD, EUR, INR, etc.)

        CRITICAL: Since today is {current_date_str}, the financial year should be current (e.g., if today is in 2025, return 2024-2025 or 2025-2026 depending on the fiscal year cycle).
        Do NOT return outdated financial years like 2022-2023.

        Consider:
        - Country-specific fiscal year start dates
        - Current date context ({current_date_str})
        - Industry standards for projection periods
        - Local currency for the business location
        - Default projection period is {NUMBER_OF_PROJECTIONS} years

        Return only valid JSON with these exact field names: fin_year, projections, currency
        """

        # Call OpenAI service
        ai_response = get_openai_completion(prompt, {
            "max_tokens": 300,
            "temperature": 0.3  # Lower temperature for more consistent financial data
        })

        # Parse AI response
        try:
            # Clean the response and extract JSON
            response_text = ai_response.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            financial_details = json.loads(response_text.strip())
            
            # Validate required fields
            required_fields = ['fin_year', 'projections', 'currency']
            for field in required_fields:
                if field not in financial_details:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate projections is a number
            if not isinstance(financial_details['projections'], int):
                financial_details['projections'] = int(financial_details['projections'])
            
            logger.info(f"AI successfully generated financial details: {financial_details}")
            return financial_details
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse AI response: {ai_response}. Error: {str(e)}")
            raise Exception(f"AI response parsing failed: {str(e)}")
            
    except Exception as e:
        logger.error(f"AI service failed: {str(e)}")
        raise Exception(f"AI service failed: {str(e)}")

def generate_financial_details_with_ai(basic_details: UserBasicDetails) -> dict:
    """
    Use AI to generate financial details based on user's business context
    """
    try:
        # Get current date for context
        from datetime import datetime
        current_date = datetime.now()
        current_date_str = current_date.strftime("%d %b %Y")
        
        # Create a comprehensive prompt for AI
        prompt = f"""
        IMPORTANT: Today's date is {current_date_str}. Generate the CURRENT financial year based on this date.

        Based on the following business details, generate appropriate financial year, projections, and currency:

        Company Details:
        - Industry: {basic_details.industry}
        - Country: {basic_details.country}
        - City: {basic_details.city}
        - Company Size: {basic_details.company_size}
        - Business Model: {basic_details.business_model}

        Please provide the following in JSON format:
        1. fin_year: CURRENT financial year in format "DD MMM YYYY - DD MMM YYYY" (based on today's date: {current_date_str})
        2. projections: Number of years for projections (default: {NUMBER_OF_PROJECTIONS} years, but can be 3-5 years based on business complexity)
        3. currency: Appropriate currency code (ISO 3-letter code like USD, EUR, INR, etc.)

        CRITICAL: Since today is {current_date_str}, the financial year should be current (e.g., if today is in 2025, return 2024-2025 or 2025-2026 depending on the fiscal year cycle).
        Do NOT return outdated financial years like 2022-2023.

        Consider:
        - Country-specific fiscal year start dates
        - Current date context ({current_date_str})
        - Industry standards for projection periods
        - Local currency for the business location
        - Business size and complexity for projection length
        - Default projection period is {NUMBER_OF_PROJECTIONS} years unless business complexity requires more

        Return only valid JSON with these exact field names: fin_year, projections, currency
        """

        # Call OpenAI service
        ai_response = get_openai_completion(prompt, {
            "max_tokens": 300,
            "temperature": 0.3  # Lower temperature for more consistent financial data
        })

        # Parse AI response
        try:
            # Clean the response and extract JSON
            response_text = ai_response.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            financial_details = json.loads(response_text.strip())
            
            # Validate required fields
            required_fields = ['fin_year', 'projections', 'currency']
            for field in required_fields:
                if field not in financial_details:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate projections is a number
            if not isinstance(financial_details['projections'], int):
                financial_details['projections'] = int(financial_details['projections'])
            
            logger.info(f"AI successfully generated financial details: {financial_details}")
            return financial_details
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse AI response: {ai_response}. Error: {str(e)}")
            raise Exception(f"AI response parsing failed: {str(e)}")
            
    except Exception as e:
        logger.error(f"AI service failed: {str(e)}")
        raise Exception(f"AI service failed: {str(e)}")


def generate_revenue_title_suggestions_with_ai(basic_details: UserBasicDetails) -> list:
    """
    Use AI to generate revenue title suggestions with growth rates for multiple years based on user's business context
    """
    try:
        # Get the number of projections (years) from user details
        projections = basic_details.projections or 3  # Default to 3 years if not set
        
        # Get prompt from prompts module
        prompt = get_revenue_title_suggestions_prompt(basic_details, projections)


        # Call OpenAI service
        ai_response = get_openai_completion(prompt, {
            "max_tokens": 800,
            "temperature": 0.6  # Balanced temperature for creative but realistic suggestions
        })

        # Parse AI response
        try:
            # Clean the response and extract JSON
            response_text = ai_response.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            # Find the JSON object boundaries
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            
            if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
                raise ValueError("No valid JSON object found in AI response")
            
            # Extract just the JSON part
            json_text = response_text[start_idx:end_idx + 1].strip()
            
            suggestions_data = json.loads(json_text)
            
            # Validate required fields
            if 'suggestions' not in suggestions_data:
                raise ValueError("Missing 'suggestions' field in AI response")
            
            suggestions = suggestions_data['suggestions']
            
            # Validate it's a list and has the right number of suggestions
            if not isinstance(suggestions, list):
                raise ValueError("'suggestions' field is not a list")
            
            if len(suggestions) != NUMBER_OF_SUGGESTIONS:
                raise ValueError(f"AI returned {len(suggestions)} suggestions, expected exactly {NUMBER_OF_SUGGESTIONS}")
            
            # Validate each suggestion has required fields
            for i, suggestion in enumerate(suggestions):
                required_fields = ['name', 'growth_rates', 'confidence', 'market_trend']
                for field in required_fields:
                    if field not in suggestion:
                        raise ValueError(f"Suggestion {i} missing required field: {field}")
                
                # Validate growth_rates is a list with correct length
                if not isinstance(suggestion['growth_rates'], list):
                    raise ValueError(f"Suggestion {i} growth_rates must be a list")
                
                if len(suggestion['growth_rates']) != projections - 1:
                    raise ValueError(f"Suggestion {i} must have exactly {projections - 1} growth rates, got {len(suggestion['growth_rates'])}")
                
                # Validate confidence is a number between 0 and 1
                if not isinstance(suggestion['confidence'], (int, float)) or not (0 <= suggestion['confidence'] <= 1):
                    raise ValueError(f"Suggestion {i} confidence must be a number between 0 and 1")
                
                # Validate market_trend is one of the allowed values
                if suggestion['market_trend'] not in ['rising', 'stable', 'declining']:
                    raise ValueError(f"Suggestion {i} market_trend must be 'rising', 'stable', or 'declining'")
            
            logger.info(f"AI successfully generated {len(suggestions)} revenue title suggestions with growth rates")
            return suggestions
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse AI response: {ai_response}. Error: {str(e)}")
            raise Exception(f"AI response parsing failed: {str(e)}")
            
    except Exception as e:
        logger.error(f"AI service failed: {str(e)}")
        raise Exception(f"AI service failed: {str(e)}")


def validate_product_name_with_ai(product_name: str, basic_details: UserBasicDetails) -> dict:
    """
    Stage 1: Validate if the product name is legitimate or nonsense using AI
    """
    try:
        prompt = validate_product_name_prompt(product_name, basic_details)
        
        ai_response = get_openai_completion(prompt, {
            "max_tokens": 300,
            "temperature": 0.3  # Low temperature for consistent validation
        })
        
        # Parse AI response
        response_text = ai_response.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError("No valid JSON found in AI response")
        
        json_text = response_text[start_idx:end_idx + 1].strip()
        validation_data = json.loads(json_text)
        
        # Validate required fields
        required_fields = ['is_legitimate', 'confidence', 'reasoning']
        for field in required_fields:
            if field not in validation_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate data types
        if not isinstance(validation_data['is_legitimate'], bool):
            raise ValueError("is_legitimate must be boolean")
        
        if not isinstance(validation_data['confidence'], (int, float)):
            validation_data['confidence'] = float(validation_data['confidence'])
        
        validation_data['confidence'] = max(0.0, min(1.0, validation_data['confidence']))
        
        logger.info(f"Product validation for '{product_name}': legitimate={validation_data['is_legitimate']}, confidence={validation_data['confidence']}")
        return validation_data
        
    except Exception as e:
        logger.error(f"Product validation failed for '{product_name}': {str(e)}")
        raise Exception(f"Product validation failed: {str(e)}")


def get_real_product_growth_rates_with_ai(product_name: str, basic_details: UserBasicDetails) -> dict:
    """
    Stage 2: Get real growth rates for legitimate products using AI
    """
    try:
        projections = basic_details.projections or 3
        
        prompt = get_product_growth_rate_prompt(product_name, basic_details, projections)
        
        ai_response = get_openai_completion(prompt, {
            "max_tokens": 500,
            "temperature": 0.4
        })
        
        # Parse AI response
        response_text = ai_response.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError("No valid JSON found in AI response")
        
        json_text = response_text[start_idx:end_idx + 1].strip()
        growth_data = json.loads(json_text)
        
        # Validate required fields
        required_fields = ['growth_rates', 'confidence', 'market_trend']
        for field in required_fields:
            if field not in growth_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate growth_rates format
        if not isinstance(growth_data['growth_rates'], list):
            raise ValueError("growth_rates must be a list")
        
        if len(growth_data['growth_rates']) != projections - 1:
            raise ValueError(f"Must have exactly {projections - 1} growth rates, got {len(growth_data['growth_rates'])}")
        
        # Validate data types and ranges
        if not isinstance(growth_data['confidence'], (int, float)):
            growth_data['confidence'] = float(growth_data['confidence'])
        
        growth_data['confidence'] = max(0.0, min(1.0, growth_data['confidence']))
        
        # Validate and ensure growth rates are reasonable (0-50%)
        for i, rate in enumerate(growth_data['growth_rates']):
            if not isinstance(rate, (int, float)):
                growth_data['growth_rates'][i] = float(rate)
            growth_data['growth_rates'][i] = max(0.0, min(50.0, growth_data['growth_rates'][i]))
        
        # Validate market trend - must be from AI, no fallback
        valid_trends = ['rising', 'stable', 'declining']
        if growth_data['market_trend'] not in valid_trends:
            raise ValueError(f"AI returned invalid market_trend: '{growth_data['market_trend']}'. Must be one of: {valid_trends}")
        
        logger.info(f"Real growth rates for '{product_name}': {growth_data['growth_rates']}")
        return growth_data
        
    except Exception as e:
        logger.error(f"Real growth rate analysis failed for '{product_name}': {str(e)}")
        raise Exception(f"Real growth rate analysis failed: {str(e)}")


def calculate_product_growth_rate_with_ai(product_name: str, basic_details: UserBasicDetails) -> dict:
    """
    Calculate product growth rates using AI with strict validation flow.

    Flow:
    1. Validate product name using AI
    2. If NOT legitimate → return zero growth rates
    3. If legitimate → generate real growth rates using AI
    """
    try:
        logger.info(f"Starting AI analysis for product: '{product_name}'")

        logger.info(f"Validating product name '{product_name}'")
        validation_result = validate_product_name_with_ai(product_name, basic_details)

        is_legitimate = validation_result["is_legitimate"]
        confidence = validation_result["confidence"]

        logger.info(
            f"Validation result for '{product_name}': "
            f"legitimate={is_legitimate}, confidence={confidence}"
        )

        if not is_legitimate:
            projections = basic_details.projections or 3

            logger.warning(
                f"Product '{product_name}' is NOT legitimate. "
                f"Skipping growth rate generation."
            )

            return {
                "growth_rates": [0] * (projections - 1),
                "confidence": 0.0,
                "market_trend": "unknown",
                "analysis": "Product name failed AI validation. Growth rates set to zero.",
                "validation_stage": "failed_validation",
                "product_validation": validation_result
            }

        # --------------------------------
        # Stage 2: Generate growth rates
        # --------------------------------
        logger.info(f"Getting growth rates from AI for product '{product_name}'")
        growth_data = get_real_product_growth_rates_with_ai(product_name, basic_details)

        growth_data["validation_stage"] = "ai_analysis"
        growth_data["product_validation"] = validation_result

        logger.info(
            f"AI analysis successful for '{product_name}'. "
            f"Growth rates: {growth_data.get('growth_rates')}"
        )

        return growth_data

    except Exception as e:
        logger.error(f"AI analysis failed for product '{product_name}': {str(e)}")
        raise Exception(f"Product analysis failed: {str(e)}")




def generate_cogs_title_suggestions_with_ai(basic_details: UserBasicDetails) -> list:
    """
    Use AI to generate COGS title suggestions based on user's business context
    """
    try:
        # Get prompt from prompts module
        prompt = get_cogs_title_suggestions_prompt(basic_details)

        # Call OpenAI service
        ai_response = get_openai_completion(prompt, {
            "max_tokens": 500,
            "temperature": 0.7  # Slightly higher temperature for creative suggestions
        })

        # Parse AI response
        try:
            # Clean the response and extract JSON
            response_text = ai_response.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            # Find the JSON object boundaries
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            
            if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
                raise ValueError("No valid JSON object found in AI response")
            
            # Extract just the JSON part
            json_text = response_text[start_idx:end_idx + 1].strip()
            
            suggestions_data = json.loads(json_text)
            
            # Validate required fields
            if 'titles' not in suggestions_data:
                raise ValueError("Missing 'titles' field in AI response")
            
            titles = suggestions_data['titles']
            
            # Validate it's a list and has the right number of suggestions
            if not isinstance(titles, list):
                raise ValueError("'titles' field is not a list")
            
            if len(titles) != NUMBER_OF_SUGGESTIONS:
                raise ValueError(f"AI returned {len(titles)} suggestions, expected exactly {NUMBER_OF_SUGGESTIONS}")
            
            logger.info(f"AI successfully generated {len(titles)} COGS title suggestions")
            return titles
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse AI response: {ai_response}. Error: {str(e)}")
            raise Exception(f"AI response parsing failed: {str(e)}")
            
    except Exception as e:
        logger.error(f"AI service failed: {str(e)}")
        raise Exception(f"AI service failed: {str(e)}")


def generate_cogs_title_suggestions_with_revenue_context(basic_details: UserBasicDetails, revenue_selected_titles: list, revenue_projected_titles: list) -> list:
    """
    Use AI to generate COGS title suggestions with growth rates for multiple years based on user's business context and revenue selected titles
    """
    try:
        # Get the number of projections (years) from user details
        projections = basic_details.projections or 3  # Default to 3 years if not set
        # Get prompt from prompts module
        prompt = get_cogs_title_suggestions_with_revenue_context_prompt(
            basic_details, revenue_selected_titles, revenue_projected_titles, projections
        )

        # Call OpenAI service
        ai_response = get_openai_completion(prompt, {
            "max_tokens": 800,
            "temperature": 0.6  # Balanced creativity and consistency
        })

        # Parse AI response
        try:
            # Clean the response and extract JSON
            response_text = ai_response.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            # Find the JSON object boundaries
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            
            if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
                raise ValueError("No valid JSON object found in AI response")
            
            # Extract just the JSON part
            json_text = response_text[start_idx:end_idx + 1].strip()
            
            suggestions_data = json.loads(json_text)
            
            # Validate required fields
            if 'suggestions' not in suggestions_data:
                raise ValueError("Missing 'suggestions' field in AI response")
            
            suggestions = suggestions_data['suggestions']
            
            # Validate it's a list
            if not isinstance(suggestions, list):
                raise ValueError("'suggestions' field is not a list")
            
            if len(suggestions) != NUMBER_OF_SUGGESTIONS:
                raise ValueError(f"AI returned {len(suggestions)} suggestions, expected exactly {NUMBER_OF_SUGGESTIONS}")
            
            # Validate each suggestion has required fields
            for i, suggestion in enumerate(suggestions):
                required_fields = ['name', 'percentage_of_revenue', 'confidence', 'market_trend']
                for field in required_fields:
                    if field not in suggestion:
                        raise ValueError(f"Suggestion {i} missing required field: {field}")
                
                # Validate field types and values
                if not isinstance(suggestion['name'], str) or not suggestion['name'].strip():
                    raise ValueError(f"Suggestion {i} name must be a non-empty string")
                
                # Validate growth_rates format
                if not isinstance(suggestion['percentage_of_revenue'], list):
                    raise ValueError(f"Suggestion {i} percentage_of_revenue must be a list")
                
                if len(suggestion['percentage_of_revenue']) != projections :
                    raise ValueError(f"Suggestion {i} must have exactly {projections } percentage_of_revenue, got {len(suggestion['percentage_of_revenue'])}")
                
                # Validate each growth rate
                for j, rate in enumerate(suggestion['percentage_of_revenue']):
                    if not isinstance(rate, (int, float)):
                        raise ValueError(f"Suggestion {i} percentage_of_revenue[{j}] must be a number")
                
                if not isinstance(suggestion['confidence'], (int, float)) or not (0 <= suggestion['confidence'] <= 1):
                    raise ValueError(f"Suggestion {i} confidence must be a number between 0 and 1")
                if suggestion['market_trend'] not in ['rising', 'stable', 'declining']:
                    raise ValueError(f"Suggestion {i} market_trend must be 'rising', 'stable', or 'declining'")
            
            logger.info(f"AI successfully generated {len(suggestions)} COGS title suggestions with percentage_of_revenue")
            return suggestions
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse AI response: {ai_response}. Error: {str(e)}")
            raise Exception(f"AI response parsing failed: {str(e)}")
            
    except Exception as e:
        logger.error(f"AI service failed: {str(e)}")
        raise Exception(f"AI service failed: {str(e)}")



def generate_operating_expenses_title_suggestions_with_ai(basic_details: UserBasicDetails,user_id: int, db: Session) -> list:
    """
    Use AI to generate operating expenses title suggestions with growth rates based on user's business context
    """
    try:
        # Get the number of projections from user details
        projections = getattr(basic_details, 'projections', 5)  # Default to 5 if not set
        pnl_record = db.query(PNLStatement).filter(PNLStatement.user_id == user_id).first()
        existing_revenue_titles = []
        if pnl_record:
            revenue_record = db.query(RevenueStream).filter(RevenueStream.pnl_id == pnl_record.id).first()
            if revenue_record and revenue_record.selected_titles:
                # existing_revenue_titles = [item.get("name", "") for item in revenue_record.selected_titles]
                existing_revenue_titles = []

                raw_titles = revenue_record.selected_titles

                # If stored as JSON string → convert to Python object
                if isinstance(raw_titles, str):
                    try:
                        raw_titles = json.loads(raw_titles)
                    except json.JSONDecodeError:
                        raw_titles = []

                if isinstance(raw_titles, list):
                    for item in raw_titles:
                        if isinstance(item, dict):
                            existing_revenue_titles.append(item.get("name", ""))
                        elif isinstance(item, str):
                            existing_revenue_titles.append(item)
        # Create a comprehensive prompt for AI
        prompt = f"""
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
        - The following are EXISTING REVENUE TITLES and are provided ONLY for CONTEXT.
        - Use them strictly to understand the business model and cost structure.
        Existing Revenue Titles (Context Only):
        • {existing_revenue_titles}
        

        Revenue Percentage Guidelines:
        - Research current market trends for each operating expense category in the {basic_details.industry} industry
        - Consider the company size ({basic_details.company_size}) and business model ({basic_details.business_model})
        - Factor in the country's economic conditions ({basic_details.country})
        - Consider the location-specific costs ({basic_details.city}, {basic_details.country})
        - Provide realistic year-over-year changes in the percentage of revenue based on market conditions, industry norms, and business context. The AI has full flexibility to determine appropriate values (including low, high, zero, or negative changes) as long as they are justified.
        - These percentage-of-revenue values should be provided for each of the {projections} years.
        - The percentage of revenue for each operating expense should be provided for every year of the {projections}-year period.
        - The percentage of revenue must be integers only and may be positive, negative, or zero
        - These percentages may vary year to year, but the fluctuations should remain realistic and within a reasonable range based on industry norms and business context.
        - Avoid extreme or unrealistic jumps unless clearly justified by the business model or market conditions.
        - Higher confidence for well-established categories, lower for emerging markets

        Make sure to provide Upto 10 suggestions with exactly {projections} percentage of revenue values each.
        """

        # Call OpenAI service
        ai_response = get_openai_completion(prompt, {
            "max_tokens": 1000,
            "temperature": 0.6  # Balanced creativity and consistency
        })

        # Parse AI response
        try:
            # Clean the response and extract JSON
            response_text = ai_response.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            # Find the JSON object boundaries
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            
            if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
                raise ValueError("No valid JSON object found in AI response")
            
            # Extract just the JSON part
            json_text = response_text[start_idx:end_idx + 1].strip()
            
            suggestions_data = json.loads(json_text)
            
            # Validate required fields
            if 'suggestions' not in suggestions_data:
                raise ValueError("Missing 'suggestions' field in AI response")
            
            suggestions = suggestions_data['suggestions']
            
            # Validate it's a list
            if not isinstance(suggestions, list):
                raise ValueError("'suggestions' field is not a list")
            
            if len(suggestions) != NUMBER_OF_SUGGESTIONS:
                raise ValueError(f"AI returned {len(suggestions)} suggestions, expected exactly {NUMBER_OF_SUGGESTIONS}")
            
            # Validate each suggestion has required fields
            for i, suggestion in enumerate(suggestions):
                required_fields = ['name', 'percentage_of_revenue', 'confidence', 'market_trend']
                for field in required_fields:
                    if field not in suggestion:
                        raise ValueError(f"Suggestion {i} missing required field: {field}")
                
                # Validate field types and values
                if not isinstance(suggestion['name'], str) or not suggestion['name'].strip():
                    raise ValueError(f"Suggestion {i} name must be a non-empty string")
                if not isinstance(suggestion['percentage_of_revenue'], list):
                    raise ValueError(f"Suggestion {i} percentage_of_revenue must be a list")
                if len(suggestion['percentage_of_revenue']) != projections:
                    raise ValueError(f"Suggestion {i} must have exactly {projections} growth rates")
                for j, rate in enumerate(suggestion['percentage_of_revenue']):
                    if not isinstance(rate, (int, float)):
                        raise ValueError(f"Suggestion {i} percentage_of_revenue[{j}] must be a number")
                if not isinstance(suggestion['confidence'], (int, float)) or not (0 <= suggestion['confidence'] <= 1):
                    raise ValueError(f"Suggestion {i} confidence must be a number between 0 and 1")
                if suggestion['market_trend'] not in ['rising', 'stable', 'declining']:
                    raise ValueError(f"Suggestion {i} market_trend must be 'rising', 'stable', or 'declining'")
            
            logger.info(f"AI successfully generated {len(suggestions)} operating expenses title suggestions with growth rates")
            return suggestions
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse AI response: {ai_response}. Error: {str(e)}")
            raise Exception(f"AI response parsing failed: {str(e)}")
            
    except Exception as e:
        logger.error(f"AI service failed: {str(e)}")
        raise Exception(f"AI service failed: {str(e)}")

# def calculate_cogs_product_growth_rate_with_ai(product_name: str, basic_details: UserBasicDetails) -> dict:
#     """
#     Calculate growth rates for a COGS product using AI analysis.
#     Similar to calculate_product_growth_rate_with_ai but focused on COGS context.
#     """
#     try:
#         projections = getattr(basic_details, 'projections', 5)
        
#         # Get prompt from prompts module
#         prompt = get_cogs_product_growth_rate_prompt(product_name, basic_details, projections)
        
#         ai_response = get_openai_completion(prompt, {
#             "max_tokens": 500,
#             "temperature": 0.4
#         })
        
#         logger.info(f"AI response for COGS product '{product_name}': {ai_response}")
        
#         if not ai_response:
#             raise Exception("AI service returned empty response")
        
#         # Parse AI response
#         response_text = ai_response.strip()
        
#         # Remove any markdown code blocks if present
#         if response_text.startswith('```json'):
#             response_text = response_text[7:]
#         if response_text.startswith('```'):
#             response_text = response_text[3:]
#         if response_text.endswith('```'):
#             response_text = response_text[:-3]
        
#         # Find JSON object
#         start_idx = response_text.find('{')
#         end_idx = response_text.rfind('}')
        
#         if start_idx == -1 or end_idx == -1:
#             raise Exception("No valid JSON found in AI response")
        
#         json_text = response_text[start_idx:end_idx + 1].strip()
#         ai_data = json.loads(json_text)
        
#         return {
#             "corrected_name": ai_data.get("corrected_name", product_name),
#             "growth_rates": ai_data.get("growth_rates", []),
#             "confidence": ai_data.get("confidence", 0.0),
#             "market_trend": ai_data.get("market_trend", "unknown")
#         }
        
#     except Exception as e:
#         logger.error(f"AI analysis failed for COGS product '{product_name}': {str(e)}")
#         raise Exception(f"AI analysis failed for COGS product '{product_name}': {str(e)}")

def calculate_cogs_product_growth_rate_with_ai(
    product_name: str,
    basic_details: UserBasicDetails
) -> dict:
    """
    Calculate growth rates for a COGS product using AI analysis.

    FLOW:
    1. Validate COGS product name using AI
    2. If INVALID → return zero growth rates (DO NOT call growth AI)
    3. If VALID → call AI to generate growth rates
    """
    try:
        projections = getattr(basic_details, 'projections', 5)

        # -------------------------------------------------
        # Stage 1: Validate COGS product name
        # -------------------------------------------------
        logger.info(f"Validating COGS product name '{product_name}'")

        validation_result = validate_cogs_product_name_with_ai(
            product_name,
            basic_details
        )

        if not validation_result["is_legitimate"]:
            logger.warning(
                f"COGS product '{product_name}' failed validation. "
                f"Returning zero growth rates."
            )

            return {
                "corrected_name": product_name,  # keep exact user input
                "percentage_of_revenue": [0] * (projections ),
                "confidence": 0.0,
                "market_trend": "unknown",
                "validation_stage": "failed_validation",
                "cogs_validation": validation_result
            }

        # -------------------------------------------------
        # Stage 2: Generate growth rates via AI
        # -------------------------------------------------
        prompt = get_cogs_product_growth_rate_prompt(
            product_name,
            basic_details,
            projections
        )

        ai_response = get_openai_completion(prompt, {
            "max_tokens": 500,
            "temperature": 0.4
        })

        logger.info(f"AI response for COGS product '{product_name}': {ai_response}")

        if not ai_response:
            raise Exception("AI service returned empty response")

        # Parse AI response
        response_text = ai_response.strip()

        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]

        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')

        if start_idx == -1 or end_idx == -1:
            raise Exception("No valid JSON found in AI response")

        json_text = response_text[start_idx:end_idx + 1].strip()
        ai_data = json.loads(json_text)

        return {
            "corrected_name": ai_data.get("corrected_name", product_name),
            "percentage_of_revenue": ai_data.get("percentage_of_revenue", []),
            "confidence": ai_data.get("confidence", 0.0),
            "market_trend": ai_data.get("market_trend", "unknown"),
            "validation_stage": "ai_analysis",
            "cogs_validation": validation_result
        }

    except Exception as e:
        logger.error(
            f"AI analysis failed for COGS product '{product_name}': {str(e)}"
        )
        raise Exception(
            f"AI analysis failed for COGS product '{product_name}': {str(e)}"
        )



# def calculate_operating_expense_growth_rate_with_ai(expense_name: str, basic_details: UserBasicDetails) -> dict:
#     """
#     Calculate growth rates for an operating expense using AI analysis.
#     Similar to calculate_product_growth_rate_with_ai but focused on operating expenses context.
#     """
#     try:
#         projections = getattr(basic_details, 'projections', 5)
        
#         # Get prompt from prompts module
#         prompt = get_operating_expense_growth_rate_prompt(expense_name, basic_details, projections)
        
#         ai_response = get_openai_completion(prompt, {
#             "max_tokens": 500,
#             "temperature": 0.4
#         })
        
#         logger.info(f"AI response for operating expense '{expense_name}': {ai_response}")
        
#         if not ai_response:
#             raise Exception("AI service returned empty response")
        
#         # Parse AI response
#         response_text = ai_response.strip()
        
#         # Remove any markdown code blocks if present
#         if response_text.startswith('```json'):
#             response_text = response_text[7:]
#         if response_text.startswith('```'):
#             response_text = response_text[3:]
#         if response_text.endswith('```'):
#             response_text = response_text[:-3]
        
#         # Find JSON object
#         start_idx = response_text.find('{')
#         end_idx = response_text.rfind('}')
        
#         if start_idx == -1 or end_idx == -1:
#             raise Exception("No valid JSON found in AI response")
        
#         json_text = response_text[start_idx:end_idx + 1].strip()
#         ai_data = json.loads(json_text)
        
#         return {
#             "corrected_name": ai_data.get("corrected_name", expense_name),
#             "percentage_of_revenue": ai_data.get("percentage_of_revenue", []),
#             "confidence": ai_data.get("confidence", 0.0),
#             "market_trend": ai_data.get("market_trend", "unknown")
#         }
        
#     except Exception as e:
#         logger.error(f"AI analysis failed for operating expense '{expense_name}': {str(e)}")
#         raise Exception(f"AI analysis failed for operating expense '{expense_name}': {str(e)}")




def calculate_operating_expense_growth_rate_with_ai(
    expense_name: str,
    basic_details: UserBasicDetails
) -> dict:
    """
    Calculate growth rates for an operating expense using AI analysis.

    FLOW:
    1. Validate operating expense name using AI
    2. If INVALID → return zero values (DO NOT call growth AI)
    3. If VALID → generate growth rates via AI
    """
    try:
        projections = getattr(basic_details, 'projections', 5)

        # -------------------------------------------------
        # Stage 1: Validate operating expense name
        # -------------------------------------------------
        logger.info(f"Validating operating expense name '{expense_name}'")

        validation_result = validate_operating_expense_product_name_with_ai(
            expense_name,
            basic_details
        )

        if not validation_result["is_legitimate"]:
            logger.warning(
                f"Operating expense '{expense_name}' failed validation. "
                f"Returning zero growth values."
            )

            return {
                "corrected_name": expense_name,  # preserve user input
                "percentage_of_revenue": [0] * (projections - 1),
                "confidence": 0.0,
                "market_trend": "unknown",
                "validation_stage": "failed_validation",
                "opex_validation": validation_result
            }

        # -------------------------------------------------
        # Stage 2: Generate growth via AI
        # -------------------------------------------------
        prompt = get_operating_expense_growth_rate_prompt(
            expense_name,
            basic_details,
            projections
        )

        ai_response = get_openai_completion(prompt, {
            "max_tokens": 500,
            "temperature": 0.4
        })

        logger.info(f"AI response for operating expense '{expense_name}': {ai_response}")

        if not ai_response:
            raise Exception("AI service returned empty response")

        # Parse AI response
        response_text = ai_response.strip()

        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]

        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')

        if start_idx == -1 or end_idx == -1:
            raise Exception("No valid JSON found in AI response")

        json_text = response_text[start_idx:end_idx + 1].strip()
        ai_data = json.loads(json_text)

        return {
            "corrected_name": ai_data.get("corrected_name", expense_name),
            "percentage_of_revenue": ai_data.get("percentage_of_revenue", []),
            "confidence": ai_data.get("confidence", 0.0),
            "market_trend": ai_data.get("market_trend", "unknown"),
            "validation_stage": "ai_analysis",
            "opex_validation": validation_result
        }

    except Exception as e:
        logger.error(
            f"AI analysis failed for operating expense '{expense_name}': {str(e)}"
        )
        raise Exception(
            f"AI analysis failed for operating expense '{expense_name}': {str(e)}"
        )



def generate_depreciation_assets_with_ai(basic_details: UserBasicDetails,user_id, db) -> list:
    """
    Generate 3 depreciation/amortisation assets using AI based on user's business context.
    Returns list of assets with asset_name, purchase_year, and purchase_cost.
    """
    try:
        # Get prompt from prompts module
        prompt = get_depreciation_assets_prompt(basic_details, user_id, db)
        
        ai_response = get_openai_completion(prompt, {
            "max_tokens": 800,
            "temperature": 0.6
        })
        
        logger.info(f"AI response for generating assets: {ai_response}")
        
        if not ai_response:
            raise Exception("AI service returned empty response")
        
        # Parse AI response
        response_text = ai_response.strip()
        
        # Remove any markdown code blocks if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        # Find JSON object
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            raise Exception("No valid JSON found in AI response")
        
        json_text = response_text[start_idx:end_idx + 1].strip()
        ai_data = json.loads(json_text)
        
        assets = ai_data.get("assets", [])
        
        if not isinstance(assets, list) or len(assets) != 6:
            raise Exception("AI response must contain exactly 6 assets")
        enriched_assets = []
        # Validate each asset has required fields
        for i, asset in enumerate(assets):
            if not isinstance(asset, dict):
                raise Exception(f"Asset {i} must be a dictionary")
            
            required_fields = ["asset_name", "purchase_year", "purchase_cost"]
            for field in required_fields:
                if field not in asset:
                    raise Exception(f"Asset {i} must have '{field}' field")
            
            # Validate data types
            if not isinstance(asset["asset_name"], str):
                raise Exception(f"Asset {i} asset_name must be a string")
            
            if not isinstance(asset["purchase_year"], int):
                raise Exception(f"Asset {i} purchase_year must be an integer")
            
            if not isinstance(asset["purchase_cost"], (int, float)):
                raise Exception(f"Asset {i} purchase_cost must be a number")
        
            enriched_assets.append({
                **asset,
                "suggestion_type": "AI"
            })

        return enriched_assets
        
    except Exception as e:
        logger.error(f"AI analysis failed for generating assets: {str(e)}")
        raise Exception(f"AI analysis failed for generating assets: {str(e)}")


def generate_other_charges_title_suggestions_with_ai(basic_details: UserBasicDetails, db:Session, user_id: int) -> list:
    """
    Use AI to generate other charges title suggestions with growth rates based on user's business context
    """
    try:
        # Get the number of projections from user details
        projections = basic_details.projections or 5
        
        # Get prompt from prompts module
        prompt = get_other_charges_title_suggestions_prompt(basic_details, db, user_id, projections)
        
        # Call AI service
        response = get_openai_completion(prompt)
        
        if not response or not response.strip():
            raise Exception("Empty response from AI service")
        
        # Clean and parse JSON response
        cleaned_response = response.strip()
        
        # Log the raw response for debugging
        logger.info(f"Raw AI response: {cleaned_response[:500]}...")
        
        # Try to fix common JSON formatting issues
        # Replace single quotes with double quotes for property names
        import re
        cleaned_response = re.sub(r"'([^']*)':", r'"\1":', cleaned_response)
        cleaned_response = re.sub(r":\s*'([^']*)'", r': "\1"', cleaned_response)
        
        # Parse JSON response
        try:
            suggestions = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {str(e)}")
            logger.error(f"Cleaned response: {cleaned_response[:1000]}...")
            
            # Try to fix common JSON issues
            try:
                # Fix missing commas between objects
                fixed_response = re.sub(r'}\s*{', '},{', cleaned_response)
                # Fix trailing commas
                fixed_response = re.sub(r',\s*}', '}', fixed_response)
                fixed_response = re.sub(r',\s*]', ']', fixed_response)
                # Fix missing quotes around values
                fixed_response = re.sub(r':\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*([,}])', r': "\1"\2', fixed_response)
                
                suggestions = json.loads(fixed_response)
                logger.info("Successfully fixed JSON formatting issues")
            except json.JSONDecodeError as e2:
                logger.error(f"JSON fixing also failed: {str(e2)}")
                
                # If still failing, try to extract and fix JSON from the response
                json_match = re.search(r'\[.*\]', cleaned_response, re.DOTALL)
                if json_match:
                    try:
                        json_text = json_match.group()
                        # Try to fix the extracted JSON
                        json_text = re.sub(r'}\s*{', '},{', json_text)
                        json_text = re.sub(r',\s*}', '}', json_text)
                        json_text = re.sub(r',\s*]', ']', json_text)
                        suggestions = json.loads(json_text)
                        logger.info("Successfully extracted and fixed JSON")
                    except json.JSONDecodeError as e3:
                        logger.error(f"JSON extraction and fixing failed: {str(e3)}")
                        # Last resort: try to parse individual objects
                        try:
                            # Extract individual objects and build a valid array
                            # Use a more robust regex to find complete objects
                            objects = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned_response)
                            suggestions = []
                            for obj_str in objects:
                                try:
                                    # Clean up the object string
                                    obj_str = obj_str.strip()
                                    if obj_str.startswith('{') and obj_str.endswith('}'):
                                        obj = json.loads(obj_str)
                                        # Validate that it has the required fields
                                        if all(field in obj for field in ['name', 'description', 'growth_rates', 'market_trend']):
                                            suggestions.append(obj)
                                except:
                                    continue
                            
                            if not suggestions:
                                raise Exception("Could not parse any valid objects from response")
                            
                            logger.info(f"Successfully parsed {len(suggestions)} individual objects")
                            
                            # If we have fewer than 10, try to find more objects with a different approach
                            if len(suggestions) < 10:
                                # Try to find objects that might be split across lines
                                lines = cleaned_response.split('\n')
                                for line in lines:
                                    line = line.strip()
                                    if line.startswith('{') and not line.endswith('}'):
                                        # This might be a split object, try to find the complete one
                                        continue
                                    elif line.startswith('{') and line.endswith('}'):
                                        try:
                                            obj = json.loads(line)
                                            if all(field in obj for field in ['name', 'description', 'growth_rates', 'market_trend']):
                                                if obj not in suggestions:  # Avoid duplicates
                                                    suggestions.append(obj)
                                        except:
                                            continue
                        except Exception as e4:
                            logger.error(f"Individual object parsing failed: {str(e4)}")
                            raise Exception(f"Could not parse AI response as JSON. Original error: {str(e)}, Fixed error: {str(e2)}, Extraction error: {str(e3)}, Object parsing error: {str(e4)}")
                else:
                    raise Exception(f"Could not find JSON array in AI response: {str(e)}")
        
        # Validate response structure
        if not isinstance(suggestions, list):
            raise ValueError("AI response must be a list")
        
        if len(suggestions) == 0:
            raise ValueError("AI response must contain at least one suggestion")
        
        # Validate that we have at least some suggestions
        if len(suggestions) < 5:
            raise ValueError(f"AI response must contain at least 5 suggestions, but got {len(suggestions)}")
        
        # If we have fewer than 10, log a warning but continue
        if len(suggestions) != 10:
            logger.warning(f"AI returned {len(suggestions)} suggestions instead of 10, but continuing with available suggestions")
        
        # Validate each suggestion
        for i, suggestion in enumerate(suggestions):
            required_fields = ['name', 'description', 'growth_rates', 'market_trend']
            for field in required_fields:
                if field not in suggestion:
                    raise ValueError(f"Suggestion {i} must have '{field}' field")
            
            # Validate data types
            if not isinstance(suggestion['name'], str):
                raise ValueError(f"Suggestion {i} name must be a string")
            
            if not isinstance(suggestion['description'], str):
                raise ValueError(f"Suggestion {i} description must be a string")
            
            if not isinstance(suggestion['growth_rates'], list):
                raise ValueError(f"Suggestion {i} growth_rates must be a list")
            
            if len(suggestion['growth_rates']) != projections:
                raise ValueError(f"Suggestion {i} growth_rates must have {projections} values")
            
            for j, rate in enumerate(suggestion['growth_rates']):
                if not isinstance(rate, (int, float)):
                    raise ValueError(f"Suggestion {i} growth_rates[{j}] must be a number")
            
            if suggestion['market_trend'] not in ['rising', 'stable', 'declining']:
                raise ValueError(f"Suggestion {i} market_trend must be 'rising', 'stable', or 'declining'")
        
        # Extract only the names from suggestions for storage
        suggestion_names = [suggestion.get("name", "") for suggestion in suggestions if suggestion.get("name")]
        
        logger.info(f"AI successfully generated {len(suggestion_names)} other charges title suggestions")
        return suggestion_names
        
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"AI response validation failed: {str(e)}")
        raise Exception(f"AI response validation failed: {str(e)}")
    
    except Exception as e:
        logger.error(f"AI service failed: {str(e)}")
        raise Exception(f"AI service failed: {str(e)}")


def generate_other_expense_title_suggestions_with_ai(
    basic_details: UserBasicDetails,
    user_id: int,
    db: Session
) -> list:   
    """
    Use AI to generate other expense title suggestions with growth rates based on user's business context.
    """
    try:
        projections = basic_details.projections or 5

        # Get prompt from prompts module
        prompt = get_other_expense_title_suggestions_prompt(basic_details, projections, user_id, db)

        # Call AI service
        response = get_openai_completion(prompt)

        if not response or not response.strip():
            raise Exception("Empty response from AI service")

        cleaned_response = response.strip()
        logger.info(f"Raw AI response (expenses): {cleaned_response[:500]}...")

        import re
        cleaned_response = re.sub(r"'([^']*)':", r'"\1":', cleaned_response)
        cleaned_response = re.sub(r":\s*'([^']*)'", r': "\1"', cleaned_response)

        try:
            suggestions = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {str(e)}")
            logger.error(f"Cleaned response: {cleaned_response[:1000]}...")

            try:
                fixed_response = re.sub(r'}\s*{', '},{', cleaned_response)
                fixed_response = re.sub(r',\s*}', '}', fixed_response)
                fixed_response = re.sub(r',\s*]', ']', fixed_response)
                fixed_response = re.sub(r':\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*([,}])', r': "\1"\2', fixed_response)
                suggestions = json.loads(fixed_response)
                logger.info("Successfully fixed JSON formatting issues for expenses")
            except json.JSONDecodeError as e2:
                logger.error(f"JSON fixing also failed: {str(e2)}")

                json_match = re.search(r'\[.*\]', cleaned_response, re.DOTALL)
                if json_match:
                    json_text = json_match.group()
                    json_text = re.sub(r'}\s*{', '},{', json_text)
                    json_text = re.sub(r',\s*}', '}', json_text)
                    json_text = re.sub(r',\s*]', ']', json_text)
                    suggestions = json.loads(json_text)
                    logger.info("Successfully extracted and fixed JSON for expenses")
                else:
                    raise Exception(f"Could not parse JSON array for expenses: {str(e)}")

        # Validate structure
        if not isinstance(suggestions, list) or len(suggestions) == 0:
            raise ValueError("AI response must contain a list of suggestions")

        if len(suggestions) < 5:
            raise ValueError(f"AI returned too few suggestions ({len(suggestions)})")

        if len(suggestions) != 10:
            logger.warning(f"AI returned {len(suggestions)} expense suggestions instead of 10")

        # Validate each suggestion
        for i, suggestion in enumerate(suggestions):
            required_fields = ['name', 'description', 'growth_rates', 'market_trend']
            for field in required_fields:
                if field not in suggestion:
                    raise ValueError(f"Suggestion {i} missing '{field}' field")

            if not isinstance(suggestion['name'], str):
                raise ValueError(f"Suggestion {i} name must be string")

            if not isinstance(suggestion['growth_rates'], list):
                raise ValueError(f"Suggestion {i} growth_rates must be list")

            if len(suggestion['growth_rates']) != projections:
                raise ValueError(f"Suggestion {i} must have {projections} growth rates")

            if suggestion['market_trend'] not in ['rising', 'stable', 'declining']:
                raise ValueError(f"Suggestion {i} has invalid market_trend value")

        suggestion_names = [s.get("name", "") for s in suggestions if s.get("name")]
        logger.info(f"AI successfully generated {len(suggestion_names)} other expense title suggestions")
        return suggestion_names

    except Exception as e:
        logger.error(f"AI service failed for other expenses: {str(e)}")
        raise Exception(f"AI service failed for other expenses: {str(e)}")


def generate_terminal_growth_rate_with_ai(db: Session, user_id: int):
    """
    Generate terminal (perpetual) growth rate using AI and return it
    """
    try:
        basic_details = db.query(UserBasicDetails).filter(
            UserBasicDetails.user_id == user_id
        ).first()
        if not basic_details:
            raise HTTPException(
                status_code=404,
                detail="User basic details not found. Please complete your basic details first."
            )
        from app.prompts.valuation import get_terminal_growth_rate_prompt
        ai_prompt = get_terminal_growth_rate_prompt(basic_details)
        from app.utils.openai_client import get_openai_completion
        try:
            ai_response = get_openai_completion(ai_prompt, {
                "max_tokens": 100,
                "temperature": 0.6
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"AI service failed: {str(e)}")
        if not ai_response:
            raise HTTPException(status_code=500, detail="AI service returned empty response")
        try:
            terminal_growth_str = (
                ai_response.strip()
                .replace('%', '')
                .replace('percent', '')
                .strip()
            )
            terminal_growth_rate = float(terminal_growth_str)
            if terminal_growth_rate < 0:
                raise ValueError("Terminal growth rate cannot be negative")
        except (ValueError, TypeError) as e:
            raise HTTPException(
                status_code=500,
                detail=f"AI returned invalid terminal growth rate format: '{ai_response}'. Error: {str(e)}"
            )
        return {
            "success": True,
            "message": f"Terminal growth rate generated successfully: {terminal_growth_rate}%",
            "terminal_growth_rate": terminal_growth_rate
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Terminal growth rate generation failed: {str(e)}"
        )



def generate_wacc_with_ai(db: Session, user_id: int):
    """
    Generate Weighted Average Cost of Capital (WACC) using AI and return it
    """
    try:
        basic_details = db.query(UserBasicDetails).filter(
            UserBasicDetails.user_id == user_id
        ).first()
        if not basic_details:
            raise HTTPException(
                status_code=404,
                detail="User basic details not found. Please complete your basic details first."
            )
        from app.prompts.valuation import get_wacc_prompt
        ai_prompt = get_wacc_prompt(basic_details)
        from app.utils.openai_client import get_openai_completion
        try:
            ai_response = get_openai_completion(ai_prompt, {
                "max_tokens": 100,
                "temperature": 0.6
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"AI service failed: {str(e)}")
        if not ai_response:
            raise HTTPException(status_code=500, detail="AI service returned empty response")
        try:
            wacc_str = (
                ai_response.strip()
                .replace('%', '')
                .replace('percent', '')
                .strip()
            )
            wacc = float(wacc_str)
            if wacc < 0:
                raise ValueError("WACC cannot be negative")
        except (ValueError, TypeError) as e:
            raise HTTPException(
                status_code=500,
                detail=f"AI returned invalid WACC format: '{ai_response}'. Error: {str(e)}"
            )
        return {
            "success": True,
            "message": f"WACC generated successfully: {wacc}%",
            "wacc": wacc
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"WACC generation failed: {str(e)}"
        )



def validate_cogs_product_name_with_ai(product_name: str, basic_details: UserBasicDetails) -> dict:
    """
    Stage 1: Validate if the product name is legitimate or nonsense using AI
    """
    try:
        prompt = validate_cogs_product_name_prompt(product_name, basic_details)
        
        ai_response = get_openai_completion(prompt, {
            "max_tokens": 300,
            "temperature": 0.3  # Low temperature for consistent validation
        })
        
        # Parse AI response
        response_text = ai_response.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError("No valid JSON found in AI response")
        
        json_text = response_text[start_idx:end_idx + 1].strip()
        validation_data = json.loads(json_text)
        
        # Validate required fields
        required_fields = ['is_legitimate', 'confidence', 'reasoning']
        for field in required_fields:
            if field not in validation_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate data types
        if not isinstance(validation_data['is_legitimate'], bool):
            raise ValueError("is_legitimate must be boolean")
        
        if not isinstance(validation_data['confidence'], (int, float)):
            validation_data['confidence'] = float(validation_data['confidence'])
        
        validation_data['confidence'] = max(0.0, min(1.0, validation_data['confidence']))
        
        logger.info(f"Product validation for '{product_name}': legitimate={validation_data['is_legitimate']}, confidence={validation_data['confidence']}")
        return validation_data
        
    except Exception as e:
        logger.error(f"Product validation failed for '{product_name}': {str(e)}")
        raise Exception(f"Product validation failed: {str(e)}")



def validate_operating_expense_product_name_with_ai(product_name: str, basic_details: UserBasicDetails) -> dict:
    """
    Stage 1: Validate if the product name is legitimate or nonsense using AI
    """
    try:
        prompt = validate_operating_expense_product_name_prompt(product_name, basic_details)
        
        ai_response = get_openai_completion(prompt, {
            "max_tokens": 300,
            "temperature": 0.3  # Low temperature for consistent validation
        })
        
        # Parse AI response
        response_text = ai_response.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError("No valid JSON found in AI response")
        
        json_text = response_text[start_idx:end_idx + 1].strip()
        validation_data = json.loads(json_text)
        
        # Validate required fields
        required_fields = ['is_legitimate', 'confidence', 'reasoning']
        for field in required_fields:
            if field not in validation_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate data types
        if not isinstance(validation_data['is_legitimate'], bool):
            raise ValueError("is_legitimate must be boolean")
        
        if not isinstance(validation_data['confidence'], (int, float)):
            validation_data['confidence'] = float(validation_data['confidence'])
        
        validation_data['confidence'] = max(0.0, min(1.0, validation_data['confidence']))
        
        logger.info(f"Product validation for '{product_name}': legitimate={validation_data['is_legitimate']}, confidence={validation_data['confidence']}")
        return validation_data
        
    except Exception as e:
        logger.error(f"Product validation failed for '{product_name}': {str(e)}")
        raise Exception(f"Product validation failed: {str(e)}")