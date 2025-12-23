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
