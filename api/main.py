"""
PES Embroidery API Service
FastAPI-based REST API for PES file conversion and preview
"""

import os
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from pes_to_json import process_pes_to_json
from render_pes_trueview import render_pes
from pes_api_utils import process_pes_to_json_fast, process_pes_to_json_no_preview

app = FastAPI(
    title="PES Embroidery API",
    description="API service for converting PES embroidery files to JSON and generating previews",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "pes-embroidery-api"}


@app.post("/api/convert")
async def convert_pes_to_json(
    file: UploadFile = File(...),
    include_preview: bool = True,
    preview_size: int = 400,
):
    """
    Convert PES file to JSON format
    
    - Upload a .pes file
    - include_preview: set false to skip preview generation (faster)
    - preview_size: smaller = faster (default 400px)
    - Returns JSON with file info, colors, needle assignments, and optional base64 preview
    """
    if not file.filename.lower().endswith('.pes'):
        raise HTTPException(status_code=400, detail="File must be a .pes file")
    
    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pes') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # Process PES file with optional preview
            if include_preview:
                result = process_pes_to_json_fast(tmp_path, preview_size=preview_size)
            else:
                result = process_pes_to_json_no_preview(tmp_path)
            
            # Update filename to original
            result["file_info"]["filename"] = file.filename
            result["file_info"]["filepath"] = file.filename
            return JSONResponse(content=result)
        finally:
            # Cleanup temp file
            os.unlink(tmp_path)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PES file: {str(e)}")


@app.post("/api/preview")
async def generate_preview(
    file: UploadFile = File(...),
    max_size: int = 800,
    linewidth: int = 2,
):
    """
    Generate PNG preview of PES file
    
    - Upload a .pes file
    - Returns PNG image
    """
    if not file.filename.lower().endswith('.pes'):
        raise HTTPException(status_code=400, detail="File must be a .pes file")
    
    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pes') as tmp_pes:
            content = await file.read()
            tmp_pes.write(content)
            tmp_pes_path = tmp_pes.name
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_png:
            tmp_png_path = tmp_png.name
        
        try:
            # Render preview
            render_pes(
                pes_path=Path(tmp_pes_path),
                png_path=Path(tmp_png_path),
                background=None,
                linewidth=linewidth,
                margin=0,
                max_size=max_size,
                native_size=True,
                output_base64=False,
            )
            
            # Read and return PNG
            with open(tmp_png_path, 'rb') as f:
                png_data = f.read()
            
            return Response(content=png_data, media_type="image/png")
        finally:
            # Cleanup temp files
            os.unlink(tmp_pes_path)
            if os.path.exists(tmp_png_path):
                os.unlink(tmp_png_path)
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating preview: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
