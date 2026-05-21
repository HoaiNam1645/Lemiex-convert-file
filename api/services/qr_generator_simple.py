"""
QR Code Generator Service - Simple Layout
Generates QR codes with only Order ID on top (large red) and QR below.
"""

import qrcode
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from typing import Dict, Any
import os

from services.b2_storage import upload_qr_to_b2


def generate_qr_image(data: Dict[str, Any]) -> bytes:
    order_id = data.get('order_id', '')
    order_item_id = data.get('order_item_id', '')
    pageqr = data.get('pageqr', '')

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=1,
    )
    qr.add_data(pageqr)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.convert('RGB')
    qr_width, qr_height = qr_img.size

    # Layout constants
    side_padding = 40
    top_padding = 30
    gap_text_qr = 30
    bottom_padding = 30
    title_font_size = 80

    # Load BOLD font
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
    ]

    font_title = None
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                font_title = ImageFont.truetype(font_path, title_font_size)
                break
            except:
                continue

    if font_title is None:
        font_title = ImageFont.load_default()

    # Measure title text
    tmp_img = Image.new('RGB', (10, 10))
    tmp_draw = ImageDraw.Draw(tmp_img)
    title_text = f"{order_id} - {order_item_id}" if order_item_id != '' else str(order_id)
    bbox = tmp_draw.textbbox((0, 0), title_text, font=font_title)
    title_w = bbox[2] - bbox[0]
    title_h = bbox[3] - bbox[1]

    # Canvas dimensions: width = max(title, qr) + padding; height = top + title + gap + qr + bottom
    content_width = max(title_w, qr_width)
    canvas_width = content_width + side_padding * 2
    canvas_height = top_padding + title_h + gap_text_qr + qr_height + bottom_padding

    canvas = Image.new('RGB', (canvas_width, canvas_height), color=(255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Border
    draw.rectangle(
        [(0, 0), (canvas_width - 1, canvas_height - 1)],
        outline=(80, 80, 80),
        width=2,
    )

    # Order ID centered horizontally
    title_x = (canvas_width - title_w) // 2 - bbox[0]
    title_y = top_padding - bbox[1]
    draw.text((title_x, title_y), title_text, fill=(220, 0, 0), font=font_title)

    # QR centered horizontally, below title
    qr_x = (canvas_width - qr_width) // 2
    qr_y = top_padding + title_h + gap_text_qr
    canvas.paste(qr_img, (qr_x, qr_y))

    output = BytesIO()
    canvas.save(output, format='PNG', optimize=True)
    output.seek(0)
    return output.getvalue()


async def create_qr_and_upload(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate simple QR code and upload to B2.
    Filename pattern kept identical to legacy endpoint for compatibility.
    """
    image_bytes = generate_qr_image(data)

    order_id = data.get('order_id', 0)
    order_item_id = data.get('order_item_id', 0)
    import re

    def sanitize(s):
        return re.sub(r'[^a-zA-Z0-9]', '', str(s))

    stt = data.get('stt', 1)
    total = data.get('total', 1)

    parts = [
        str(order_id),
        str(order_item_id),
        sanitize(data.get('style', '')),
        sanitize(data.get('size', '')),
        sanitize(data.get('color', '')),
        str(stt),
        str(total),
    ]
    filename = "_".join(p for p in parts if p) + "_qr.png"

    url = upload_qr_to_b2(image_bytes, filename)
    return {"url": url}
