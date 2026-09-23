import hashlib
import random
from typing import Annotated, Any, Literal

from langchain_core.tools import BaseTool, InjectedToolArg, tool
from pydantic import BaseModel, ConfigDict, Field

from app.db.repository import Repository


class _StrippedInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class OrderInput(_StrippedInput):
    order_id: str = Field(
        min_length=1,
        max_length=64,
        description="用户提供的原始订单号",
    )


class ProductInput(_StrippedInput):
    product_name: str = Field(
        min_length=1,
        max_length=200,
        description="用户询问的商品名称",
    )


class LogisticsInput(_StrippedInput):
    order_id: str = Field(
        min_length=1,
        max_length=64,
        description="需要查询物流轨迹的原始订单号",
    )


class FaqInput(_StrippedInput):
    keyword: str = Field(
        min_length=1,
        max_length=200,
        description="保留用户原词的 FAQ 关键词，不改写同义词",
    )


def _seeded_random(namespace: str, value: str) -> random.Random:
    digest = hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest, "big"))


@tool(args_schema=OrderInput)
async def query_order(order_id: str) -> dict[str, Any]:
    """按订单号查询订单状态、金额和商品件数；仅在用户询问订单时使用。"""
    rng = _seeded_random("order", order_id)
    return {
        "order_id": order_id,
        "status": rng.choice(["待付款", "处理中", "已发货", "已完成"]),
        "amount": round(rng.uniform(39.0, 999.0), 2),
        "item_count": rng.randint(1, 4),
    }


@tool(args_schema=ProductInput)
async def query_product(product_name: str) -> dict[str, Any]:
    """按商品名称查询当前演示价格和库存；仅在用户询问商品时使用。"""
    rng = _seeded_random("product", product_name)
    stock = rng.randint(0, 500)
    return {
        "product_name": product_name,
        "price": round(rng.uniform(19.0, 899.0), 2),
        "stock": stock,
        "available": stock > 0,
    }


@tool(args_schema=LogisticsInput)
async def query_logistics(order_id: str) -> dict[str, Any]:
    """按订单号查询承运商、运单状态和物流轨迹；仅在用户询问配送进度时使用。"""
    rng = _seeded_random("logistics", order_id)
    return {
        "order_id": order_id,
        "carrier": rng.choice(["顺丰速运", "中通快递", "圆通速递"]),
        "tracking_no": f"MOCK{rng.randint(1_000_000_000, 9_999_999_999)}",
        "status": rng.choice(["已揽收", "运输中", "派送中", "已签收"]),
        "timeline": [
            rng.choice(["包裹已揽收", "包裹已离开分拨中心", "快递员正在派送"]),
            rng.choice(["预计今日送达", "预计明日送达", "等待更新"]),
        ],
    }


def build_business_tools(repository: Repository) -> list[BaseTool]:
    @tool(args_schema=FaqInput)
    async def query_faq(keyword: str) -> dict[str, Any]:
        """按用户原词查询常见问题；不要把同义词改写后再查询。"""
        faq = await repository.find_faq(keyword)
        if faq is None:
            return {"found": False, "keyword": keyword}
        return {
            "found": True,
            "question": faq.question,
            "answer": faq.answer,
            "category": faq.category,
        }

    @tool
    async def create_ticket(
        description: Annotated[
            str,
            Field(
                min_length=1,
                max_length=2000,
                description="需要人工客服跟进的问题描述",
            ),
        ],
        ticket_type: Annotated[
            Literal["售后", "投诉", "咨询"],
            Field(description="工单类型，只能是售后、投诉或咨询"),
        ],
        conversation_id: Annotated[int, InjectedToolArg],
    ) -> dict[str, Any]:
        """仅在用户明确要求人工客服继续跟进时创建工单。"""
        ticket = await repository.create_ticket(
            conversation_id,
            description,
            ticket_type,
        )
        return {"ticket_no": ticket.ticket_no, "status": "待处理"}

    return [
        query_order,
        query_product,
        query_logistics,
        query_faq,
        create_ticket,
    ]
