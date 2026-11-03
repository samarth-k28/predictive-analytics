"""FastAPI app: serves the dashboard, the model API, and the static frontend."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.model import Bundle, build_bundle, predict

STATIC = Path(__file__).resolve().parent / "static"


class PredictRequest(BaseModel):
    hour: int = Field(ge=0, le=23)
    season: Literal["Spring", "Summer", "Autumn", "Winter"]
    weekend: bool = False
    holiday: bool = False
    temperature: float = Field(ge=-20, le=40)
    humidity: float = Field(ge=0, le=100)
    rainfall: float = Field(ge=0, le=50)

    model_config = {"extra": "forbid"}


def create_app(bundle: Bundle | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.bundle = bundle or build_bundle()
        yield

    app = FastAPI(title="Seoul Velo", lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/dashboard")
    def dashboard() -> dict:
        return app.state.bundle.payload

    @app.post("/api/predict")
    def forecast(request: PredictRequest) -> dict:
        return predict(app.state.bundle, request.model_dump())

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/report", include_in_schema=False)
    def report() -> FileResponse:
        return FileResponse(STATIC / "report.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
