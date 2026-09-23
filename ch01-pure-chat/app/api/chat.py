from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_chat_model
from app.api.sse import encode_sse
from app.core.config import Settings, get_settings
from app.core.messages import MessageBudgetExceeded
from app.schemas.chat import ChatRequest
from app.services.chat import prepare_chat_messages, stream_chat


router = APIRouter(tags=["chat"])


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    model: Annotated[Any, Depends(get_chat_model)],
) -> StreamingResponse:
    try:
        messages = prepare_chat_messages(request, settings.history_max_tokens)
    except MessageBudgetExceeded as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def events() -> AsyncIterator[str]:
        try:
            async for token in stream_chat(messages, model):
                yield encode_sse("token", {"content": token})
        except Exception:
            yield encode_sse(
                "error",
                {"code": "upstream_error", "message": "模型服务暂时不可用"},
            )
            return
        yield encode_sse("done", {})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
