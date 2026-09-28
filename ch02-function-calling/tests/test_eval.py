from scripts import eval_ch02


def test_order_id_from_question_does_not_replace_tool_status() -> None:
    case = {"expected_tool": "query_order", "grounded_fields": ["status"]}
    payload = {"ok": True, "tool": "query_order", "data": {"order_id": "1001", "status": "已发货"}}

    assert not eval_ch02.answer_grounds_tool(case, "订单 1001 已收到", [payload])
    assert eval_ch02.answer_grounds_tool(case, "订单 1001 已发货", [payload])


def test_ticket_answer_must_include_created_ticket_number() -> None:
    case = {"expected_tool": "create_ticket", "grounded_fields": ["ticket_no"]}
    payload = {"ok": True, "tool": "create_ticket", "data": {"ticket_no": "T123456", "status": "待处理"}}

    assert not eval_ch02.answer_grounds_tool(case, "已经为您转人工", [payload])
    assert eval_ch02.answer_grounds_tool(case, "工单 T123456 已创建", [payload])
