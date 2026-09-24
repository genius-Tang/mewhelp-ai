import pytest
from pydantic import ValidationError

from app.schemas.after_sales import AfterSalesRequest, AfterSalesResult
from app.schemas.chat import ChatRequest


def test_chat_request_strips_public_fields() -> None:
    request = ChatRequest(
        user_id=" browser-user ",
        message=" 订单 A123 ",
        conversation_id=7,
    )

    assert request.model_dump() == {
        "user_id": "browser-user",
        "message": "订单 A123",
        "conversation_id": 7,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": " ", "message": "hello"},
        {"user_id": "u" * 65, "message": "hello"},
        {"user_id": "user", "message": " "},
        {"user_id": "user", "message": "m" * 4001},
        {"user_id": "user", "message": "hello", "conversation_id": -1},
    ],
)
def test_chat_request_rejects_invalid_public_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(payload)


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
