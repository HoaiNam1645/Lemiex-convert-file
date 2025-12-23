"""Batch convert PES to DST and upload to B2"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pyembroidery import read, write as write_embroidery

from services.file_handler import download_from_url, cleanup_temp_file
from services.b2_storage import (
    upload_dst_to_b2,
    upload_image_to_b2,
    extract_filename_from_url,
    delete_from_b2,
    delete_multiple_from_b2,
)
from render_pes_trueview import render_pes

router = APIRouter()

# Thread pool for CPU-bound tasks
executor = ThreadPoolExecutor(max_workers=4)


class PesFileInput(BaseModel):
    side: str
    item_id: int
    url: str


class BatchConvertRequest(BaseModel):
    urls: List[PesFileInput]
    order_id: int
    include_dst: bool = True


class FileOutput(BaseModel):
    item_id: int
    side: str
    dst_url: Optional[str] = None
    info_image_url: str
    metadata: dict


class BatchConvertResponse(BaseModel):
    files: List[FileOutput]


def process_single_file_sync(
    pes_path: str,
    base_name: str,
    include_dst: bool,
) -> tuple:
    """
    Synchronous processing of a single PES file (for thread pool)
    Returns: (dst_path, png_path, stitch_count)
    """
    # Read pattern
    pattern = read(pes_path)
    if pattern is None:
        raise ValueError(f"Unable to read PES file")
    
    stitch_count = pattern.count_stitches()
    
    dst_path = None
    png_path = None
    
    # Convert to DST
    if include_dst:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dst") as tmp:
            dst_path = tmp.name
        write_embroidery(pattern, dst_path)
    
    # Generate preview image
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        png_path = tmp.name
    
    render_pes(
        pes_path=Path(pes_path),
        png_path=Path(png_path),
        background=None,
        linewidth=1,  # Thinner = faster
        margin=0,
        max_size=400,  # Smaller for speed
        native_size=True,
        output_base64=False,
    )
    
    return dst_path, png_path, stitch_count


async def process_single_pes(
    pes_input: PesFileInput,
    include_dst: bool,
    loop: asyncio.AbstractEventLoop,
) -> tuple:
    """
    Process a single PES file asynchronously
    Returns: (FileOutput, temp_files_to_cleanup, uploaded_urls)
    """
    temp_files = []
    uploaded_urls = []  # Track uploaded URLs for rollback
    
    # Download PES file
    tmp_pes_path = await download_from_url(pes_input.url)
    temp_files.append(tmp_pes_path)
    
    # Extract base filename
    original_filename = extract_filename_from_url(pes_input.url)
    base_name = original_filename.rsplit(".", 1)[0]
    
    # Process in thread pool (CPU-bound)
    dst_path, png_path, stitch_count = await loop.run_in_executor(
        executor,
        process_single_file_sync,
        tmp_pes_path,
        base_name,
        include_dst,
    )
    
    if dst_path:
        temp_files.append(dst_path)
    if png_path:
        temp_files.append(png_path)
    
    # Upload to B2 concurrently
    upload_tasks = []
    
    if include_dst and dst_path:
        upload_tasks.append(
            loop.run_in_executor(
                executor,
                upload_dst_to_b2,
                dst_path,
                f"{base_name}.dst",
            )
        )
    
    upload_tasks.append(
        loop.run_in_executor(
            executor,
            upload_image_to_b2,
            png_path,
            f"{base_name}.png",
        )
    )
    
    # Wait for uploads
    upload_results = await asyncio.gather(*upload_tasks)
    
    if include_dst:
        dst_url = upload_results[0]
        info_image_url = upload_results[1]
        uploaded_urls.extend([dst_url, info_image_url])
    else:
        dst_url = None
        info_image_url = upload_results[0]
        uploaded_urls.append(info_image_url)
    
    result = FileOutput(
        item_id=pes_input.item_id,
        side=pes_input.side,
        dst_url=dst_url,
        info_image_url=info_image_url,
        metadata={"stitch_count": stitch_count}
    )
    
    return result, temp_files, uploaded_urls


@router.post("/convert-pes-to-dst", response_model=BatchConvertResponse)
async def convert_pes_to_dst(request: BatchConvertRequest):
    """
    Batch convert PES files to DST and generate info images (PARALLEL)
    
    If any file fails, all uploaded files will be deleted (rollback).
    """
    all_temp_files = []
    all_uploaded_urls = []  # Track all uploaded URLs for rollback
    
    try:
        # Validate URLs
        for pes_input in request.urls:
            if not pes_input.url.lower().endswith(".pes"):
                raise HTTPException(
                    status_code=400,
                    detail=f"URL must point to a .pes file: {pes_input.url}"
                )
        
        loop = asyncio.get_event_loop()
        
        # Process all files in parallel
        tasks = [
            process_single_pes(pes_input, request.include_dst, loop)
            for pes_input in request.urls
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect results, temp files, and uploaded URLs
        file_outputs = []
        has_error = False
        error_message = None
        
        for result in results:
            if isinstance(result, Exception):
                has_error = True
                error_message = str(result)
            else:
                file_output, temp_files, uploaded_urls = result
                file_outputs.append(file_output)
                all_temp_files.extend(temp_files)
                all_uploaded_urls.extend(uploaded_urls)
        
        # If any error, rollback all uploaded files
        if has_error:
            # Delete all uploaded files
            delete_multiple_from_b2(all_uploaded_urls)
            raise HTTPException(
                status_code=500,
                detail=f"Error processing file: {error_message}. All uploaded files have been rolled back."
            )
        
        return BatchConvertResponse(files=file_outputs)
    
    except HTTPException:
        raise
    except Exception as e:
        # Rollback on unexpected error
        delete_multiple_from_b2(all_uploaded_urls)
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}. All uploaded files have been rolled back."
        )
    finally:
        # Cleanup all temp files
        for tmp_file in all_temp_files:
            cleanup_temp_file(tmp_file)
