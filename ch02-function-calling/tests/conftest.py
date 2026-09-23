from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import Conversation, Faq, Message, Ticket


FAQ_SEED_ROWS = (
    {
        "question": "退货政策是什么",
        "answer": "商品满足条件时支持七天无理由退货，具体以商品页面和平台规则为准。",
        "category": "售后",
    },
    {
        "question": "换货需要什么条件",
        "answer": "商品符合换货条件时，请在订单页面发起申请并保持商品及包装完好。",
        "category": "售后",
    },
    {
        "question": "退款多久到账",
        "answer": "退款成功后通常按原支付渠道退回，到账时间以支付机构处理进度为准。",
        "category": "售后",
    },
    {
        "question": "会员有什么权益",
        "answer": "会员权益请以会员中心当前展示的等级说明为准。",
        "category": "会员",
    },
    {
        "question": "如何开发票",
        "answer": "请在订单页面提交发票信息，具体开票范围以订单详情为准。",
        "category": "发票",
    },
    {
        "question": "运费怎么算",
        "answer": "达到包邮门槛免运费，否则按结算页面展示的金额收取。",
        "category": "配送",
    },
)


@pytest_asyncio.fixture
async def test_engine() -> AsyncIterator[AsyncEngine]:
    settings = get_settings()
    engine = create_async_engine(
        settings.test_database_url.get_secret_value(), pool_pre_ping=True
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def test_session_factory(
    test_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def _restore_test_data(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(delete(Ticket))
        await session.execute(delete(Message))
        await session.execute(delete(Conversation))
        await session.execute(delete(Faq))
        await session.execute(insert(Faq), FAQ_SEED_ROWS)


@pytest_asyncio.fixture(autouse=True)
async def clean_test_database(
    request: pytest.FixtureRequest,
) -> AsyncIterator[None]:
    if Path(str(request.node.path)).name != "test_repository.py":
        yield
        return

    settings = get_settings()
    engine = create_async_engine(
        settings.test_database_url.get_secret_value(), pool_pre_ping=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _restore_test_data(session_factory)
        yield
        await _restore_test_data(session_factory)
    finally:
        await engine.dispose()
