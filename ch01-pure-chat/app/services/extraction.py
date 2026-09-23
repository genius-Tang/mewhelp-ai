from typing import Any

from app.core.config import StructuredOutputMethod
from app.core.prompts import build_extraction_prompt_messages
from app.schemas.after_sales import AfterSalesResult


async def extract_after_sales(
    description: str,
    model: Any,
    method: StructuredOutputMethod,
) -> AfterSalesResult:
    structured_model = model.with_structured_output(
        AfterSalesResult,
        method=method,
    )
    result = await structured_model.ainvoke(
        build_extraction_prompt_messages(description)
    )
    if isinstance(result, AfterSalesResult):
        return result
    return AfterSalesResult.model_validate(result)
