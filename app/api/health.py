from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe for the container healthcheck. No auth, no DB access."""
    return {"status": "ok"}
