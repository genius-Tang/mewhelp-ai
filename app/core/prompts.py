from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


CUSTOMER_SERVICE_SYSTEM_PROMPT = """你是电商平台的智能客服。
请使用用户当前使用的语言，保持简洁、礼貌、明确。
信息不足时先追问，不得编造订单状态、物流进度、退款结果或平台政策。
你当前没有工具和业务系统访问能力，不得声称已经查询数据库或完成退款、退货、换货、补发、维修等操作。
对于超出电商客服范围的问题，简短说明能力边界并引导用户描述电商相关诉求。"""

AFTER_SALES_EXTRACTION_SYSTEM_PROMPT = """你负责从用户的售后描述中提取结构化信息。
只能使用原文明确出现的信息，不得猜测订单号或期望方案。
诉求类型只能选择：退货、退款、换货、补发、维修、物流查询、其他。
原文没有订单号或期望方案时，对应字段返回 null。"""

CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", CUSTOMER_SERVICE_SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
    ]
)

EXTRACTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", AFTER_SALES_EXTRACTION_SYSTEM_PROMPT),
        ("human", "{description}"),
    ]
)


def build_chat_prompt_messages(history: list[BaseMessage]) -> list[BaseMessage]:
    return CHAT_PROMPT.invoke({"history": history}).to_messages()


def build_extraction_prompt_messages(description: str) -> list[BaseMessage]:
    return EXTRACTION_PROMPT.invoke({"description": description}).to_messages()
