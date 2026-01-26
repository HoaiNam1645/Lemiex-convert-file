"""
QR Code Generator Service
Generates QR codes with order information overlay
"""

import qrcode
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from typing import Dict, Any
import os

from services.b2_storage import upload_qr_to_b2


def generate_qr_image(data: Dict[str, Any]) -> bytes:
    """
    Generate a QR code image with order information on the left side
    
    Args:
        data: Dictionary containing order information
    
    Returns:
        PNG image bytes
    """
    # Extract data
    order_id = data.get('order_id', '')
    stt = data.get('stt', 1)
    total = data.get('total', 1)
    style = data.get('style', '')
    color = data.get('color', '')
    size = data.get('size', '')
    pageqr = data.get('pageqr', '')
    dst_url = data.get('dst_url', '')
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=5,
        border=1,
    )
    qr.add_data(pageqr)
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.convert('RGB')
    qr_width, qr_height = qr_img.size
    
    # Canvas dimensions
    text_width = 180
    gap = 10  # Gap between text and QR
    bottom_padding = 50 # Khoảng trắng ở dưới
    
    canvas_width = text_width + gap + qr_width
    canvas_height = qr_height + bottom_padding
    
    # Create canvas with white background
    canvas = Image.new('RGB', (canvas_width, canvas_height), color=(255, 255, 255))
    
    # Paste QR code on right side
    qr_x = text_width + gap
    qr_y = 0
    canvas.paste(qr_img, (qr_x, qr_y))
    
    # Draw border
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([(0, 0), (canvas_width - 1, canvas_height - 1)], outline=(80, 80, 80), width=1)
    
    # Load BOLD fonts for all text
    font_title = font_text = None
    
    # Prioritize bold font files
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                font_title = ImageFont.truetype(font_path, 22)
                font_text = ImageFont.truetype(font_path, 16)
                break
            except:
                continue
    
    if font_title is None:
        font_title = font_text = ImageFont.load_default()
    
    # Calculate text positions - spread evenly across height
    x = 10
    padding_top = 12
    padding_bottom = 12
    # Use qr_height for text spacing to keep it aligned with QR, ignoring bottom padding
    available_height = qr_height - padding_top - padding_bottom
    
    # 4 lines of text, calculate equal spacing
    num_lines = 4
    line_spacing = available_height // num_lines
    
    # Line 1: Order ID
    y = padding_top
    draw.text((x, y), str(order_id), fill=(0, 0, 0), font=font_title)
    
    # Line 2: Total item
    y = padding_top + line_spacing
    total_text = f"Total item:{total}   {stt}/{total}"
    draw.text((x, y), total_text, fill=(0, 0, 0), font=font_text)
    
    # Line 3: Style - Size (red)
    y = padding_top + line_spacing * 2
    style_size_text = f"{style} - {size}"
    draw.text((x, y), style_size_text, fill=(180, 0, 0), font=font_text)
    
    # Line 4: Color (red)
    y = padding_top + line_spacing * 3
    draw.text((x, y), str(color), fill=(180, 0, 0), font=font_text)
    
    # Convert to bytes
    output = BytesIO()
    canvas.save(output, format='PNG', optimize=True)
    output.seek(0)
    
    return output.getvalue()


async def create_qr_and_upload(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate QR code and upload to B2
    
    Args:
        data: QR data dictionary
        
    Returns:
        Dict with 'url' key containing the B2 URL
    """
    # Generate image
    image_bytes = generate_qr_image(data)
    
    # Create filename: {order_id}_{item_id}_{style}_{size}_{color}_{stt}_{total}_qr.png
    order_id = data.get('order_id', 0)
    order_item_id = data.get('order_item_id', 0)
    style = data.get('style', '')
    size = data.get('size', '')
    color = data.get('color', '')
    stt = data.get('stt', 1)
    total = data.get('total', 1)
    filename = f"{order_id}_{order_item_id}_{style}_{size}_{color}_{stt}_{total}_qr.png"
    
    # Upload to B2
    url = upload_qr_to_b2(image_bytes, filename)
    
    return {"url": url}
