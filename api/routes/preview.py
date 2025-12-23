"""Generate preview endpoint"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import Response

from services.file_handler import handle_file_or_url, cleanup_temp_file
from services.pes_converter import generate_pes_preview

router = APIRouter()


@router.post("/preview")
async def generate_preview(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    max_size: int = Form(800),
    linewidth: int = Form(2),
):
    """
    Generate PNG preview of PES file - supports both file upload and URL
    
    Two ways to use:
    1. Upload file: Send multipart/form-data with 'file' field
    2. Provide URL: Send multipart/form-data with 'url' field
    
    Parameters:
    - file: PES file upload (optional)
    - url: URL to PES file (optional)
    - max_size: max dimension in pixels (default 800)
    - linewidth: line thickness (default 2)
    
    Returns PNG image
    """
    tmp_path = None
    
    try:
        # Handle file or URL
        tmp_path, filename, filepath = await handle_file_or_url(
            file, url, required_extension=".pes"
        )
        
        # Generate preview
        png_data = generate_pes_preview(tmp_path, max_size, linewidth)
        
        return Response(content=png_data, media_type="image/png")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating preview: {str(e)}"
        )
    finally:
        cleanup_temp_file(tmp_path)
