"""
Progress API Route
Returns JSON progress data for PES files scanning and order status
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from config import (
    DROPBOX_ACCESS_TOKEN,
    DROPBOX_ACCESS_KEY,
    DROPBOX_PATH,
    EMBROIDERY_ROOT,
)
from services.progress_scanner import (
    PesScanner,
    DropboxPesScanner,
    DropboxTokenProvider,
    LemiexClient,
    ProgressCollector,
    ScannerProtocol,
)

from datetime import datetime
from services.background_store import get_store

router = APIRouter()


class ProgressResponse(BaseModel):
    """Response model for progress endpoint"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


@router.get("/progress", response_model=ProgressResponse)
async def get_progress():
    """
    Get embroidery production progress (Cached/Real-time)
    
    Returns cached progress data updated by background worker.
    Scan limit: 10 days most recent.
    """
    try:
        store = get_store()
        data = store.get_data()
        
        return ProgressResponse(
            success=True,
            data=data,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve progress data: {str(e)}"
        )


@router.post("/progress/refresh", response_model=ProgressResponse)
async def refresh_progress():
    """
    Force refresh embroidery progress data
    
    Triggers an immediate background scan and returns the result.
    This may take some time (5-10s).
    """
    try:
        store = get_store()
        await store.update_now()
        data = store.get_data()
        
        return ProgressResponse(
            success=True,
            data=data,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh progress: {str(e)}"
        )



