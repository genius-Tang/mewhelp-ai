from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import Conversation, Faq, Message, Ticket
from app.db.repository import Repository
from app.tools.business import (
    build_business_tools,
    query_logistics,
    query_order,
    query_product,
)


FAQ_ROWS = (
    {
        "question": "退货政策是什么",
        "answer": "商品满足条件时支持七天无理由退货，具体以商品页面和平台规则为准。",
        "category": "售后",
    },
    {
        "question": "运费怎么算",
        "answer": "达到包邮门槛免运费，否则按结算页面展示的金额收取。",
        "category": "配送",
    },
)


@pytest_asyncio.fixture
async def tool_database() -> AsyncIterator[
    tuple[Repository, async_sessionmaker[AsyncSession]]
]:
    settings = get_settings()
    engine: AsyncEngine = create_async_engine(
        settings.test_database_url.get_secret_value(), pool_pre_ping=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def reset() -> None:
        async with session_factory() as session, session.begin():
            await session.execute(delete(Ticket))
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.execute(delete(Faq))
            session.add_all(Faq(**row) for row in FAQ_ROWS)

    try:
        await reset()
        yield Repository(session_factory), session_factory
        await reset()
    finally:
        await engine.dispose()


def test_business_tools_expose_stable_names_and_model_schemas(
    tool_database: tuple[Repository, async_sessionmaker[AsyncSession]],
) -> None:
    repository, _ = tool_database
    tools = build_business_tools(repository)

    assert [tool.name for tool in tools] == [
        "query_order",
        "query_product",
        "query_logistics",
        "query_faq",
        "create_ticket",
    ]
    assert query_order.name == "query_order"
    assert query_product.name == "query_product"
    assert query_logistics.name == "query_logistics"

    schemas = {
        tool.name: tool.tool_call_schema.model_json_schema() for tool in tools
    }
    assert set(schemas["query_order"]["properties"]) == {"order_id"}
    assert set(schemas["query_product"]["properties"]) == {"product_name"}
    assert set(schemas["query_logistics"]["properties"]) == {"order_id"}
    assert set(schemas["query_faq"]["properties"]) == {"keyword"}
    assert set(schemas["create_ticket"]["properties"]) == {
        "description",
        "ticket_type",
    }
    assert "conversation_id" not in schemas["create_ticket"]["properties"]


@pytest.mark.asyncio
async def test_mock_tools_return_stable_seeded_business_data() -> None:
    order = await query_order.ainvoke({"order_id": " 1001 "})
    product = await query_product.ainvoke({"product_name": " 星空猫窝 "})
    logistics = await query_logistics.ainvoke({"order_id": " 1001 "})

    assert order == {
        "order_id": "1001",
        "status": "待付款",
        "amount": 284.47,
        "item_count": 1,
    }
    assert product == {
        "product_name": "星空猫窝",
        "price": 408.68,
        "stock": 370,
        "available": True,
    }
    assert logistics == {
        "order_id": "1001",
        "carrier": "中通快递",
        "tracking_no": "MOCK4170686075",
        "status": "已揽收",
        "timeline": ["快递员正在派送", "等待更新"],
    }

    assert await query_order.ainvoke({"order_id": "1001"}) == order
    assert await query_product.ainvoke({"product_name": "星空猫窝"}) == product
    assert await query_logistics.ainvoke({"order_id": "1001"}) == logistics


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("query_order", {"order_id": "   "}),
        ("query_product", {"product_name": "   "}),
        ("query_logistics", {"order_id": "   "}),
        ("query_faq", {"keyword": "   "}),
    ],
)
async def test_query_tools_reject_blank_model_arguments(
    tool_database: tuple[Repository, async_sessionmaker[AsyncSession]],
    tool_name: str,
    arguments: dict[str, str],
) -> None:
    repository, _ = tool_database
    tools = {tool.name: tool for tool in build_business_tools(repository)}

    with pytest.raises(ValidationError):
        await tools[tool_name].ainvoke(arguments)


@pytest.mark.asyncio
async def test_query_faq_returns_literal_like_hit_and_expected_miss(
    tool_database: tuple[Repository, async_sessionmaker[AsyncSession]],
) -> None:
    repository, _ = tool_database
    faq_tool = {tool.name: tool for tool in build_business_tools(repository)}[
        "query_faq"
    ]

    assert await faq_tool.ainvoke({"keyword": "退货政策"}) == {
        "found": True,
        "question": "退货政策是什么",
        "answer": "商品满足条件时支持七天无理由退货，具体以商品页面和平台规则为准。",
        "category": "售后",
    }
    assert await faq_tool.ainvoke({"keyword": "邮费是多少"}) == {
        "found": False,
        "keyword": "邮费是多少",
    }


@pytest.mark.asyncio
async def test_create_ticket_hides_and_uses_trusted_conversation_id(
    tool_database: tuple[Repository, async_sessionmaker[AsyncSession]],
) -> None:
    repository, session_factory = tool_database
    conversation = await repository.create_conversation("tool-test-user")
    tools = {tool.name: tool for tool in build_business_tools(repository)}
    schema = tools["create_ticket"].tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"description", "ticket_type"}
    assert "conversation_id" not in schema["properties"]

    result = await tools["create_ticket"].ainvoke(
        {
            "description": "商品破损，请安排人工跟进",
            "ticket_type": "售后",
            "conversation_id": conversation.id,
        }
    )

    async with session_factory() as session:
        ticket = await session.scalar(
            select(Ticket).where(Ticket.ticket_no == result["ticket_no"])
        )
        persisted_conversation = await session.get(Conversation, conversation.id)

    assert result == {"ticket_no": ticket.ticket_no, "status": "待处理"}
    assert ticket.conversation_id == conversation.id
    assert ticket.description == "商品破损，请安排人工跟进"
    assert ticket.ticket_type == "售后"
    assert persisted_conversation.status == "已转人工"
