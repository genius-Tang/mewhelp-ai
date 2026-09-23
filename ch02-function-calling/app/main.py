from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.extraction import router as extraction_router
from app.core.config import Settings, get_settings


STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings_loader: Callable[[], Settings] = get_settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings_loader()
        yield

    application = FastAPI(title="MewHelp", version="0.1.0", lifespan=lifespan)
    application.include_router(chat_router)
    application.include_router(extraction_router)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    async def chat_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "chat.html")

    return application


app = create_app()
