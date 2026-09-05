from fastapi import APIRouter
router = APIRouter(prefix="/equipos", tags=["equipos"])
@router.get("/health")
async def health(): return {"success": True, "data": {"status": "equipos ok"}}
