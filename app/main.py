from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.extraction import router as extraction_router
from app.core.config import Settings, get_settings


def create_app(settings_loader: Callable[[], Settings] = get_settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings_loader()
        yield

    application = FastAPI(title="MewHelp", version="0.1.0", lifespan=lifespan)
    application.include_router(chat_router)
    application.include_router(extraction_router)
    return application


app = create_app()
