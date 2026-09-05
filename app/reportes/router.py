from fastapi import APIRouter
router = APIRouter(prefix="/reportes", tags=["reportes"])
@router.get("/health")
async def health(): return {"success": True, "data": {"status": "reportes ok"}}
