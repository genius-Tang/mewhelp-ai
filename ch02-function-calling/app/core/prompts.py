from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


TOOL_SELECTOR_SYSTEM_PROMPT = """你是电商客服的工具选择器。根据用户原话最多选择一个必要工具。
无需工具时不要编造工具调用；FAQ 关键词必须尽量保留用户原词，不得把“邮费”改写成“运费”。
不要在本阶段输出给用户的最终答复。"""

FINAL_ANSWER_SYSTEM_PROMPT = """你是电商平台智能客服。使用用户当前语言简洁、礼貌回答。
如果提供了工具结果，只能依据该结果回答；工具失败或未找到时如实说明，不得编造数据。
不得再请求或声称调用任何工具。"""

AFTER_SALES_EXTRACTION_SYSTEM_PROMPT = """你负责从用户的售后描述中提取结构化信息。
只能使用原文明确出现的信息，不得猜测订单号或期望方案。
诉求类型只能选择：退货、退款、换货、补发、维修、物流查询、其他。
原文没有订单号或期望方案时，对应字段返回 null。
仅输出一个 JSON 对象，不要输出 Markdown 或解释文字。JSON 固定包含 order_id、request_type、expected_solution 三个字段。
示例：{{"order_id":"A123","request_type":"退款","expected_solution":"退款"}}。
用户明确要求查询物流位置或进度时，expected_solution 填写“查询物流进度”；例如：{{"order_id":"ZX-900","request_type":"物流查询","expected_solution":"查询物流进度"}}。"""

TOOL_SELECTOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", TOOL_SELECTOR_SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
    ]
)

FINAL_ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", FINAL_ANSWER_SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
    ]
)

EXTRACTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", AFTER_SALES_EXTRACTION_SYSTEM_PROMPT),
        ("human", "{description}"),
    ]
)


def build_tool_selector_prompt_messages(
    history: list[BaseMessage],
) -> list[BaseMessage]:
    return TOOL_SELECTOR_PROMPT.invoke({"history": history}).to_messages()


def build_final_answer_prompt_messages(history: list[BaseMessage]) -> list[BaseMessage]:
    return FINAL_ANSWER_PROMPT.invoke({"history": history}).to_messages()


def build_chat_prompt_messages(history: list[BaseMessage]) -> list[BaseMessage]:
    """Compatibility alias for chapter-one callers until the API is rewired."""

    return build_final_answer_prompt_messages(history)


def build_extraction_prompt_messages(description: str) -> list[BaseMessage]:
    return EXTRACTION_PROMPT.invoke({"description": description}).to_messages()
