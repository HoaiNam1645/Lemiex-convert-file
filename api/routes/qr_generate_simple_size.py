"""
QR Code Generation Route - Simple Layout WITH SIZE (Batch)

Same as /qr/generate-simple, but the title also renders the size next to the
two ids, e.g. "24 - 28 - L". Cloned into a separate endpoint so the original
endpoint is left untouched for projects that don't want the size shown.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import asyncio

from services.qr_generator_simple_size import create_qr_and_upload


router = APIRouter()


class QRItem(BaseModel):
    item_id: int = Field(..., description="ID của order item")
    stt: int = Field(..., description="Số thứ tự unit trong đơn")
    pageqr: str = Field(..., description="URL được encode vào QR")
    # Optional metadata; `size` is now also drawn on the QR title.
    style: Optional[str] = ""
    color: Optional[str] = ""
    size: Optional[str] = ""
    total: Optional[int] = 1


class QRBatchRequest(BaseModel):
    order_id: int
    items: List[QRItem]


class QRBatchResponse(BaseModel):
    urls: List[str]


@router.post("/qr/generate-simple-size", response_model=QRBatchResponse)
async def generate_qr_simple_size_batch(payload: QRBatchRequest):
    """
    Batch generate simplified QR codes with the size shown in the title
    ("{order_id} - {order_item_id} - {size}", e.g. "24 - 28 - L").

    Each item in `items` produces 1 QR image, returned in the same order.
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="items must not be empty")

    async def gen(item: QRItem) -> str:
        data = {
            "order_item_id": item.item_id,
            "order_id": payload.order_id,
            "stt": item.stt,
            "total": item.total or 1,
            "style": item.style or "",
            "color": item.color or "",
            "size": item.size or "",
            "pageqr": item.pageqr,
        }
        try:
            result = await create_qr_and_upload(data)
            return result["url"]
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"QR (size) generate failed for item {item.item_id} stt {item.stt}: {e}")
            return ""

    urls = await asyncio.gather(*(gen(it) for it in payload.items))
    return QRBatchResponse(urls=list(urls))
