"""File and URL handling service"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from fastapi import UploadFile, HTTPException

from config import DOWNLOAD_TIMEOUT


async def download_from_url(url: str) -> str:
    """
    Download file from URL to temp file
    
    Args:
        url: URL to download
    
    Returns:
        Path to temp file
    """
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.content
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Failed to download file from URL: {e}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid URL or network error: {e}"
        )
    
    # Get file extension from URL
    filename = url.split("/")[-1]
    file_ext = os.path.splitext(filename)[1]
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        tmp.write(content)
        return tmp.name


async def handle_file_or_url(
    file: Optional[UploadFile],
    url: Optional[str],
    required_extension: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Handle file upload or URL download
    
    Args:
        file: Uploaded file
        url: URL to download
        required_extension: Required file extension (e.g., '.pes')
    
    Returns:
        Tuple of (temp_file_path, filename, filepath)
    
    Raises:
        HTTPException: If validation fails
    """
    # Validate input
    if not file and not url:
        raise HTTPException(
            status_code=400,
            detail="Either 'file' or 'url' must be provided"
        )
    
    if file and url:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'file' or 'url', not both"
        )
    
    tmp_path = None
    filename = None
    filepath = None
    
    # Handle file upload
    if file:
        filename = file.filename
        filepath = file.filename
        
        # Validate extension
        if required_extension and not filename.lower().endswith(required_extension):
            raise HTTPException(
                status_code=400,
                detail=f"File must be a {required_extension} file"
            )
        
        # Save to temp file
        file_ext = os.path.splitext(filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
    
    # Handle URL
    elif url:
        filename = url.split("/")[-1]
        filepath = url
        
        # Validate extension
        if required_extension and not url.lower().endswith(required_extension):
            raise HTTPException(
                status_code=400,
                detail=f"URL must point to a {required_extension} file"
            )
        
        # Download file
        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to download file from URL: {e}",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid URL or network error: {e}"
            )
        
        # Save to temp file
        file_ext = os.path.splitext(filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
    
    return tmp_path, filename, filepath


def cleanup_temp_file(file_path: Optional[str]) -> None:
    """Safely cleanup temporary file"""
    if file_path and os.path.exists(file_path):
        try:
            os.unlink(file_path)
        except OSError:
            pass
