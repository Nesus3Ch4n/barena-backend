from fastapi import APIRouter
router = APIRouter(prefix="/atletas", tags=["atletas"])
@router.get("/health")
async def health(): return {"success": True, "data": {"status": "atletas ok"}}
