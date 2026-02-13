from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.schemas.user import UserRegister, UserLogin, UserOut, UserBasicDetailsCreate, UserBasicDetailsOut, StandardResponse, ResetProgressRequest, SkipTopicRequest, UserBasicDetailsUpdate, CompanyUpdateRequest
from app.services.user_service import register_user, authenticate_user, create_user_basic_details, update_user_basic_details_progress
from app.models.models import Base, UserProgress, Return, RevenueStream, PNLStatement, COGS, OperatingExpenses, DepreciationNAmortisation, Skipped, OtherIncome, InterestExpense, IncomeBeforeTaxes, BalanceSheet, WorkingCapital, Inventory, BSRecords, CashFlowStatement, OtherExpense, Valuation
from app.models.admin_models import Admin
from app.core.database import get_db
from typing import Optional
from app.utils.utility import get_current_user, get_current_user_from_token, create_all_pnl_records, create_valuation_record, create_balance_sheet_records, get_current_admin
from app.utils.response_utils import success_response, error_response, unauthorized_error, not_found_error, bad_request_error, bad_request_response, internal_server_error_response
from datetime import datetime
from app.schemas.admin import AdminLogin, AdminRegister, ForgotPasswordRequest, VerifyOtpRequest, ResetPasswordRequest, AdminUpdate
from app.services.admin_service import authenticate_admin, generate_otp, send_otp_email
from app.core.security import get_password_hash
from datetime import timedelta

router = APIRouter()



@router.post('/register', response_model=StandardResponse)
def register_admin(admin_data: AdminRegister, db: Session = Depends(get_db)):
    try:
        # Check if admin already exists
        existing_admin = db.query(Admin).filter(
            Admin.email == admin_data.email
        ).first()

        if existing_admin:
            return error_response(message="Admin already exists with this email")

        # Hash password
        hashed_password = get_password_hash(admin_data.password)

        # Create admin object
        new_admin = Admin(
            name=admin_data.name.strip(),
            email=admin_data.email.strip().lower(),
            password=hashed_password
        )

        db.add(new_admin)
        db.commit()
        db.refresh(new_admin)

        return success_response(
            message="Admin registered successfully",
            data={
                "id": new_admin.id,
                "name": new_admin.name,
                "email": new_admin.email
            }
        )

    except Exception as e:
        db.rollback()
        return error_response(
            message=f"Admin registration failed: {str(e)}"
        )



@router.post('/login', response_model=StandardResponse)
def admin_login(admin_data: AdminLogin, db: Session = Depends(get_db)):
    try:
        db_admin, access_token, refresh_token = authenticate_admin(
            db,
            admin_data.email, 
            admin_data.password
        )

        if not db_admin:
            unauthorized_error("Invalid admin credentials")

        return success_response(
            message="Admin login successful",
            data={
                "id": db_admin.id,
                "name": db_admin.name,
                "email": db_admin.email,
                "access_token": access_token,
                "refresh_token": refresh_token
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        return error_response(
            message=f"Admin login failed: {str(e)}"
        )



@router.post("/forgot-password")
def admin_forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    admin = db.query(Admin).filter(Admin.email == request.email).first()

    if not admin:
        return error_response(message="Admin not found")

    otp = generate_otp()
    expiry_time = datetime.utcnow() + timedelta(minutes=5)

    admin.otp = otp
    admin.otp_expiry = expiry_time

    db.commit()

    send_otp_email(admin.email, otp)

    return success_response(message="OTP sent to email")



@router.post("/verify-otp")
def verify_admin_otp(
    request: VerifyOtpRequest,
    db: Session = Depends(get_db)
):
    admin = db.query(Admin).filter(Admin.email == request.email).first()

    if not admin or admin.otp != request.otp:
        return error_response(message="Invalid OTP")

    if datetime.utcnow() > admin.otp_expiry:
        return error_response(message="OTP expired")

    return success_response(message="OTP verified successfully")


@router.post("/reset-password")
def reset_admin_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    admin = db.query(Admin).filter(Admin.email == request.email).first()

    if not admin or admin.otp != request.otp:
        return error_response(message="Invalid OTP")

    if datetime.utcnow() > admin.otp_expiry:
        return error_response(message="OTP expired")

    admin.password = get_password_hash(request.new_password)
    admin.otp = None
    admin.otp_expiry = None

    db.commit()

    return success_response(message="Password reset successful")
    

@router.put("/update-profile", response_model=StandardResponse)
def update_admin_profile(
    admin_data: AdminUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin) 
):
    try:
        admin = db.query(Admin).filter(Admin.id == current_admin["id"]).first()

        if not admin:
            return error_response(message="Admin not found")

        admin.name = admin_data.name.strip()
        admin.email = admin_data.email.strip().lower()
        admin.password = get_password_hash(admin_data.password)

        db.commit()
        db.refresh(admin)

        return success_response(
            message="Admin updated successfully",
            data={
                "id": admin.id,
                "name": admin.name,
                "email": admin.email
            }
        )

    except Exception as e:
        db.rollback()
        return error_response(
            message=f"Admin update failed: {str(e)}"
        )



