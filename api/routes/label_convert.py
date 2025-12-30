"""
Label Convert API Routes
API endpoints for converting shipping labels
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional

from services.label_converter import convert_shipping_label

router = APIRouter()


class OrderItem(BaseModel):
    """Order item model"""
    order_id: int
    quantity: int = 1
    variant_id: Optional[int] = None
    style: str = "Unknown"


class LabelConvertRequest(BaseModel):
    """Request model for label conversion"""
    id: int = Field(..., description="Order ID")
    shipping_label: str = Field(..., description="URL to original shipping label PDF")
    order_stt: str = Field(..., description="Order sequence number")
    items: List[OrderItem] = Field(default=[], description="List of order items")


class LabelConvertResponse(BaseModel):
    """Response model for label conversion"""
    id: int = Field(..., description="Order ID")
    link: str = Field(..., description="URL/path to converted label")
    status: str = Field(..., description="Conversion status: success, failed, or error")
    tracking_id: str = Field(..., description="Tracking number extracted from label")
    fedex: int = Field(..., description="Carrier type: 0=USPS, 1=FedEx, 2=UPS")
    error: Optional[str] = Field(None, description="Error message if conversion failed")


@router.post("/label/convert", response_model=LabelConvertResponse)
async def convert_label(request: LabelConvertRequest):
    """
    Convert a shipping label by adding order info overlay
    
    This endpoint:
    1. Downloads the original label PDF from the provided URL
    2. Adds order ID and style x quantity info to the bottom-left corner
    3. Extracts the tracking number from the label
    4. Detects the carrier type (USPS, FedEx, or UPS)
    5. Saves the converted label locally (B2 upload coming soon)
    
    Returns the conversion result with tracking info and carrier type.
    """
    # Convert items to dict format
    items_data = [
        {
            "order_id": item.order_id,
            "quantity": item.quantity,
            "variant_id": item.variant_id,
            "style": item.style
        }
        for item in request.items
    ]
    
    result = await convert_shipping_label(
        order_id=request.id,
        shipping_label_url=request.shipping_label,
        order_stt=request.order_stt,
        items=items_data
    )
    
    return result


@router.get("/label/health")
async def label_health_check():
    """Health check for label conversion service"""
    return {
        "status": "healthy",
        "service": "label-converter"
    }
