import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from threading import Lock
from weakref import WeakKeyDictionary
from uuid import uuid4

from sqlalchemy import and_, null, or_, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import Conversation, Faq, Message, Ticket


class TurnBusy(RuntimeError):
    """A conversation already has an unfinished turn."""


_fallback_guard = Lock()
_fallback_occupied: WeakKeyDictionary[object, set[int]] = WeakKeyDictionary()


class Repository:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory
        self._lock_engine: AsyncEngine | None = None
        self._lock_engine_guard = Lock()

    def _turn_lock_engine(self, business_engine: AsyncEngine) -> AsyncEngine:
        if self._lock_engine is None:
            with self._lock_engine_guard:
                if self._lock_engine is None:
                    self._lock_engine = create_async_engine(
                        business_engine.url,
                        poolclass=NullPool,
                        pool_pre_ping=True,
                    )
        return self._lock_engine

    async def close(self) -> None:
        if self._lock_engine is not None:
            await self._lock_engine.dispose()

    @asynccontextmanager
    async def turn_slot(self, conversation_id: int) -> AsyncIterator[None]:
        engine = self._session_factory.kw["bind"]
        if engine.dialect.name != "mysql":
            # Test databases share this nonblocking reservation within one process.
            with _fallback_guard:
                occupied = _fallback_occupied.setdefault(engine, set())
                if conversation_id in occupied:
                    raise TurnBusy("会话正在处理上一条消息，请稍后重试")
                occupied.add(conversation_id)
            try:
                yield
            finally:
                with _fallback_guard:
                    occupied.remove(conversation_id)
            return

        lock_name = f"mewhelp:conversation:{conversation_id}"
        async with self._turn_lock_engine(engine).connect() as connection:
            acquired = await connection.scalar(
                text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name}
            )
            if acquired != 1:
                raise TurnBusy("会话正在处理上一条消息，请稍后重试")
            try:
                yield
            finally:
                release = asyncio.create_task(
                    connection.scalar(
                        text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name}
                    )
                )
                try:
                    await asyncio.shield(release)
                except asyncio.CancelledError:
                    await release
                    raise

    async def create_conversation(self, user_id: str) -> Conversation:
        async with self._session_factory() as session, session.begin():
            conversation = Conversation(user_id=user_id)
            session.add(conversation)
            await session.flush()
            return conversation

    async def get_conversation(
        self, conversation_id: int, user_id: str
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        async with self._session_factory() as session:
            return await session.scalar(statement)

    async def append_message(
        self,
        conversation_id: int,
        role: str,
        content: str | None,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
    ) -> Message:
        async with self._session_factory() as session, session.begin():
            message = Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                tool_calls=tool_calls if tool_calls is not None else null(),
                tool_call_id=tool_call_id,
            )
            session.add(message)
            await session.flush()
            return message

    async def list_replay_messages(self, conversation_id: int) -> list[Message]:
        statement = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                or_(
                    Message.role == "user",
                    and_(
                        Message.role == "assistant",
                        Message.content.is_not(None),
                        Message.content != "",
                        Message.tool_calls.is_(None),
                    ),
                ),
            )
            .order_by(Message.created_at, Message.id)
        )
        async with self._session_factory() as session:
            return list((await session.scalars(statement)).all())

    async def find_faq(self, keyword: str) -> Faq | None:
        statement = (
            select(Faq)
            .where(Faq.question.like(f"%{keyword}%"))
            .order_by(Faq.id)
            .limit(1)
        )
        async with self._session_factory() as session:
            return await session.scalar(statement)

    async def create_ticket(
        self, conversation_id: int, description: str, ticket_type: str
    ) -> Ticket:
        async with self._session_factory() as session, session.begin():
            conversation = await session.scalar(
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .with_for_update()
            )
            if conversation is None:
                raise LookupError(f"conversation {conversation_id} does not exist")

            ticket = Ticket(
                ticket_no=f"T{uuid4().hex[:31]}",
                conversation_id=conversation_id,
                description=description,
                ticket_type=ticket_type,
            )
            conversation.status = "已转人工"
            session.add(ticket)
            await session.flush()
            return ticket
