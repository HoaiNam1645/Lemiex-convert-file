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

router = APIRouter()


class ProgressResponse(BaseModel):
    """Response model for progress endpoint"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    source: Optional[str] = None


def build_scanner(
    dropbox_token: Optional[str] = None,
    dropbox_key: Optional[str] = None,
    dropbox_path: Optional[str] = None,
    local_root: Optional[str] = None,
) -> tuple[ScannerProtocol, str]:
    """Build scanner based on available credentials"""
    
    # Use environment variables as defaults
    dropbox_token = dropbox_token or DROPBOX_ACCESS_TOKEN
    dropbox_key = dropbox_key or DROPBOX_ACCESS_KEY
    dropbox_path = dropbox_path or DROPBOX_PATH
    local_root = local_root or EMBROIDERY_ROOT
    
    # Try Dropbox first if credentials are provided
    if dropbox_token or dropbox_key:
        token_provider = DropboxTokenProvider(dropbox_token, dropbox_key)
        
        if token_provider.ensure_token():
            scanner = DropboxPesScanner(token_provider, dropbox_path)
            root_display = f"Dropbox{dropbox_path}"
            return scanner, root_display
    
    # Fallback to local scanning
    if local_root:
        root_path = Path(local_root)
    else:
        # Try common default paths
        root_path = Path(r"C:\Users\ADMIN\Dropbox\.Embroidery_Lemiex")
    
    return PesScanner(root_path), str(root_path)


@router.get("/progress", response_model=ProgressResponse)
async def get_progress(
    dropbox_token: Optional[str] = Query(None, description="Dropbox access token (optional, uses env var if not provided)"),
    dropbox_key: Optional[str] = Query(None, description="Dropbox API key (optional, uses env var if not provided)"),
    dropbox_path: Optional[str] = Query(None, description="Dropbox folder path (optional, default from env)"),
    local_root: Optional[str] = Query(None, description="Local root folder path (optional, default from env)"),
):
    """
    Get embroidery production progress
    
    Scans PES files from Local/Dropbox and queries Lemiex API for order status.
    Returns comprehensive progress data in JSON format.
    
    **Priority:**
    1. If dropbox_token or dropbox_key is provided (or set in env) → scan Dropbox
    2. Otherwise → scan local filesystem
    
    **Response includes:**
    - Dates with progress (done/total items, completion %)
    - Stations within each date
    - Orders with status (done/total items, pending items)
    - Overall completion statistics
    - Missing order IDs (not found in API)
    """
    try:
        # Build scanner (will use env vars by default)
        scanner, source = build_scanner(
            dropbox_token=dropbox_token,
            dropbox_key=dropbox_key,
            dropbox_path=dropbox_path,
            local_root=local_root,
        )
        
        # Collect progress data
        client = LemiexClient()
        collector = ProgressCollector(scanner, client)
        snapshot = collector.collect()
        
        # Convert to JSON-serializable dict
        progress_data = snapshot.to_dict()
        
        return ProgressResponse(
            success=True,
            data=progress_data,
            source=source,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to collect progress: {str(e)}"
        )


@router.get("/progress/summary", response_model=ProgressResponse)
async def get_progress_summary(
    dropbox_token: Optional[str] = Query(None, description="Dropbox access token (optional, uses env var if not provided)"),
    dropbox_key: Optional[str] = Query(None, description="Dropbox API key (optional, uses env var if not provided)"),
    dropbox_path: Optional[str] = Query(None, description="Dropbox folder path (optional, default from env)"),
    local_root: Optional[str] = Query(None, description="Local root folder path (optional, default from env)"),
):
    """
    Get embroidery production progress summary (lightweight version)
    
    Returns only high-level statistics without detailed order information.
    """
    try:
        # Build scanner (will use env vars by default)
        scanner, source = build_scanner(
            dropbox_token=dropbox_token,
            dropbox_key=dropbox_key,
            dropbox_path=dropbox_path,
            local_root=local_root,
        )
        
        # Collect progress data
        client = LemiexClient()
        collector = ProgressCollector(scanner, client)
        snapshot = collector.collect()
        
        # Build summary only
        summary_data = {
            "order_count": snapshot.order_count,
            "overall_completion": snapshot.overall_completion,
            "date_count": len(snapshot.dates),
            "missing_ids_count": len(snapshot.missing_ids),
            "dates_summary": [
                {
                    "name": date.name,
                    "completion": date.completion,
                    "done_items": date.done_items,
                    "total_items": date.total_items,
                    "completed_orders": date.completed_orders,
                    "total_orders": date.total_orders,
                }
                for date in snapshot.dates
            ],
        }
        
        return ProgressResponse(
            success=True,
            data=summary_data,
            source=source,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to collect progress summary: {str(e)}"
        )
