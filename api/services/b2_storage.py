"""Backblaze B2 Storage Service"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import boto3
from botocore.config import Config

from config import (
    B2_ACCESS_KEY_ID,
    B2_SECRET_ACCESS_KEY,
    B2_DEFAULT_REGION,
    B2_BUCKET,
    B2_ENDPOINT,
    B2_JSON_OUTPUT_PATH,
    B2_DST_OUTPUT_PATH,
    B2_INFO_IMAGE_PATH,
)


def get_b2_client():
    """Create B2 S3-compatible client"""
    return boto3.client(
        "s3",
        endpoint_url=B2_ENDPOINT,
        aws_access_key_id=B2_ACCESS_KEY_ID,
        aws_secret_access_key=B2_SECRET_ACCESS_KEY,
        region_name=B2_DEFAULT_REGION,
        config=Config(signature_version="s3v4"),
    )


def upload_json_to_b2(data: dict, filename: str) -> str:
    """
    Upload JSON data to B2
    
    Args:
        data: JSON data to upload
        filename: Output filename (without path)
    
    Returns:
        Full URL to uploaded file
    """
    client = get_b2_client()
    
    # Ensure filename ends with .json
    if not filename.endswith(".json"):
        filename = filename.rsplit(".", 1)[0] + ".json"
    
    # Build key path
    key = f"{B2_JSON_OUTPUT_PATH}/{filename}"
    
    # Convert to JSON string
    json_content = json.dumps(data, indent=2, ensure_ascii=False)
    
    # Upload to B2
    client.put_object(
        Bucket=B2_BUCKET,
        Key=key,
        Body=json_content.encode("utf-8"),
        ContentType="application/json",
    )
    
    # Return full URL
    return f"{B2_ENDPOINT}/{B2_BUCKET}/{key}"


def extract_filename_from_url(url: str) -> str:
    """Extract filename from URL"""
    return url.split("/")[-1]


def upload_dst_to_b2(file_path: str, filename: str) -> str:
    """
    Upload DST file to B2
    
    Args:
        file_path: Local path to DST file
        filename: Output filename (without path)
    
    Returns:
        Full URL to uploaded file
    """
    client = get_b2_client()
    
    # Ensure filename ends with .dst
    if not filename.endswith(".dst"):
        filename = filename.rsplit(".", 1)[0] + ".dst"
    
    # Build key path
    key = f"{B2_DST_OUTPUT_PATH}/{filename}"
    
    # Read file content
    with open(file_path, "rb") as f:
        content = f.read()
    
    # Upload to B2
    client.put_object(
        Bucket=B2_BUCKET,
        Key=key,
        Body=content,
        ContentType="application/octet-stream",
    )
    
    # Return full URL
    return f"{B2_ENDPOINT}/{B2_BUCKET}/{key}"


def upload_image_to_b2(file_path: str, filename: str) -> str:
    """
    Upload PNG image to B2
    
    Args:
        file_path: Local path to PNG file
        filename: Output filename (without path)
    
    Returns:
        Full URL to uploaded file
    """
    client = get_b2_client()
    
    # Ensure filename ends with .png
    if not filename.endswith(".png"):
        filename = filename.rsplit(".", 1)[0] + ".png"
    
    # Build key path
    key = f"{B2_INFO_IMAGE_PATH}/{filename}"
    
    # Read file content
    with open(file_path, "rb") as f:
        content = f.read()
    
    # Upload to B2
    client.put_object(
        Bucket=B2_BUCKET,
        Key=key,
        Body=content,
        ContentType="image/png",
    )
    
    # Return full URL
    return f"{B2_ENDPOINT}/{B2_BUCKET}/{key}"


def delete_from_b2(url: str) -> bool:
    """
    Delete file from B2 by URL
    
    Args:
        url: Full URL to file on B2
    
    Returns:
        True if deleted successfully
    """
    try:
        client = get_b2_client()
        
        # Extract key from URL
        # URL format: https://s3.../Bucket/path/to/file
        prefix = f"{B2_ENDPOINT}/{B2_BUCKET}/"
        if url.startswith(prefix):
            key = url[len(prefix):]
        else:
            # Try to extract from any URL format
            parts = url.split(f"{B2_BUCKET}/")
            if len(parts) > 1:
                key = parts[1]
            else:
                return False
        
        client.delete_object(Bucket=B2_BUCKET, Key=key)
        return True
    except Exception:
        return False


def delete_multiple_from_b2(urls: list) -> None:
    """
    Delete multiple files from B2
    
    Args:
        urls: List of URLs to delete
    """
    for url in urls:
        if url:
            delete_from_b2(url)
