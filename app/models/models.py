from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    email = Column(String, unique=True)
    password = Column(String)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime)
    basic_details = relationship("UserBasicDetails", backref="user", cascade="all, delete", passive_deletes=True)
    progress = relationship("UserProgress", backref="user", cascade="all, delete", passive_deletes=True)
    pnl_statements = relationship("PNLStatement", backref="user", cascade="all, delete", passive_deletes=True)
    balance_sheets = relationship("BalanceSheet", backref="user", cascade="all, delete", passive_deletes=True)
    skipped = relationship("Skipped", backref="user", cascade="all, delete", passive_deletes=True)

class UserBasicDetails(Base):
    __tablename__ = 'user_basic_details'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"))
    company_name = Column(String)
    industry = Column(String)
    city = Column(String)
    country = Column(String)
    company_size = Column(String)
    competitors = Column(String)
    business_model = Column(String)
    fin_year = Column(String)
    projections = Column(Integer)
    currency = Column(String)
    base_year = Column(String)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    corrected_json=Column(JSONB)

class UserProgress(Base):
    __tablename__ = 'user_progress'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"))
    user_basic_details = Column(Boolean, default=False)
    pnl_statements = Column(Boolean, default=False)
    balance_sheet = Column(Boolean, default=False)
    # cash_flow_statement = Column(Boolean, default=False)
    valuation = Column(Boolean, default=False)
    charts_n_insights = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class PNLStatement(Base):
    __tablename__ = 'pnl_statements'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"))
    revenue = Column(Boolean, default=False)
    cogs = Column(Boolean, default=False)
    returns = Column(Boolean, default=False)
    operating_expenses = Column(Boolean, default=False)
    depreciation_n_amortisation = Column(Boolean, default=False)
    other_income = Column(Boolean, default=False)
    other_expense = Column(Boolean, default=False)
    interest_expense = Column(Boolean, default=False)
    income_before_taxes = Column(Boolean, default=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    revenue_streams = relationship("RevenueStream", backref="pnl_statement", cascade="all, delete", passive_deletes=True)
    cogs_items = relationship("COGS", backref="pnl_statement", cascade="all, delete", passive_deletes=True)
    operating_expenses_items = relationship("OperatingExpenses", backref="pnl_statement", cascade="all, delete", passive_deletes=True)
    returns_items = relationship("Return", backref="pnl_statement", cascade="all, delete", passive_deletes=True)
    depreciation_n_amortisation_items = relationship("DepreciationNAmortisation", backref="pnl_statement", cascade="all, delete", passive_deletes=True)
    other_income_items = relationship("OtherIncome", backref="pnl_statement", cascade="all, delete", passive_deletes=True)
    other_expense_items = relationship("OtherExpense", backref="pnl_statement", cascade="all, delete", passive_deletes=True)
    interest_expense_items = relationship("InterestExpense", backref="pnl_statement", cascade="all, delete", passive_deletes=True)
    income_before_taxes_items = relationship("IncomeBeforeTaxes", backref="pnl_statement", cascade="all, delete", passive_deletes=True)

class RevenueStream(Base):
    __tablename__ = 'revenue'
    id = Column(Integer, primary_key=True)
    pnl_id = Column(Integer, ForeignKey('pnl_statements.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    projected_titles = Column(JSONB)
    selected_titles = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class COGS(Base):
    __tablename__ = 'cogs'
    id = Column(Integer, primary_key=True)
    pnl_id = Column(Integer, ForeignKey('pnl_statements.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    projected_titles = Column(JSONB)
    selected_titles = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class Skipped(Base):
    __tablename__ = 'skipped'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"))
    returns = Column(Boolean, default=False)
    other_income = Column(Boolean, default=False)
    other_expense = Column(Boolean, default=False)
    depreciation_and_amortisation = Column(Boolean, default=False)
    interest_expense = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class Return(Base):
    __tablename__ = 'returns'
    id = Column(Integer, primary_key=True)
    pnl_id = Column(Integer, ForeignKey('pnl_statements.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    projected_titles = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class OperatingExpenses(Base):
    __tablename__ = 'operating_expenses'
    id = Column(Integer, primary_key=True)
    pnl_id = Column(Integer, ForeignKey('pnl_statements.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    projected_titles = Column(JSONB)
    selected_titles = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class OtherIncome(Base):
    __tablename__ = 'other_income'
    id = Column(Integer, primary_key=True)
    pnl_id = Column(Integer, ForeignKey('pnl_statements.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    projected_titles = Column(JSONB)
    selected_titles = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class OtherExpense(Base):
    __tablename__ = 'other_expense'
    id = Column(Integer, primary_key=True)
    pnl_id = Column(Integer, ForeignKey('pnl_statements.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    projected_titles = Column(JSONB)
    selected_titles = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    
class DepreciationNAmortisation(Base):
    __tablename__ = 'depreciation_n_amortisation'
    id = Column(Integer, primary_key=True)
    pnl_id = Column(Integer, ForeignKey('pnl_statements.id', ondelete="CASCADE"))
    assets_input = Column(JSONB)
    projected_titles = Column(JSONB)
    selected_titles = Column(JSONB)
    data_json = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class InterestExpense(Base):
    __tablename__ = 'interest_expense'
    id = Column(Integer, primary_key=True)
    pnl_id = Column(Integer, ForeignKey('pnl_statements.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class IncomeBeforeTaxes(Base):
    __tablename__ = 'income_before_taxes'
    id = Column(Integer, primary_key=True)
    pnl_id = Column(Integer, ForeignKey('pnl_statements.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class BalanceSheet(Base):
    __tablename__ = 'balance_sheets'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"))
    working_capital = Column(Boolean, default=False)
    inventory = Column(Boolean, default=False)
    bs_records = Column(Boolean, default=False)
    cash_flow_statement = Column(Boolean, default=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    working_capital_items = relationship("WorkingCapital", backref="balance_sheet", cascade="all, delete", passive_deletes=True)
    inventory_items = relationship("Inventory", backref="balance_sheet", cascade="all, delete", passive_deletes=True)
    bs_records_items = relationship("BSRecords", backref="balance_sheet", cascade="all, delete", passive_deletes=True)
    cash_flow_statement_items = relationship("CashFlowStatement", backref="balance_sheet", cascade="all, delete", passive_deletes=True)

class WorkingCapital(Base):
    __tablename__ = 'working_capital'
    id = Column(Integer, primary_key=True)
    balance_sheet_id = Column(Integer, ForeignKey('balance_sheets.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class Inventory(Base):
    __tablename__ = 'inventory'
    id = Column(Integer, primary_key=True)
    balance_sheet_id = Column(Integer, ForeignKey('balance_sheets.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class BSRecords(Base):
    __tablename__ = 'bs_records'
    id = Column(Integer, primary_key=True)
    balance_sheet_id = Column(Integer, ForeignKey('balance_sheets.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class CashFlowStatement(Base):
    __tablename__='cash_flow_statement'
    id = Column(Integer, primary_key=True)
    balance_sheet_id = Column(Integer, ForeignKey('balance_sheets.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    beginning_cash = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    

class Valuation(Base):
    __tablename__ = 'valuation'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"))
    data_json = Column(JSONB)
    projected_titles = Column(JSONB)
    selected_titles = Column(JSONB)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
