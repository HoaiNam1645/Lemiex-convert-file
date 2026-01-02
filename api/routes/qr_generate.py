"""
QR Code Generation Route
API endpoint to generate QR codes with order information
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.qr_generator import create_qr_and_upload


router = APIRouter()


class QRGenerateRequest(BaseModel):
    """Request model for QR generation"""
    order_item_id: int
    order_id: int
    stt: int
    total: int
    style: str
    color: str
    size: str
    pageqr: str
    dst_url: Optional[str] = ""


class QRGenerateResponse(BaseModel):
    """Response model for QR generation"""
    url: str


@router.post("/qr/generate", response_model=QRGenerateResponse)
async def generate_qr(request: QRGenerateRequest):
    """
    Generate a QR code with order information
    
    The output image contains:
    - Left side: Order info (order_id, total, stt, style, size, color)
    - Right side: QR code containing pageqr URL
    
    Returns: URL of the uploaded image on B2
    """
    try:
        data = {
            "order_item_id": request.order_item_id,
            "order_id": request.order_id,
            "stt": request.stt,
            "total": request.total,
            "style": request.style,
            "color": request.color,
            "size": request.size,
            "pageqr": request.pageqr,
            "dst_url": request.dst_url,
        }
        
        result = await create_qr_and_upload(data)
        
        return QRGenerateResponse(url=result["url"])
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate QR: {str(e)}")
