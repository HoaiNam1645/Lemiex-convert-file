"""
QR Code Generation Route
API endpoint to generate QR codes with order information
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from services.qr_generator import create_qr_and_upload


router = APIRouter()


class QRGenerateResponse(BaseModel):
    """Response model for QR generation"""
    url: str


@router.get("/qr/generate", response_model=QRGenerateResponse)
async def generate_qr(
    order_item_id: int = Query(..., description="ID của order item"),
    order_id: int = Query(..., description="ID của order"),
    stt: int = Query(..., description="Số thứ tự (1, 2, 3...)"),
    total: int = Query(..., description="Tổng số lượng trong order"),
    style: str = Query(..., description="Style sản phẩm"),
    color: str = Query(..., description="Màu sản phẩm"),
    size: str = Query(..., description="Size sản phẩm"),
    pageqr: str = Query(..., description="URL để encode trong QR"),
    dst_url: Optional[str] = Query("", description="Filename pattern cho output"),
):
    """
    Generate a QR code with order information
    
    The output image contains:
    - Left side: Order info (order_id, total, stt, style, size, color)
    - Right side: QR code containing pageqr URL
    
    Returns: URL of the uploaded image on B2
    """
    try:
        data = {
            "order_item_id": order_item_id,
            "order_id": order_id,
            "stt": stt,
            "total": total,
            "style": style,
            "color": color,
            "size": size,
            "pageqr": pageqr,
            "dst_url": dst_url,
        }
        
        result = await create_qr_and_upload(data)
        
        return QRGenerateResponse(url=result["url"])
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate QR: {str(e)}")
