from pydantic import BaseModel, field_validator
from typing import Optional, Any, Dict, List, Union


class Way2Data(BaseModel):
    fin_year: str
    projections: int
    currency: str


class RevenueStreamCreate(BaseModel):
    data_json: Optional[Dict[str, Any]] = None
    projected_titles: Optional[Dict[str, Any]] = None
    fin_year: Optional[str] = None
    projections: Optional[int] = None
    currency: Optional[str] = None


class RevenueStreamOut(BaseModel):
    id: int
    pnl_id: int
    data_json: Optional[Dict[str, Any]] = None
    projected_titles: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class ReturnCreate(BaseModel):
    data_json: Optional[Dict[str, Any]] = None
    projected_titles: Optional[Dict[str, Any]] = None


class ReturnOut(BaseModel):
    id: int
    revenue_id: int
    data_json: Optional[Dict[str, Any]] = None
    projected_titles: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class COGSCreate(BaseModel):
    data_json: Optional[Dict[str, Any]] = None
    projected_titles: Optional[Dict[str, Any]] = None


class COGSOut(BaseModel):
    id: int
    pnl_id: int
    data_json: Optional[Dict[str, Any]] = None
    projected_titles: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class OperatingExpensesCreate(BaseModel):
    data_json: Optional[Dict[str, Any]] = None
    projected_titles: Optional[Dict[str, Any]] = None


class OperatingExpensesOut(BaseModel):
    id: int
    pnl_id: int
    data_json: Optional[Dict[str, Any]] = None
    projected_titles: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class StandardResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None


# New schemas for revenue save API (clean version without extra fields)
class RevenueProductData(BaseModel):
    name: str
    revenue: list
    units_sold: Optional[int] = None
    average_price: Optional[float] = None
    month_1: Optional[float] = None
    growth_rate: Optional[float] = None  # Growth rate as percentage (e.g., 10.5 for 10.5%)
    
    @field_validator('growth_rate')
    @classmethod
    def validate_growth_rate(cls, v):
        if v is not None:
            if not isinstance(v, (int, float)):
                raise ValueError('Growth rate must be a number')
            if v < 0 or v > 1000:  # Reasonable range for growth rates
                raise ValueError('Growth rate must be between 0 and 1000%')
        return v


class RevenueDataStructure(BaseModel):
    years: Optional[list] = None
    products: list[RevenueProductData]
    total_revenue: Optional[list] = None


class RevenueSaveRequest(BaseModel):
    revenue_id: int
    data_json: RevenueDataStructure


class RevenueSaveResponse(BaseModel):
    product_name: str
    revenue: list
    units_sold: Optional[int] = None
    average_price: Optional[float] = None
    month_1: Optional[float] = None
    growth_rate: Optional[float] = None  # Growth rate as percentage (e.g., 10.5 for 10.5%)
    revenue_id: int


# New schemas for revenue calculation API
class Y1Data(BaseModel):
    number_of_months: int
    y1_revenue: float

class RevenueRowData(BaseModel):
    revenue_id: int
    product_name: str
    units_sold: int
    average_price: float
    month_1: float
    y1_data: Y1Data




class CogsCalculationResponse(BaseModel):
    product_name: str
    cogs: list
    cogs_percentage: float
    formula_id: Optional[int] = None


# COGS save schemas
class CogsProductData(BaseModel):
    name: str
    cogs: list
    units_sold: Optional[float] = None
    average_price: Optional[float] = None
    month_1: Optional[float] = None
    growth_rate: Optional[float] = None  # Growth rate as percentage (e.g., 8.5 for 8.5%)
    
    @field_validator('growth_rate')
    @classmethod
    def validate_growth_rate(cls, v):
        if v is not None:
            if not isinstance(v, (int, float)):
                raise ValueError('Growth rate must be a number')
            if v < 0 or v > 1000:  # Reasonable range for growth rates
                raise ValueError('Growth rate must be between 0 and 1000%')
        return v

class CogsDataStructure(BaseModel):
    years: Optional[list] = None
    products: list[CogsProductData]
    total_cogs: Optional[list] = None


class CogsSaveRequest(BaseModel):
    cogs_id: int
    data_json: CogsDataStructure


class CogsSaveResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    cogs_id: int


# New schemas for returns save API (clean version without extra fields)
class ReturnsProductData(BaseModel):
    name: str
    returns: list
    units_returned: Optional[int] = None
    average_price: Optional[float] = None


class ReturnsDataStructure(BaseModel):
    years: Optional[list] = None
    products: list[ReturnsProductData]
    total_returns: Optional[list] = None


class ReturnsSaveRequest(BaseModel):
    return_id: int
    data_json: ReturnsDataStructure


class ReturnsSaveResponse(BaseModel):
    product_name: str
    returns: list
    units_returned: Optional[int] = None
    average_price: Optional[float] = None
    return_id: int


# New schemas for returns calculation API
class ReturnsRowData(BaseModel):
    product_name: str
    y1_returns: float
    y0_units_returned: int
    y0_price: float


# Base Year schemas
class BaseYearRequest(BaseModel):
    base_year: int
    
    @field_validator('base_year')
    @classmethod
    def validate_base_year(cls, v):
        if not isinstance(v, int):
            raise ValueError('Base year must be an integer')
        if v < 2000 or v > 2100:  # Reasonable range for base years
            raise ValueError('Base year must be between 2000 and 2100')
        return v


class BaseYearResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class BaseYearGetResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


# Interest Expense schemas
class InterestExpenseLoanData(BaseModel):
    loan_name: str
    amounts: Dict[str, float]  # Y1, Y2, Y3, Y4, Y5
    interest_rate: str
    loan_term_years: int
    payment_type: str


class InterestExpenseDataStructure(BaseModel):
    years: Optional[list] = None
    loans: list[InterestExpenseLoanData]
    total_interest: Optional[Dict[str, float]] = None


class InterestExpenseSaveRequest(BaseModel):
    data_json: Dict[str, Any]  # This will contain the nested structure with data containing years, loans, and total_interest


class InterestExpenseSaveResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    interest_expense_id: int


# Income Before Taxes schemas
class IncomeBeforeTaxesDataStructure(BaseModel):
    data: Dict[str, Any]  # This will contain the nested structure with tax, tax_exp, and net_income


class IncomeBeforeTaxesSaveRequest(BaseModel):
    data_json: IncomeBeforeTaxesDataStructure


class IncomeBeforeTaxesSaveResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    income_before_taxes_id: int


class ConceptRecordsRequest(BaseModel):
    concept: str
    
    @field_validator('concept')
    @classmethod
    def validate_concept(cls, v):
        valid_concepts = [
            "revenue", "cogs", "operating_expenses",
            "depreciation_and_amortisation", "other_income",
            "interest_expense", "income_before_taxes", "all"
        ]
        if v.lower() not in valid_concepts:
            raise ValueError(f"Concept must be one of: {', '.join(valid_concepts)}")
        return v.lower()



