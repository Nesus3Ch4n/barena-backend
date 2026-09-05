from fastapi import APIRouter
router = APIRouter(prefix="/estadisticas", tags=["estadisticas"])
@router.get("/health")
async def health(): return {"success": True, "data": {"status": "estadisticas ok"}}
