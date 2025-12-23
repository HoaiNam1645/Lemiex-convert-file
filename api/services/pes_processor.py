"""PES processing service"""

import os
import sys
import tempfile
import pathlib
from pathlib import Path
from typing import Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from render_pes_trueview import render_pes
from api.services.pes_converter import process_pes_to_json_fast, process_pes_to_json_no_preview


def process_pes_file(
    pes_path: str,
    include_preview: bool = True,
    preview_size: int = 400,
) -> Dict:
    """
    Process PES file to JSON
    
    Args:
        pes_path: Path to PES file
        include_preview: Whether to include preview
        preview_size: Preview size in pixels
    
    Returns:
        Dict with PES data
    """
    if include_preview:
        return process_pes_to_json_fast(pes_path, preview_size=preview_size)
    else:
        return process_pes_to_json_no_preview(pes_path)


def generate_pes_preview(
    pes_path: str,
    max_size: int = 800,
    linewidth: int = 2,
) -> bytes:
    """
    Generate PNG preview of PES file
    
    Args:
        pes_path: Path to PES file
        max_size: Max dimension in pixels
        linewidth: Line thickness
    
    Returns:
        PNG image data as bytes
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_png:
        tmp_png_path = tmp_png.name
    
    try:
        render_pes(
            pes_path=pathlib.Path(pes_path),
            png_path=pathlib.Path(tmp_png_path),
            background=None,
            linewidth=linewidth,
            margin=0,
            max_size=max_size,
            native_size=True,
            output_base64=False,
        )
        
        with open(tmp_png_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_png_path):
            os.unlink(tmp_png_path)
