"""
Label Converter Service
Handles downloading, modifying and processing shipping labels
Converts PDF labels to JPG with text overlay
"""

import os
import re
import random
import shutil
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from io import BytesIO

import pdfplumber
from PIL import Image, ImageDraw, ImageFont, ImageOps
import pypdfium2 as pdfium
from config import DOWNLOAD_TIMEOUT, BE_API_URL
from services.b2_storage import upload_label_to_b2

# Directory for storing converted labels locally (still kept for backup/debug if needed)
LOCAL_LABELS_DIR = Path(__file__).parent.parent.parent / "converted_labels"
LOCAL_LABELS_DIR.mkdir(exist_ok=True)



async def send_update_label_callback(data: Dict[str, Any]) -> None:
    """
    Call backend API to update label info
    """
    url = f"{BE_API_URL}/api/update-label"
    try:
        print(f"Callback[{data['id']}]: Sending update to {url}...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=data)
            
            if response.status_code >= 200 and response.status_code < 300:
                print(f"Callback[{data['id']}]: SUCCESS - Status {response.status_code}")
            else:
                print(f"Callback[{data['id']}]: FAILED - Status {response.status_code} - Body: {response.text}")
                
    except Exception as e:
        print(f"Callback[{data['id']}]: ERROR - {str(e)}")


def detect_carrier(pdf_text: str) -> int:
    """
    Detect carrier type from PDF text content
    Returns: 0=USPS, 1=FedEx, 2=UPS
    """
    text_upper = pdf_text.upper()
    
    if "FEDEX" in text_upper or "FED EX" in text_upper:
        return 1
    elif "UPS" in text_upper and "USPS" not in text_upper:
        return 2
    else:
        # Default to USPS
        return 0


def extract_tracking_number(pdf_text: str, carrier: int) -> Optional[str]:
    """
    Extract tracking number from PDF text based on carrier type
    
    USPS: commonly 20-34 digits or 13 characters ending in US
    FedEx: 12-15 digits
    UPS: 1Z followed by 16 alphanumeric characters
    """
    # Strategy: Find potential tracking number sequences first (digits with optional spaces)
    # Then clean them up and validate
    
    # Extract all sequences of digits (allowing spaces/dashes between them)
    # This captures "9200 1903..." as one group
    # 1. UPS: 1Z...
    ups_matches = re.findall(r'1Z\s*[A-Z0-9\s]{16,25}', pdf_text.upper())
    for m in ups_matches:
        clean = re.sub(r'[\s-]+', '', m)
        if len(clean) >= 18 and clean.startswith('1Z'):
            return clean
            
    # 2. Extract digit-only sequences that might be tracking numbers
    # Look for sequences of at least 12 digits, allowing spaces/dashes
    digit_sequences = re.findall(r'(?:\d[\s-]*){12,35}', pdf_text)
    
    cleaned_candidates = []
    for seq in digit_sequences:
        clean = re.sub(r'[\s-]+', '', seq)
        if len(clean) >= 12:
            cleaned_candidates.append(clean)
            
    # Sort by length (descending) to prefer longer matches (like USPS 92...)
    cleaned_candidates.sort(key=len, reverse=True)
    
    for candidate in cleaned_candidates:
        # USPS: 20-34 digits (often starts with 9, 4, 0)
        if carrier == 0 or carrier == -1: # Default or Unknown
            if len(candidate) >= 20 and len(candidate) <= 34:
                if candidate.startswith(('9', '4', '0')):
                    return candidate
        
        # FedEx: 12, 14, 15, 20 digits (often starts with 96, 78, etc but vary)
        if carrier == 1:
            if len(candidate) in [12, 14, 15, 20]:
                return candidate
                
    # Fallback: if we found a very likely USPS tracking (starts with 92/93/94/95 and length 22-26), returns it even if carrier detected as something else
    for candidate in cleaned_candidates:
        if len(candidate) >= 22 and len(candidate) <= 26 and candidate.startswith(('92', '93', '94', '95')):
            return candidate

    return None


def extract_tracking_number_from_image(image: Image.Image, carrier: int) -> Optional[str]:
    """
    OCR the bottom tracking area to recover tracking numbers missing in the PDF text layer.
    """
    try:
        import pytesseract

        width, height = image.size
        tracking_region = image.crop((0, int(height * 0.62), width, height))

        grayscale = ImageOps.grayscale(tracking_region)
        # Increase contrast for barcode text and normalize to black/white.
        high_contrast = ImageOps.autocontrast(grayscale)
        binary = high_contrast.point(lambda px: 255 if px > 180 else 0, mode="1")
        enlarged = binary.resize((binary.width * 2, binary.height * 2))

        if not shutil.which('tesseract'):
            if os.path.exists('/usr/bin/tesseract'):
                pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
            elif os.path.exists('/usr/local/bin/tesseract'):
                pytesseract.pytesseract.tesseract_cmd = '/usr/local/bin/tesseract'

        ocr_text = pytesseract.image_to_string(
            enlarged,
            config='--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        )
        print(f"Tracking OCR extracted text:\n{ocr_text}")
        return extract_tracking_number(ocr_text, carrier)
    except Exception as e:
        print(f"Error extracting tracking from image OCR: {e}")
        return None


def convert_google_drive_url(url: str) -> str:
    """
    Convert Google Drive share URL to direct download URL
    
    Supported formats:
    - https://drive.google.com/file/d/{FILE_ID}/view
    - https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing
    - https://drive.google.com/open?id={FILE_ID}
    - https://drive.google.com/uc?id={FILE_ID}
    
    Returns direct download URL or original URL if not a Google Drive link
    """
    # Pattern for /file/d/{FILE_ID}/view format
    file_d_pattern = r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)'
    match = re.search(file_d_pattern, url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    
    # Pattern for open?id={FILE_ID} format
    open_id_pattern = r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)'
    match = re.search(open_id_pattern, url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    
    # Pattern for uc?id={FILE_ID} format (already direct download)
    uc_pattern = r'drive\.google\.com/uc\?.*id=([a-zA-Z0-9_-]+)'
    match = re.search(uc_pattern, url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    
    # Not a Google Drive URL, return as-is
    return url


def is_google_drive_url(url: str) -> bool:
    """Check if URL is a Google Drive URL"""
    return "drive.google.com" in url


async def download_label(url: str) -> bytes:
    """
    Download label PDF from URL
    Supports regular URLs and Google Drive share links
    """
    # Convert Google Drive URL if needed
    download_url = convert_google_drive_url(url)
    is_gdrive = is_google_drive_url(url)
    
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(DOWNLOAD_TIMEOUT, connect=10.0),
        follow_redirects=True
    ) as client:
        response = await client.get(download_url)
        response.raise_for_status()
        content = response.content
        
        # Google Drive may show a confirmation page for large files
        # Check if we got HTML instead of PDF
        if is_gdrive and content[:4] != b'%PDF':
            # Try to extract confirm token and retry
            html_content = content.decode('utf-8', errors='ignore')
            
            # Look for confirm token in the HTML
            confirm_pattern = r'confirm=([a-zA-Z0-9_-]+)'
            match = re.search(confirm_pattern, html_content)
            
            if match:
                confirm_token = match.group(1)
                # Extract file ID from original URL
                file_id_match = re.search(r'id=([a-zA-Z0-9_-]+)', download_url)
                if file_id_match:
                    file_id = file_id_match.group(1)
                    confirm_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
                    response = await client.get(confirm_url)
                    response.raise_for_status()
                    content = response.content
            
            # Alternative: Try with confirm=t parameter
            if content[:4] != b'%PDF':
                file_id_match = re.search(r'id=([a-zA-Z0-9_-]+)', download_url)
                if file_id_match:
                    file_id = file_id_match.group(1)
                    confirm_url = f"https://drive.google.com/uc?export=download&confirm=t&id={file_id}"
                    response = await client.get(confirm_url)
                    response.raise_for_status()
                    content = response.content
        
        # Verify we got a PDF
        if content[:4] != b'%PDF':
            raise ValueError("Downloaded content is not a valid PDF file")
        
        return content


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF using pdfplumber, fallback to OCR if needed"""
    full_text = ""
    
    # First try pdfplumber for text-based PDFs
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"
                # Also try to extract text from tables if present
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row:
                            full_text += " ".join(str(cell) for cell in row if cell) + "\n"
    except Exception as e:
        print(f"Error extracting text with pdfplumber: {e}")
    
    # If pdfplumber didn't get meaningful text (too short), try OCR
    # Sometimes PDFs have hidden text layers or just "Scanned by..."
    if len(full_text.strip()) < 100:
        print(f"PDF text too short ({len(full_text.strip())} chars), trying OCR to ensure quality...")
        try:
            import pytesseract
            
            # Convert PDF to image first
            pdf = pdfium.PdfDocument(pdf_bytes)
            page = pdf[0]
            scale = 300 / 72  # Increased DPI to 300 for clearer text on server
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()
            
            # Convert to RGB if needed
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            
            # Run OCR with config to treat image as single block of text
            custom_config = r'--oem 3 --psm 6'
            
            # Explicitly set tesseract path if needed
            if not shutil.which('tesseract'):
                if os.path.exists('/usr/bin/tesseract'):
                    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
                elif os.path.exists('/usr/local/bin/tesseract'):
                    pytesseract.pytesseract.tesseract_cmd = '/usr/local/bin/tesseract'
            
            ocr_text = pytesseract.image_to_string(pil_image, config=custom_config)
            
            print(f"OCR extracted {len(ocr_text)} chars")
            # If OCR got more text, use it
            if len(ocr_text.strip()) > len(full_text.strip()):
                full_text = ocr_text
                
        except Exception as e:
            print(f"Error with OCR: {e}")
            import traceback
            traceback.print_exc()
    
    return full_text


def pdf_to_image(pdf_bytes: bytes, dpi: int = 150) -> Image.Image:
    """
    Convert first page of PDF to PIL Image using pypdfium2
    """
    pdf = pdfium.PdfDocument(pdf_bytes)
    page = pdf[0]  # Get first page
    
    # Render page to image
    scale = dpi / 72  # 72 is the default DPI for PDF
    bitmap = page.render(scale=scale)
    pil_image = bitmap.to_pil()
    
    # Convert to RGB if necessary (remove alpha channel)
    if pil_image.mode == 'RGBA':
        # Create white background
        background = Image.new('RGB', pil_image.size, (255, 255, 255))
        background.paste(pil_image, mask=pil_image.split()[3])
        pil_image = background
    elif pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    
    return pil_image


def add_text_overlay_to_image(
    image: Image.Image,
    order_id: int,
    order_stt: str,
    items: list
) -> Image.Image:
    """
    Add text overlay to image at bottom-left corner
    """
    # Create a copy to avoid modifying original
    img = image.copy()
    draw = ImageDraw.Draw(img)
    
    # Prepare text lines
    lines = []
    
    # First line: order_stt and order_id
    lines.append(f"{order_stt} {order_id}")
    
    # Aggregate quantities by style
    style_quantities: Dict[str, int] = {}
    for item in items:
        style = item.get("style", "Unknown")
        qty = item.get("quantity", 1)
        if style in style_quantities:
            style_quantities[style] += qty
        else:
            style_quantities[style] = qty
    
    # Add style lines
    for style, qty in style_quantities.items():
        lines.append(f"{style} x {qty}")
    
    # Font settings
    font_size = 14
    line_height = 18
    margin_left = 15
    margin_bottom = 25
    
    # Try to use a TrueType font, fallback to default
    try:
        # Try common system fonts
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSText.ttf",
            "/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        font = None
        for font_path in font_paths:
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, font_size)
                break
        if font is None:
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    # Calculate position (bottom-left)
    img_width, img_height = img.size
    y_position = img_height - margin_bottom - (len(lines) * line_height)
    
    # Draw text with black color
    for line in lines:
        draw.text((margin_left, y_position), line, fill=(0, 0, 0), font=font)
        y_position += line_height
    
    return img


def convert_label_to_jpg(
    pdf_bytes: bytes,
    order_id: int,
    order_stt: str,
    items: list
) -> Tuple[bytes, str, int]:
    """
    Convert PDF label to JPG with text overlay
    
    Returns:
        Tuple of (jpg_bytes, tracking_number, carrier_type)
    """
    # Convert PDF to image
    image = pdf_to_image(pdf_bytes)

    # Extract text for tracking detection
    full_text = extract_text_from_pdf(pdf_bytes)

    # Debug: Print extracted text
    print(f"Extracted text from PDF:\n{full_text[:1000]}...")

    # Detect carrier and extract tracking
    carrier = detect_carrier(full_text)
    tracking_id = extract_tracking_number(full_text, carrier)

    # USPS labels often have incomplete PDF text layers, so OCR the barcode block when needed.
    if carrier == 0 and (not tracking_id or len(tracking_id) < 24):
        ocr_tracking_id = extract_tracking_number_from_image(image, carrier)
        if ocr_tracking_id and len(ocr_tracking_id) > len(tracking_id or ""):
            tracking_id = ocr_tracking_id

    # Debug: Print detection results
    print(f"Detected carrier: {carrier}, tracking_id: {tracking_id}")

    if not tracking_id:
        print("WARNING: Tracking ID not found! Dumping full text for debug:")
        print("-" * 50)
        print(full_text)
        print("-" * 50)
    
    # Add text overlay
    image_with_overlay = add_text_overlay_to_image(image, order_id, order_stt, items)
    
    # Save to bytes as JPEG
    output_buffer = BytesIO()
    image_with_overlay.save(output_buffer, format='JPEG', quality=95)
    output_buffer.seek(0)
    
    return output_buffer.getvalue(), tracking_id, carrier


def save_label_locally(
    jpg_bytes: bytes,
    order_id: int
) -> str:
    """
    Save converted label JPG to local directory with random query
    
    Returns: Local file path with random query parameter
    """
    # Generate random number for query
    random_num = random.randint(100000, 999999)
    
    # Create filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"label_{order_id}_{timestamp}.jpg"
    filepath = LOCAL_LABELS_DIR / filename
    
    with open(filepath, "wb") as f:
        f.write(jpg_bytes)
    
    # Return path with random query for easy identification
    return f"{str(filepath)}?random={random_num}"


async def convert_shipping_label(
    order_id: int,
    shipping_label_url: str,
    order_stt: str,
    items: list
) -> Dict[str, Any]:
    """
    Main function to convert a shipping label
    
    Args:
        order_id: Order ID
        shipping_label_url: URL to original label PDF
        order_stt: Order sequence number
        items: List of order items with style and quantity
        
    Returns:
        Dict with conversion result
    """
    try:
        # Download original label
        original_pdf = await download_label(shipping_label_url)
        
        # Convert to JPG with text overlay
        jpg_bytes, tracking_id, carrier = convert_label_to_jpg(
            original_pdf, order_id, order_stt, items
        )
        
        # Upload to B2
        filename = f"label_{order_id}.jpg"
        b2_url = upload_label_to_b2(jpg_bytes, filename)
        
        # Add random query parameter
        random_num = random.randint(100000, 999999)
        final_link = f"{b2_url}?random={random_num}"
        
        print(f"Uploaded label to B2: {final_link}")
        
        result_data = {
            "id": order_id,
            "link": final_link,
            "status": "success",
            "tracking_id": tracking_id or "UNKNOWN",
            "fedex": carrier,
            "error": None
        }
        
        # Send callback to update backend
        # We use ensure_future or just await it depending on requirement
        # Here we await it but capture error inside the function so it doesn't fail the request
        await send_update_label_callback(result_data)
        
        return result_data
        
    except httpx.HTTPError as e:
        return {
            "id": order_id,
            "link": "",
            "status": "failed",
            "tracking_id": "",
            "fedex": 0,
            "error": f"Failed to download label: {str(e)}"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "id": order_id,
            "link": "",
            "status": "error",
            "tracking_id": "",
            "fedex": 0,
            "error": str(e)
        }
