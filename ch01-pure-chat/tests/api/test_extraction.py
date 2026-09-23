from fastapi.testclient import TestClient

from app.api.dependencies import get_chat_model
from app.core.config import Settings, get_settings
from app.main import create_app
from app.schemas.after_sales import AfterSalesResult


class FakeRunnable:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error

    async def ainvoke(self, messages):
        if self.error:
            raise self.error
        return self.result


class FakeModel:
    def __init__(self, runnable: FakeRunnable) -> None:
        self.runnable = runnable

    def with_structured_output(self, schema, *, method):
        return self.runnable


def settings() -> Settings:
    return Settings(
        chat_base_url="https://example.test/v1",
        chat_api_key="secret",
        chat_model="example-model",
        _env_file=None,
    )


def make_client(model: FakeModel) -> TestClient:
    application = create_app(settings_loader=settings)
    application.dependency_overrides[get_settings] = settings
    application.dependency_overrides[get_chat_model] = lambda: model
    return TestClient(application)


def test_extract_after_sales_returns_fixed_json() -> None:
    result = AfterSalesResult(
        order_id="A12345",
        request_type="退货",
        expected_solution="退货退款",
    )
    with make_client(FakeModel(FakeRunnable(result=result))) as client:
        response = client.post(
            "/extract/after-sales",
            json={"description": "订单 A12345 的耳机有杂音，我想退货退款"},
        )
    assert response.status_code == 200
    assert response.json() == result.model_dump()


def test_extract_after_sales_sanitizes_upstream_failure() -> None:
    with make_client(
        FakeModel(FakeRunnable(error=RuntimeError("secret upstream body")))
    ) as client:
        response = client.post(
            "/extract/after-sales",
            json={"description": "想换货"},
        )
    assert response.status_code == 502
    assert response.json() == {"detail": "模型服务暂时不可用"}
    assert "secret upstream body" not in response.text


def test_extract_after_sales_sanitizes_invalid_model_mapping() -> None:
    invalid_result = {
        "order_id": "A12345",
        "request_type": "不存在的诉求",
        "expected_solution": None,
    }
    with make_client(FakeModel(FakeRunnable(result=invalid_result))) as client:
        response = client.post(
            "/extract/after-sales",
            json={"description": "订单 A12345 有问题"},
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "模型服务暂时不可用"}
    assert "不存在的诉求" not in response.text
