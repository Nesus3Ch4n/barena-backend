from fastapi import APIRouter
router = APIRouter(prefix="/rankings", tags=["rankings"])
@router.get("/health")
async def health(): return {"success": True, "data": {"status": "rankings ok"}}
