from fastapi import APIRouter
router = APIRouter(prefix="/config", tags=["config"])
@router.get("/health")
async def health(): return {"success": True, "data": {"status": "config ok"}}
@router.get("/flags")
async def flags(): return {"success": True, "data": {"freemium": True, "realtime_enabled": True}}
