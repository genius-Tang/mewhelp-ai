import pytest

from app.schemas.after_sales import AfterSalesResult
from app.services.extraction import extract_after_sales


class FakeStructuredRunnable:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.seen_messages = None

    async def ainvoke(self, messages):
        self.seen_messages = messages
        if self.error:
            raise self.error
        return self.result


class FakeStructuredModel:
    def __init__(self, runnable: FakeStructuredRunnable) -> None:
        self.runnable = runnable
        self.schema = None
        self.method = None

    def with_structured_output(self, schema, *, method):
        self.schema = schema
        self.method = method
        return self.runnable


async def test_extract_after_sales_uses_schema_and_configured_method() -> None:
    expected = AfterSalesResult(
        order_id="A12345",
        request_type="退货",
        expected_solution="退货退款",
    )
    runnable = FakeStructuredRunnable(result=expected)
    model = FakeStructuredModel(runnable)

    result = await extract_after_sales(
        "订单 A12345 的耳机有杂音，我想退货退款",
        model,
        "function_calling",
    )

    assert result == expected
    assert model.schema is AfterSalesResult
    assert model.method == "function_calling"
    assert runnable.seen_messages[-1].content.startswith("订单 A12345")


async def test_extract_after_sales_validates_mapping_response() -> None:
    model = FakeStructuredModel(
        FakeStructuredRunnable(
            result={
                "order_id": "A12345",
                "request_type": "换货",
                "expected_solution": "更换耳机",
            }
        )
    )

    result = await extract_after_sales("耳机损坏，订单 A12345，想换货", model, "json_mode")

    assert result == AfterSalesResult(
        order_id="A12345",
        request_type="换货",
        expected_solution="更换耳机",
    )


async def test_extract_after_sales_propagates_upstream_failure() -> None:
    model = FakeStructuredModel(
        FakeStructuredRunnable(error=RuntimeError("secret upstream body"))
    )
    with pytest.raises(RuntimeError, match="secret upstream body"):
        await extract_after_sales("想换货", model, "json_mode")
