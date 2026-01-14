
import httpx
from PIL import Image
from io import BytesIO
from typing import Dict, Any, Tuple, List
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from services.b2_storage import upload_merged_image_to_b2

# Create a thread pool for CPU-bound tasks
t_executor = ThreadPoolExecutor(max_workers=4)

async def download_image(client: httpx.AsyncClient, url: str) -> Image.Image:
    """Download image from URL and open with PIL"""
    response = await client.get(url)
    response.raise_for_status()
    # Loading image bytes is fast, opening is fast, but we should load fully to memory
    img = Image.open(BytesIO(response.content))
    img.load() # Ensure it's loaded
    return img

def merge_images_logic(img_main: Image.Image, img_qr: Image.Image) -> bytes:
    """
    Merge main image and QR code.
    Strategy: Side-by-side with Main Image larger than QR.
    CPU-bound task.
    """
    img_main = img_main.convert("RGBA")
    img_qr = img_qr.convert("RGBA")

    # Original sizes
    orig_w1, orig_h1 = img_main.size
    orig_w2, orig_h2 = img_qr.size

    # Reduce Main Image by 40% (scale to 60%)
    w1 = int(orig_w1 * 0.6)
    h1 = int(orig_h1 * 0.6)
    img_main = img_main.resize((w1, h1), Image.Resampling.LANCZOS)

    # Reduce QR Image by 20% (scale to 80%)
    target_qr_w = int(orig_w2 * 0.8)
    target_qr_h = int(orig_h2 * 0.8)
    img_qr_resized = img_qr.resize((target_qr_w, target_qr_h), Image.Resampling.LANCZOS)
    
    # Gap between images
    gap = 20
    
    # Canvas dimensions
    canvas_w = w1 + gap + target_qr_w
    canvas_h = max(h1, target_qr_h) # Ensure canvas fits both if QR is somehow taller
    
    # Create canvas (white background)
    canvas = Image.new('RGBA', (canvas_w, canvas_h), (255, 255, 255, 255))
    
    # Paste Main Image (Left, centered vertically if smaller - but here it defines height approx)
    main_y = (canvas_h - h1) // 2
    canvas.paste(img_main, (0, main_y), img_main)
    
    # Paste QR (Right, centered vertically)
    qr_y = (canvas_h - target_qr_h) // 2
    canvas.paste(img_qr_resized, (w1 + gap, qr_y), img_qr_resized)
    
    # Export
    output = BytesIO()
    # Optimize=False for speed, compress_level=1 for speed (default is 6)
    canvas.save(output, format="PNG", compress_level=3) 
    return output.getvalue()

async def process_single_merge(client: httpx.AsyncClient, url_main: str, url_qr: str, index: int) -> str:
    """
    Process a single merge operation: Download -> Merge -> Upload
    """
    # 1. Download
    try:
        # Download concurrently
        img_main, img_qr = await asyncio.gather(
            download_image(client, url_main),
            download_image(client, url_qr)
        )
    except Exception as e:
        print(f"Error downloading for merge {index}: {e}")
        return ""

    # 2. Merge (CPU bound)
    loop = asyncio.get_running_loop()
    merged_bytes = await loop.run_in_executor(
        t_executor, 
        merge_images_logic, 
        img_main, 
        img_qr
    )
    
    # 3. Generate filename
    basename = url_main.split("/")[-1]
    if "." in basename:
        basename = basename.rsplit(".", 1)[0]
    
    # Append index to filename to avoid collisions if main image is same (though typically unique)
    # But user wants standard behavior. If index is relevant to order, we might use it.
    # User's example: merged_1.png, merged_2.png -> This suggests renaming? 
    # Or just {basename}_{something}. 
    # Let's rely on basename but maybe append QR info if needed?
    # Actually user output example: `merged_1.png` suggests simpler naming or just example.
    # Let's keep `merged_{basename}.png` but if multiple QRs use same main image, we need to differentiate.
    # We will append index + 1
    
    filename = f"merged_{basename}_{index+1}.png"
    
    # 4. Upload (IO bound)
    url = await loop.run_in_executor(
        t_executor,
        upload_merged_image_to_b2,
        merged_bytes,
        filename
    )
    return url

async def merge_and_upload_images_batch(url_image: str, url_qrs: List[str]) -> Dict[str, List[str]]:
    """
    Download main image once, then merge with multiple QRs.
    """
    urls = []
    
    try:
        async with httpx.AsyncClient() as client:
            # 1. Download Main Image Once
            img_main = await download_image(client, url_image)
            
            # 2. Process each QR
            tasks = []
            for i, qr_url in enumerate(url_qrs):
                tasks.append(process_single_qr_merge(client, img_main, qr_url, url_image, i))
            
            urls = await asyncio.gather(*tasks)
            
    except Exception as e:
         raise ValueError(f"Batch merge failed: {str(e)}")

    return {"urls": urls}

async def process_single_qr_merge(client: httpx.AsyncClient, img_main: Image.Image, qr_url: str, main_url_for_name: str, index: int) -> str:
    """
    Process merge for a single QR with an already downloaded main image.
    Need to copy main image or ensure merge logic doesn't mutate it.
    PIL Image operations like resize return new image, so it's safe if we don't mutate in place before that.
    merge_images_logic calls resize which returns new image. convert returns new image.
    So it is safe to reuse img_main.
    """
    try:
        # Download QR
        img_qr = await download_image(client, qr_url)
        
        # Merge
        loop = asyncio.get_running_loop()
        merged_bytes = await loop.run_in_executor(
            t_executor, 
            merge_images_logic, 
            img_main, 
            img_qr
        )
        
        # Filename
        basename = main_url_for_name.split("/")[-1]
        if "." in basename:
            basename = basename.rsplit(".", 1)[0]
            
        # Extract meaningful part from QR filename perhaps? 
        # Or just append index. User example: merged_1.png
        # Let's append index or extract from QR.
        # QR url often has stt: 65_1_1_qr.png -> maybe use that?
        # Let's try to grab the last part of QR filename to make it unique and descriptive.
        qr_basename = qr_url.split("/")[-1].replace(".png", "").replace("_qr", "")
        
        filename = f"merged_{basename}_{qr_basename}.png"
        
        # Upload
        url = await loop.run_in_executor(
            t_executor,
            upload_merged_image_to_b2,
            merged_bytes,
            filename
        )
        return url
    except Exception as e:
        print(f"Error merging QR {qr_url}: {e}")
        return ""
