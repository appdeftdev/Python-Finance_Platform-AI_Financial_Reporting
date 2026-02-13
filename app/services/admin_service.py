from sqlalchemy.orm import Session
from app.models.admin_models import Admin
from app.core.security import verify_password, get_password_hash
from app.utils.utility import create_access_token, create_refresh_token
import smtplib
import random
from email.mime.text import MIMEText
from app.core.config import settings

def generate_otp():
    return str(random.randint(100000, 999999))


def authenticate_admin(db: Session, email: str, password: str):
    admin = db.query(Admin).filter(Admin.email == email).first()
    
    if not admin:
        return None, None, None
    
    if not verify_password(password, admin.password):
        return None, None, None

    access_token = create_access_token({"sub": str(admin.id), "role": "admin"})
    refresh_token = create_refresh_token({"sub": str(admin.id), "role": "admin"})
    
    return admin, access_token, refresh_token



def send_otp_email(to_email: str, otp: str):
    subject = "Password Reset OTP"
    body = f"Your OTP is {otp}. It is valid for 5 minutes."

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_ADDRESS
    msg["To"] = to_email

    with smtplib.SMTP_SSL(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
        server.login(settings.EMAIL_ADDRESS, settings.EMAIL_PASSWORD)
        server.sendmail(settings.EMAIL_ADDRESS, to_email, msg.as_string())
