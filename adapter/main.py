import logging
import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from routes.discovery import router as discovery_router
from routes.ucp import router as ucp_router

settings = get_settings()
settings.temp_db_dir = os.environ.get("TEMP_DB_DIR", settings.temp_db_dir)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Agentic Payment Merchant Adapter",
    version="1.0.0",
    description="A2A + UCP + AP2 adapter with dynamic merchant routing.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(discovery_router)
app.include_router(ucp_router)


@app.exception_handler(Exception)
async def global_exception_handler(_request, exc: Exception) -> JSONResponse:
    logging.exception("Unhandled exception")
    return JSONResponse(status_code=500, content={"code": type(exc).__name__, "message": str(exc)})


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"code": "ok", "data": {"status": "healthy", "adapter": "ucp+ap2"}}


def main() -> None:
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("API_HOST", settings.api_host),
        port=int(os.getenv("API_PORT", str(settings.api_port))),
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
