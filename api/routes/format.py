"""Convert embroidery format endpoint"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import Response
from pyembroidery import read, write as write_embroidery

from config import SUPPORTED_FORMATS
from services.file_handler import handle_file_or_url, cleanup_temp_file

router = APIRouter()


@router.post("/convert-format")
async def convert_embroidery_format(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    output_format: str = Form(..., description="Output format: dst, pes, jef, exp, vp3, xxx, etc."),
):
    """
    Convert embroidery file to different format
    
    Supports: PES, DST, JEF, EXP, VP3, XXX, PEC, HUS, VIP, and more
    
    Parameters:
    - file: Embroidery file upload (optional)
    - url: URL to embroidery file (optional)
    - output_format: Target format (e.g., 'dst', 'pes', 'jef')
    
    Returns: Converted embroidery file
    
    Example: Convert PES to DST
    """
    # Normalize output format
    output_format = output_format.lower().strip()
    if not output_format.startswith('.'):
        output_format = f'.{output_format}'
    
    # Validate format
    if output_format not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Supported: {', '.join(SUPPORTED_FORMATS)}"
        )
    
    tmp_input_path = None
    tmp_output_path = None
    
    try:
        # Handle file or URL (no extension requirement)
        tmp_input_path, original_filename, filepath = await handle_file_or_url(
            file, url, required_extension=None
        )
        
        # Read embroidery pattern
        pattern = read(tmp_input_path)
        if pattern is None:
            raise ValueError("Unable to read embroidery file")
        
        # Create output file
        with tempfile.NamedTemporaryFile(delete=False, suffix=output_format) as tmp_out:
            tmp_output_path = tmp_out.name
        
        # Convert format
        write_embroidery(pattern, tmp_output_path)
        
        # Read converted file
        with open(tmp_output_path, 'rb') as f:
            output_data = f.read()
        
        # Generate output filename
        base_name = os.path.splitext(original_filename)[0]
        output_filename = f"{base_name}{output_format}"
        
        return Response(
            content=output_data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{output_filename}"'
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error converting file: {str(e)}"
        )
    finally:
        cleanup_temp_file(tmp_input_path)
        cleanup_temp_file(tmp_output_path)
