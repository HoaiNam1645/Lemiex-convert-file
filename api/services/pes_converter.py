"""
Optimized PES processing utilities for API
"""

import os
import sys
import base64
import tempfile
import pathlib
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pyembroidery import read
from pes_to_json import (
    compute_hash8,
    load_cache,
    save_cache,
    compute_metrics,
    build_color_blocks,
    thread_to_hex,
    rgb_to_hex,
    assign_colors_to_needles,
)
from render_pes_trueview import render_pes


def process_pes_to_json_fast(pes_path: str, preview_size: int = 400) -> Dict:
    """
    Fast PES to JSON conversion with smaller preview
    """
    pattern = read(str(pes_path))
    if pattern is None:
        raise ValueError(f"Unable to read PES pattern from {pes_path}")

    file_hash8 = compute_hash8(pes_path)
    cache = load_cache()

    # Generate smaller preview for speed
    preview_data = generate_preview_fast(pes_path, max_size=preview_size)
    
    # Get basic file information
    pes_filename = os.path.basename(pes_path)
    stitch_count = pattern.count_stitches()
    bounds = pattern.bounds()
    
    if bounds:
        min_x, min_y, max_x, max_y = bounds
        width_mm = round((max_x - min_x) / 10, 1)
        height_mm = round((max_y - min_y) / 10, 1)
    else:
        width_mm = height_mm = 0
    
    color_blocks = build_color_blocks(pattern)
    threads = pattern.threadlist or []
    color_count = len({c for c in (thread_to_hex(t) for t in threads) if c})
    stop_flags = [block.get("stop_funshion", False) for block in color_blocks]
    metrics = compute_metrics(pattern)
    
    # Process colors
    colors = []
    for idx, block in enumerate(color_blocks):
        thread = block.get("thread")
        color_num = idx + 1
        color_rgb = thread.color if thread else 0
        st_count = block.get("stitch_count", 0)
        
        code = getattr(thread, "catalog_number", "")
        color_way = code.split("-")[1] if code and "-" in code else code
        name = getattr(thread, "description", "")
        chart = getattr(thread, "brand", "")
        
        display_code = code
        if chart in ["Metro Pro", "Lemiex"] and "-" in code:
            parts = code.split("-")
            if len(parts) == 2:
                try:
                    num1, num2 = int(parts[0]), int(parts[1])
                    display_code = str(min(num1, num2))
                except ValueError:
                    pass
        
        stop_flag = bool(stop_flags[idx]) if idx < len(stop_flags) else False
        if stop_flag and name:
            name = f"{name}, Stop"

        colors.append({
            "id": color_num,
            "sequence": color_num,
            "needle_number": None,
            "code": display_code,
            "original_code": code,
            "color_way": color_way,
            "name": name,
            "chart": chart,
            "rgb_int": color_rgb,
            "rgb_hex": rgb_to_hex(color_rgb),
            "stitch_count": st_count,
            "stop_funshion": stop_flag,
        })
    
    pes_data = {
        "file_info": {
            "filename": pes_filename,
            "filepath": pes_path,
            "hash8": file_hash8,
            "stitch_count": stitch_count,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "color_count": color_count,
            "area_mm2": metrics["area_mm2"],
            "color_changes": metrics["color_changes"],
            "stops": len(colors),
            "trims": metrics["trims"],
            "appliques": metrics["appliques"],
        },
        "preview": preview_data,
        "colors": colors,
        "needle_assignment": {
            "assignments": {},
            "defaults": {
                "black_needle": 5,
                "white_needle": 8
            }
        },
        "metadata": {
            "generated_by": "pes_converter.py",
            "version": "1.0",
            "pyembroidery_bounds": bounds
        }
    }
    
    # Auto-assign needles
    cached_entry = cache.get(file_hash8)
    if cached_entry and cached_entry.get("assignments"):
        needle_assignments = cached_entry["assignments"]
        cached_colors = {c.get("sequence"): c.get("needle_number") for c in cached_entry.get("colors", [])}
        for color in colors:
            nn = cached_colors.get(color["sequence"])
            color["needle_number"] = nn if nn is not None else color.get("needle_number")
    else:
        needle_assignments = assign_colors_to_needles(colors)
        cache[file_hash8] = {
            "assignments": needle_assignments,
            "colors": [{"sequence": c["sequence"], "needle_number": c["needle_number"]} for c in colors],
        }
        save_cache(cache)
    
    pes_data["needle_assignment"]["assignments"] = needle_assignments
    
    return pes_data


def process_pes_to_json_no_preview(pes_path: str) -> Dict:
    """
    Ultra-fast PES to JSON without preview generation
    """
    pattern = read(str(pes_path))
    if pattern is None:
        raise ValueError(f"Unable to read PES pattern from {pes_path}")

    file_hash8 = compute_hash8(pes_path)
    cache = load_cache()
    
    pes_filename = os.path.basename(pes_path)
    stitch_count = pattern.count_stitches()
    bounds = pattern.bounds()
    
    if bounds:
        min_x, min_y, max_x, max_y = bounds
        width_mm = round((max_x - min_x) / 10, 1)
        height_mm = round((max_y - min_y) / 10, 1)
    else:
        width_mm = height_mm = 0
    
    color_blocks = build_color_blocks(pattern)
    threads = pattern.threadlist or []
    color_count = len({c for c in (thread_to_hex(t) for t in threads) if c})
    stop_flags = [block.get("stop_funshion", False) for block in color_blocks]
    metrics = compute_metrics(pattern)
    
    colors = []
    for idx, block in enumerate(color_blocks):
        thread = block.get("thread")
        color_num = idx + 1
        color_rgb = thread.color if thread else 0
        st_count = block.get("stitch_count", 0)
        
        code = getattr(thread, "catalog_number", "")
        color_way = code.split("-")[1] if code and "-" in code else code
        name = getattr(thread, "description", "")
        chart = getattr(thread, "brand", "")
        
        display_code = code
        if chart in ["Metro Pro", "Lemiex"] and "-" in code:
            parts = code.split("-")
            if len(parts) == 2:
                try:
                    num1, num2 = int(parts[0]), int(parts[1])
                    display_code = str(min(num1, num2))
                except ValueError:
                    pass
        
        stop_flag = bool(stop_flags[idx]) if idx < len(stop_flags) else False
        if stop_flag and name:
            name = f"{name}, Stop"

        colors.append({
            "id": color_num,
            "sequence": color_num,
            "needle_number": None,
            "code": display_code,
            "original_code": code,
            "color_way": color_way,
            "name": name,
            "chart": chart,
            "rgb_int": color_rgb,
            "rgb_hex": rgb_to_hex(color_rgb),
            "stitch_count": st_count,
            "stop_funshion": stop_flag,
        })
    
    pes_data = {
        "file_info": {
            "filename": pes_filename,
            "filepath": pes_path,
            "hash8": file_hash8,
            "stitch_count": stitch_count,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "color_count": color_count,
            "area_mm2": metrics["area_mm2"],
            "color_changes": metrics["color_changes"],
            "stops": len(colors),
            "trims": metrics["trims"],
            "appliques": metrics["appliques"],
        },
        "preview": None,  # No preview
        "colors": colors,
        "needle_assignment": {
            "assignments": {},
            "defaults": {
                "black_needle": 5,
                "white_needle": 8
            }
        },
        "metadata": {
            "generated_by": "pes_converter.py",
            "version": "1.0",
            "pyembroidery_bounds": bounds
        }
    }
    
    cached_entry = cache.get(file_hash8)
    if cached_entry and cached_entry.get("assignments"):
        needle_assignments = cached_entry["assignments"]
        cached_colors = {c.get("sequence"): c.get("needle_number") for c in cached_entry.get("colors", [])}
        for color in colors:
            nn = cached_colors.get(color["sequence"])
            color["needle_number"] = nn if nn is not None else color.get("needle_number")
    else:
        needle_assignments = assign_colors_to_needles(colors)
        cache[file_hash8] = {
            "assignments": needle_assignments,
            "colors": [{"sequence": c["sequence"], "needle_number": c["needle_number"]} for c in colors],
        }
        save_cache(cache)
    
    pes_data["needle_assignment"]["assignments"] = needle_assignments
    
    return pes_data


def generate_preview_fast(pes_path: str, max_size: int = 400) -> Dict[str, str]:
    """
    Generate smaller preview for faster response
    """
    pes_file = pathlib.Path(pes_path)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
        png_path = tmpfile.name

    try:
        render_pes(
            pes_path=pes_file,
            png_path=pathlib.Path(png_path),
            background=None,
            linewidth=1,  # Thinner line = faster
            margin=0,
            max_size=max_size,  # Smaller size
            native_size=True,
            output_base64=False,
        )
        with open(png_path, "rb") as img_file:
            img_data = base64.b64encode(img_file.read()).decode("ascii")
    finally:
        try:
            os.remove(png_path)
        except OSError:
            pass

    return {
        "image_data": img_data,
        "format": "png",
        "encoding": "base64",
    }


def generate_pes_preview(
    pes_path: str,
    max_size: int = 800,
    linewidth: int = 2,
) -> bytes:
    """
    Generate PNG preview of PES file
    
    Args:
        pes_path: Path to PES file
        max_size: Max dimension in pixels
        linewidth: Line thickness
    
    Returns:
        PNG image data as bytes
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_png:
        tmp_png_path = tmp_png.name
    
    try:
        render_pes(
            pes_path=pathlib.Path(pes_path),
            png_path=pathlib.Path(tmp_png_path),
            background=None,
            linewidth=linewidth,
            margin=0,
            max_size=max_size,
            native_size=True,
            output_base64=False,
        )
        
        with open(tmp_png_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_png_path):
            os.unlink(tmp_png_path)
