import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import Conversation, Message, Ticket
from app.db.repository import Repository, TurnBusy


@pytest.fixture
def repository(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> Repository:
    return Repository(test_session_factory)


async def test_conversation_lookup_requires_matching_user(
    repository: Repository,
) -> None:
    conversation = await repository.create_conversation("owner")

    assert await repository.get_conversation(conversation.id, "owner") is not None
    assert await repository.get_conversation(conversation.id, "another-user") is None
    assert await repository.get_conversation(conversation.id + 1, "owner") is None


async def test_mysql_turn_slot_rejects_other_repository_and_releases_on_error(
    repository: Repository,
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conversation = await repository.create_conversation("owner")
    second_worker = Repository(test_session_factory)

    with pytest.raises(ValueError, match="test failure"):
        async with repository.turn_slot(conversation.id):
            with pytest.raises(TurnBusy):
                async with second_worker.turn_slot(conversation.id):
                    pytest.fail("overlapping turn was admitted")
            raise ValueError("test failure")

    async with second_worker.turn_slot(conversation.id):
        pass


async def test_distinct_turn_locks_do_not_starve_business_connection_pool() -> None:
    engine = create_async_engine(
        get_settings().test_database_url.get_secret_value(),
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.25,
    )
    repository = Repository(async_sessionmaker(engine, expire_on_commit=False))
    try:
        first = await repository.create_conversation("first")
        second = await repository.create_conversation("second")
        async with repository.turn_slot(first.id):
            async with repository.turn_slot(second.id):
                await repository.append_message(first.id, "user", "first question")
                await repository.append_message(second.id, "user", "second question")
        assert [row.content for row in await repository.list_replay_messages(first.id)] == ["first question"]
        assert [row.content for row in await repository.list_replay_messages(second.id)] == ["second question"]
    finally:
        await repository.close()
        await engine.dispose()


async def test_messages_preserve_complete_tool_trace_order(
    repository: Repository,
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conversation = await repository.create_conversation("trace-user")
    await repository.append_message(conversation.id, "user", "查订单")
    await repository.append_message(
        conversation.id,
        "assistant",
        None,
        tool_calls=[
            {"id": "call-1", "name": "query_order", "args": {"order_id": "1001"}}
        ],
    )
    await repository.append_message(
        conversation.id,
        "tool",
        '{"ok":true}',
        tool_call_id="call-1",
    )
    await repository.append_message(conversation.id, "assistant", "订单已发货")

    async with test_session_factory() as session:
        rows = list(
            (
                await session.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation.id)
                    .order_by(Message.created_at, Message.id)
                )
            ).all()
        )

    assert [row.role for row in rows] == ["user", "assistant", "tool", "assistant"]
    assert rows[1].tool_calls == [
        {"id": "call-1", "name": "query_order", "args": {"order_id": "1001"}}
    ]
    assert rows[2].tool_call_id == "call-1"
    assert rows[3].content == "订单已发货"


async def test_replay_excludes_tool_trace_and_keeps_final_answers(
    repository: Repository,
) -> None:
    conversation = await repository.create_conversation("replay-user")
    await repository.append_message(conversation.id, "user", "查物流")
    await repository.append_message(
        conversation.id,
        "assistant",
        None,
        tool_calls=[
            {
                "id": "call-logistics",
                "name": "query_logistics",
                "args": {"order_id": "1001"},
            }
        ],
    )
    await repository.append_message(
        conversation.id,
        "tool",
        '{"ok":true}',
        tool_call_id="call-logistics",
    )
    await repository.append_message(conversation.id, "assistant", "包裹正在派送")

    replay = await repository.list_replay_messages(conversation.id)

    assert [(row.role, row.content) for row in replay] == [
        ("user", "查物流"),
        ("assistant", "包裹正在派送"),
    ]


async def test_faq_like_hits_return_policy(repository: Repository) -> None:
    result = await repository.find_faq("退货政策")

    assert result is not None
    assert result.question == "退货政策是什么"


async def test_faq_like_does_not_rewrite_postage_to_shipping(
    repository: Repository,
) -> None:
    assert await repository.find_faq("邮费是多少") is None


async def test_ticket_creation_updates_conversation_in_the_same_transaction(
    repository: Repository,
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conversation = await repository.create_conversation("ticket-user")

    ticket = await repository.create_ticket(conversation.id, "商品破损", "售后")

    async with test_session_factory() as session:
        stored_ticket = await session.get(Ticket, ticket.ticket_no)
        stored_conversation = await session.get(Conversation, conversation.id)
    assert ticket.ticket_no.startswith("T")
    assert len(ticket.ticket_no) <= 32
    assert stored_ticket is not None
    assert stored_ticket.description == "商品破损"
    assert stored_ticket.status == "待处理"
    assert stored_conversation is not None
    assert stored_conversation.status == "已转人工"


async def test_ticket_failure_rolls_back_conversation_status(
    repository: Repository,
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    conversation = await repository.create_conversation("rollback-user")

    with pytest.raises(SQLAlchemyError):
        await repository.create_ticket(conversation.id, "无效类型", "不存在")

    async with test_session_factory() as session:
        stored_conversation = await session.get(Conversation, conversation.id)
        tickets = list(
            (
                await session.scalars(
                    select(Ticket).where(Ticket.conversation_id == conversation.id)
                )
            ).all()
        )
    assert stored_conversation is not None
    assert stored_conversation.status == "进行中"
    assert tickets == []
