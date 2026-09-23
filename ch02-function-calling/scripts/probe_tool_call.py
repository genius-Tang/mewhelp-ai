import asyncio
import json

from langchain.tools import tool

from app.core.config import get_settings
from app.core.model import create_chat_model


@tool
def probe_order(order_id: str) -> str:
    """Look up one order by its exact order ID."""
    return order_id


async def main() -> None:
    model = create_chat_model(get_settings())
    reply = await model.bind_tools(
        [probe_order], tool_choice="auto", parallel_tool_calls=False
    ).ainvoke("必须调用 probe_order 查询订单 1001，不要直接回答。")
    calls = reply.tool_calls
    if len(calls) != 1 or calls[0]["name"] != "probe_order":
        raise SystemExit("upstream did not return exactly one probe_order tool call")
    print(json.dumps({"name": calls[0]["name"], "args": calls[0]["args"]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
