from fastapi import APIRouter

router = APIRouter(prefix="/v2/health", tags=["health"])


@router.get("/live", summary="Liveness probe (v2)")
def live_v2():
    return {"status": "ok", "version": "v2"}
