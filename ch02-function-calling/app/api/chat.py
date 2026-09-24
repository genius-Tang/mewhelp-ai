from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_chat_orchestrator
from app.api.sse import encode_sse
from app.schemas.chat import ChatRequest
from app.services.chat import (
    ChatOrchestrator,
    ConversationNotFound,
    DoneEvent,
    MultipleToolCalls,
    TokenEvent,
    ToolEvent,
)


router = APIRouter(tags=["chat"])


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    orchestrator: Annotated[ChatOrchestrator, Depends(get_chat_orchestrator)],
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        try:
            async for event in orchestrator.stream_turn(
                request.user_id,
                request.message,
                request.conversation_id,
            ):
                if isinstance(event, ToolEvent):
                    yield encode_sse(
                        "tool",
                        {"name": event.name, "status": event.status},
                    )
                elif isinstance(event, TokenEvent):
                    yield encode_sse("token", {"content": event.content})
                elif isinstance(event, DoneEvent):
                    yield encode_sse(
                        "done",
                        {
                            "conversation_id": event.conversation_id,
                            "tools": list(event.tools),
                        },
                    )
                    return
        except ConversationNotFound:
            yield encode_sse(
                "error",
                {"code": "conversation_not_found", "message": "会话不存在"},
            )
            return
        except MultipleToolCalls:
            yield encode_sse(
                "error",
                {
                    "code": "multiple_tool_calls",
                    "message": "模型返回了多个工具调用",
                },
            )
            return
        except SQLAlchemyError:
            yield encode_sse(
                "error",
                {"code": "database_error", "message": "数据库暂时不可用"},
            )
            return
        except Exception:
            yield encode_sse(
                "error",
                {"code": "upstream_error", "message": "模型服务暂时不可用"},
            )
            return

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
