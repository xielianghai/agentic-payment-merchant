import logging
import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.admin import router as admin_router
from api.registry import router as registry_router
from config import get_settings

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Merchant Management Platform API",
    version="1.0.0",
    description="Merchant onboarding, capability registration, and registry for Agentic Payment Demo.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(registry_router)


@app.exception_handler(Exception)
async def global_exception_handler(_request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception")
    return JSONResponse(status_code=500, content={"code": type(exc).__name__, "message": str(exc)})


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, Any]:
    return {"code": "ok", "data": {"status": "healthy", "version": "1.0.0"}}


def main() -> None:
    import uvicorn

    host = os.getenv("API_HOST", settings.api_host)
    port = int(os.getenv("API_PORT", str(settings.api_port)))
    uvicorn.run("main:app", host=host, port=port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
