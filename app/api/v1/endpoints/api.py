from fastapi import APIRouter
from app.api.v1.endpoints import user, pnl, balance_sheet, valuation, admin

api_router = APIRouter()
api_router.include_router(user.router, prefix="/users", tags=["users"])
api_router.include_router(pnl.router, prefix="/pnl", tags=["pnl"])
api_router.include_router(balance_sheet.router, prefix="/balance-sheet", tags=["balance-sheet"])
api_router.include_router(valuation.router, prefix="/valuation", tags=["valuation"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
