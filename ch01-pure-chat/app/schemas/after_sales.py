from typing import Literal

from pydantic import BaseModel, Field, field_validator


RequestType = Literal["退货", "退款", "换货", "补发", "维修", "物流查询", "其他"]


class AfterSalesRequest(BaseModel):
    description: str = Field(min_length=1)

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("description must not be blank")
        return value


class AfterSalesResult(BaseModel):
    order_id: str | None = Field(description="订单号；原文未提供时为 null")
    request_type: RequestType = Field(description="用户的售后诉求类型")
    expected_solution: str | None = Field(
        description="用户明确期望的解决方案；原文未提供时为 null"
    )
