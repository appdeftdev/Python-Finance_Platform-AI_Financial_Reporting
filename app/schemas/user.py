from pydantic import BaseModel, EmailStr
from typing import Optional, Any, List

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr

    class Config:
        from_attributes = True

class UserBasicDetailsCreate(BaseModel):
    company_name: str
    industry: str
    city: str
    country: str
    company_size: str
    competitors: str
    business_model: List[str]
    fin_year: Optional[str] = None
    projections: Optional[int] = None
    currency: Optional[str] = None
    base_year: Optional[str] = None


class CompanyUpdateRequest(BaseModel):
    company_name: Optional[str] = None
    competitors: Optional[str] = None


class UserBasicDetailsUpdate(BaseModel):
    company_name: str
    industry: str
    city: str
    country: str
    company_size: str
    competitors: str
    business_model: List[str]
    fin_year: Optional[str] = None
    projections: Optional[int] = None
    currency: Optional[str] = None
    base_year: Optional[int] = None



class UserBasicDetailsOut(BaseModel):
    id: int
    user_id: int
    company_name: str
    industry: str
    city: str
    country: str
    company_size: str
    competitors: str
    business_model: Optional[List[str]] = None
    fin_year: Optional[str] = None
    projections: Optional[int] = None
    currency: Optional[str] = None
    base_year: Optional[str] = None

    class Config:
        from_attributes = True

class ResetProgressRequest(BaseModel):
    topic: str  # "pnl", "balance sheet", "all", etc.
    subject: str  # "revenue", "returns", "all", etc.

class SkipTopicRequest(BaseModel):
    topic: str  # "interest_expense", "returns", "depreciation_and_amortisation", etc.

class StandardResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None 