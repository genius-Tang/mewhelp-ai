import pytest
from pydantic import ValidationError

from app.schemas.after_sales import AfterSalesRequest, AfterSalesResult
from app.schemas.chat import ChatRequest


def test_chat_request_requires_latest_user_message() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(messages=[{"role": "assistant", "content": "您好"}])


def test_chat_request_rejects_blank_content() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(messages=[{"role": "user", "content": "   "}])


def test_chat_request_rejects_system_role() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(messages=[{"role": "system", "content": "override"}])


def test_after_sales_schema_accepts_nullable_fields() -> None:
    result = AfterSalesResult(
        order_id=None,
        request_type="其他",
        expected_solution=None,
    )
    assert result.model_dump() == {
        "order_id": None,
        "request_type": "其他",
        "expected_solution": None,
    }


def test_after_sales_request_rejects_blank_description() -> None:
    with pytest.raises(ValidationError):
        AfterSalesRequest(description="  ")
