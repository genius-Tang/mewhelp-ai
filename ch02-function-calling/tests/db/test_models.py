from sqlalchemy.dialects import mysql

from app.core.config import Settings
from app.db.base import Base, create_database_engine, create_session_factory
from app.db.models import Conversation, Faq, Message, Ticket


def test_metadata_contains_exact_chapter_two_tables() -> None:
    assert set(Base.metadata.tables) == {"faq", "conversations", "messages", "tickets"}


def test_message_trace_columns_are_present() -> None:
    table = Message.__table__
    assert {"conversation_id", "role", "content", "tool_calls", "tool_call_id", "created_at"} <= set(table.c.keys())
    assert table.c.tool_calls.nullable is True
    assert table.c.tool_call_id.nullable is True


def test_timestamp_and_width_columns_match_the_authoritative_ddl() -> None:
    assert {"created_at", "updated_at"} <= set(Conversation.__table__.c.keys())
    assert {"created_at", "updated_at"} <= set(Faq.__table__.c.keys())
    assert Conversation.__table__.c.user_id.type.length == 64
    assert Message.__table__.c.tool_call_id.type.length == 64


def test_ticket_number_is_the_ticket_primary_key() -> None:
    assert [column.name for column in Ticket.__table__.primary_key.columns] == ["ticket_no"]
    assert Ticket.__table__.c.ticket_no.type.length == 32


def test_unsigned_ids_and_native_enums_match_the_authoritative_ddl() -> None:
    for column in (
        Conversation.__table__.c.id,
        Message.__table__.c.id,
        Message.__table__.c.conversation_id,
        Faq.__table__.c.id,
        Ticket.__table__.c.conversation_id,
    ):
        assert isinstance(column.type, mysql.BIGINT)
        assert column.type.unsigned is True

    assert Conversation.__table__.c.status.type.enums == ["进行中", "已转人工", "已结束"]
    assert Message.__table__.c.role.type.enums == ["user", "assistant", "tool"]
    assert Ticket.__table__.c.ticket_type.type.enums == ["售后", "投诉", "咨询"]
    assert Ticket.__table__.c.status.type.enums == ["待处理", "已处理"]


def test_foreign_keys_have_no_delete_action() -> None:
    for table in (Message.__table__, Ticket.__table__):
        foreign_key = next(iter(table.foreign_keys))
        assert foreign_key.ondelete is None
        assert foreign_key.column is Conversation.__table__.c.id


async def test_engine_and_session_factory_use_configured_database() -> None:
    settings = Settings(
        chat_base_url="https://example.test/v1",
        chat_api_key="secret",
        chat_model="example-model",
        database_url="mysql+asyncmy://user:password@localhost/mewhelp",
        test_database_url="mysql+asyncmy://user:password@localhost/mewhelp_test",
        _env_file=None,
    )
    engine = create_database_engine(settings)
    try:
        assert engine.url.database == "mewhelp"
        factory = create_session_factory(engine)
        async with factory() as session:
            assert session.bind is engine
            assert session.sync_session.expire_on_commit is False
    finally:
        await engine.dispose()
