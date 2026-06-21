from fastapi import APIRouter
from app.api.v1.endpoints import auth, samples, anomaly, audit

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(samples.router, prefix="/samples", tags=["samples"])
api_router.include_router(anomaly.router, prefix="/anomaly", tags=["anomaly"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])