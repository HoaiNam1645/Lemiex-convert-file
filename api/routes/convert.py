"""Convert PES to JSON endpoint"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse

from services.file_handler import handle_file_or_url, cleanup_temp_file
from services.pes_converter import process_pes_to_json_fast, process_pes_to_json_no_preview

router = APIRouter()


@router.post("/convert")
async def convert_pes_to_json(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    include_preview: bool = Form(True),
    preview_size: int = Form(400),
):
    """
    Convert PES file to JSON format - supports both file upload and URL
    
    Two ways to use:
    1. Upload file: Send multipart/form-data with 'file' field
    2. Provide URL: Send multipart/form-data with 'url' field
    
    Parameters:
    - file: PES file upload (optional)
    - url: URL to PES file (optional, e.g., from B2, S3)
    - include_preview: set false to skip preview generation (faster)
    - preview_size: smaller = faster (default 400px)
    
    Returns JSON with file info, colors, needle assignments, and optional base64 preview
    """
    tmp_path = None
    
    try:
        # Handle file or URL
        tmp_path, filename, filepath = await handle_file_or_url(
            file, url, required_extension=".pes"
        )
        
        # Process PES file
        if include_preview:
            result = process_pes_to_json_fast(tmp_path, preview_size=preview_size)
        else:
            result = process_pes_to_json_no_preview(tmp_path)
        
        # Update file info
        result["file_info"]["filename"] = filename
        result["file_info"]["filepath"] = filepath
        
        return JSONResponse(content=result)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing PES file: {str(e)}"
        )
    finally:
        cleanup_temp_file(tmp_path)
