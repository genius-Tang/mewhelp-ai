from app.core.prompts import build_extraction_prompt_messages


def test_extraction_prompt_declares_json_contract() -> None:
    messages = build_extraction_prompt_messages("订单 A123 的商品损坏，我想退款")
    system_prompt = messages[0].content

    assert isinstance(system_prompt, str)
    assert "JSON" in system_prompt
    assert '"order_id"' in system_prompt
    assert '"request_type"' in system_prompt
    assert '"expected_solution"' in system_prompt
    assert "查询物流进度" in system_prompt
    assert messages[-1].content == "订单 A123 的商品损坏，我想退款"
