from uuid import uuid4

from sqlalchemy import and_, null, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Faq, Message, Ticket


class Repository:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory

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
