
from typing import List
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from services.image_merge import merge_and_upload_images_batch

router = APIRouter()

class MergeImageRequest(BaseModel):
    url_image: str
    url_qr: List[str]

class MergeImageResponse(BaseModel):
    urls: List[str]

@router.post("/merge-image", response_model=MergeImageResponse)
async def merge_image(request: MergeImageRequest):
    """
    Merge main image with multiple QR codes.
    Returns a list of URLs for the merged images.
    """
    try:
        if not request.url_image or not request.url_qr:
            raise HTTPException(status_code=400, detail="url_image and url_qr list are required")
            
        result = await merge_and_upload_images_batch(request.url_image, request.url_qr)
        return MergeImageResponse(urls=result["urls"])
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to merge images: {str(e)}")
