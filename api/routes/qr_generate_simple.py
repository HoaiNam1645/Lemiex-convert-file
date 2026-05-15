"""
QR Code Generation Route - Simple Layout (Batch)
Generates multiple QR codes (Order ID + QR) in a single request.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import asyncio

from services.qr_generator_simple import create_qr_and_upload


router = APIRouter()


class QRItem(BaseModel):
    item_id: int = Field(..., description="ID của order item")
    stt: int = Field(..., description="Số thứ tự unit trong đơn")
    pageqr: str = Field(..., description="URL được encode vào QR")
    # Optional metadata, only used for filename pattern (compat with existing storage)
    style: Optional[str] = ""
    color: Optional[str] = ""
    size: Optional[str] = ""
    total: Optional[int] = 1


class QRBatchRequest(BaseModel):
    order_id: int
    items: List[QRItem]


class QRBatchResponse(BaseModel):
    urls: List[str]


@router.post("/qr/generate-simple", response_model=QRBatchResponse)
async def generate_qr_simple_batch(payload: QRBatchRequest):
    """
    Batch generate simplified QR codes (Order ID + QR).

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
            print(f"QR generate failed for item {item.item_id} stt {item.stt}: {e}")
            return ""

    urls = await asyncio.gather(*(gen(it) for it in payload.items))
    return QRBatchResponse(urls=list(urls))
