from fastapi import APIRouter
router = APIRouter(prefix="/torneos", tags=["torneos"])
@router.get("/health")
async def health(): return {"success": True, "data": {"status": "torneos ok"}}
