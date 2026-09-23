from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_chat_model
from app.core.config import Settings, get_settings
from app.schemas.after_sales import AfterSalesRequest, AfterSalesResult
from app.services.extraction import extract_after_sales


router = APIRouter(tags=["extraction"])


@router.post("/extract/after-sales", response_model=AfterSalesResult)
async def extract_after_sales_route(
    request: AfterSalesRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    model: Annotated[Any, Depends(get_chat_model)],
) -> AfterSalesResult:
    try:
        return await extract_after_sales(
            request.description,
            model,
            settings.chat_structured_output_method,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="模型服务暂时不可用") from exc
