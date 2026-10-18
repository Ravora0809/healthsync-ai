from fastapi import APIRouter
from app.api.v1.endpoints import auth,records,evidence,vaccinations,reminders,assistant,profile_sharing
api_router=APIRouter()
api_router.include_router(auth.router,prefix="/auth")
api_router.include_router(records.router,prefix="/medical-records")
api_router.include_router(evidence.router,prefix="/evidence")
api_router.include_router(vaccinations.router,prefix="/vaccinations")
api_router.include_router(reminders.router,prefix="/reminders")
api_router.include_router(assistant.router,prefix="/assistant")

api_router.include_router(profile_sharing.router, prefix="/secure-sharing")
