from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.extraction import router as extraction_router
from app.core.config import Settings, get_settings
from app.core.model import create_chat_model
from app.db.base import create_database_engine, create_session_factory
from app.db.repository import Repository
from app.services.chat import ChatOrchestrator
from app.tools.business import build_business_tools
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry, ToolSpec


STATIC_DIR = Path(__file__).resolve().parent / "static"


def _build_chat_orchestrator(
    settings: Settings,
    repository: Repository,
) -> ChatOrchestrator:
    tools = build_business_tools(repository)
    specs = [
        ToolSpec(
            tool=tool,
            read_only=tool.name != "create_ticket",
            timeout_seconds=settings.tool_timeout_seconds,
            max_attempts=(
                1 if tool.name == "create_ticket" else settings.tool_max_attempts
            ),
            inject_conversation_id=tool.name == "create_ticket",
        )
        for tool in tools
    ]
    registry = ToolRegistry(specs)
    executor = ToolExecutor(registry)
    model = create_chat_model(settings)
    return ChatOrchestrator(
        repository=repository,
        registry=registry,
        executor=executor,
        model=model,
        history_max_tokens=settings.history_max_tokens,
    )


def create_app(settings_loader: Callable[[], Settings] = get_settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        settings = settings_loader()
        engine = create_database_engine(settings)
        repository: Repository | None = None
        try:
            session_factory = create_session_factory(engine)
            repository = Repository(session_factory)
            application.state.chat_orchestrator = _build_chat_orchestrator(
                settings,
                repository,
            )
            yield
        finally:
            try:
                if repository is not None:
                    await repository.close()
            finally:
                await engine.dispose()

    application = FastAPI(title="MewHelp", version="0.1.0", lifespan=lifespan)
    application.include_router(chat_router)
    application.include_router(extraction_router)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    async def chat_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "chat.html")

    return application


app = create_app()
