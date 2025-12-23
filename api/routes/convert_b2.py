"""Convert PES to JSON and upload to B2 endpoint"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.file_handler import download_from_url, cleanup_temp_file
from services.pes_converter import process_pes_to_json_no_preview
from services.b2_storage import upload_json_to_b2, extract_filename_from_url

router = APIRouter()


class ConvertB2Request(BaseModel):
    url: str


class ConvertB2Response(BaseModel):
    url: str


@router.post("/convert-b2", response_model=ConvertB2Response)
async def convert_pes_to_b2(request: ConvertB2Request):
    """
    Convert PES file from URL to JSON and upload to B2
    
    Input:
    {
        "url": "https://s3.us-east-005.backblazeb2.com/Lemiex-Fulfillment/pes_files/63_61_front.pes"
    }
    
    Output:
    {
        "url": "https://s3.us-east-005.backblazeb2.com/Lemiex-Fulfillment/converted_json/63_61_front.json"
    }
    """
    tmp_path = None
    
    try:
        # Validate URL
        if not request.url.lower().endswith(".pes"):
            raise HTTPException(
                status_code=400,
                detail="URL must point to a .pes file"
            )
        
        # Download PES file
        tmp_path = await download_from_url(request.url)
        
        # Extract filename
        original_filename = extract_filename_from_url(request.url)
        
        # Process PES file - NO PREVIEW for speed
        result = process_pes_to_json_no_preview(tmp_path)
        
        # Update file info
        result["file_info"]["filename"] = original_filename
        result["file_info"]["filepath"] = request.url
        
        # Upload to B2
        json_filename = original_filename.rsplit(".", 1)[0] + ".json"
        json_url = upload_json_to_b2(result, json_filename)
        
        return ConvertB2Response(url=json_url)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing PES file: {str(e)}"
        )
    finally:
        cleanup_temp_file(tmp_path)
