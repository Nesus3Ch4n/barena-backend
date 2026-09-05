from fastapi import APIRouter
router = APIRouter(prefix="/partidos", tags=["partidos"])
@router.get("/health")
async def health(): return {"success": True, "data": {"status": "partidos ok"}}
