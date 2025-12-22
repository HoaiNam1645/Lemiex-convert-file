#!/usr/bin/env python3
"""
PES to JSON Converter
Converts PES embroidery files to JSON format for web interface
Based on pesinfo.py functionality
"""

import os
import json
import tempfile
import base64
import argparse
import pathlib
from typing import Dict, List
import hashlib
import json

from pyembroidery import COLOR_CHANGE, END, STOP, TRIM, STITCH, read
CACHE_FILE = os.path.join(os.path.dirname(__file__), "needle_cache.json")


def compute_hash8(pes_path: str) -> str:
    """Compute short hash of PES file contents (first 8 hex chars of sha256)."""
    h = hashlib.sha256()
    with open(pes_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:8]


def load_cache() -> Dict:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache: Dict) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# APPLIQUE symbol is not always present; guard access dynamically
APPLIQUE = getattr(__import__("pyembroidery"), "APPLIQUE", None)
from render_pes_trueview import render_pes as render_trueview

def rgb_to_hex(rgb_int):
    """Convert RGB integer to hex color string"""
    r = (rgb_int >> 16) & 0xFF
    g = (rgb_int >> 8) & 0xFF
    b = rgb_int & 0xFF
    return f"#{r:02X}{g:02X}{b:02X}"


def thread_to_hex(thread) -> str:
    """Best-effort hex color from thread object."""
    if thread is None:
        return ""
    if hasattr(thread, "hex_color"):
        val = thread.hex_color
        val = val() if callable(val) else val
        if val:
            val = str(val)
            return val if val.startswith("#") else f"#{val}"
    color_val = getattr(thread, "color", None)
    if isinstance(color_val, int):
        return rgb_to_hex(color_val)
    return ""


def generate_preview_base64(pes_path: str) -> Dict[str, str]:
    """Render TrueView preview and return base64 payload."""
    pes_file = pathlib.Path(pes_path)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
        png_path = tmpfile.name

    try:
        render_trueview(
            pes_path=pes_file,
            png_path=pathlib.Path(png_path),
            background=None,
            linewidth=2,
            margin=0,
            max_size=800,
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


def compute_stop_flags(pattern, block_count: int) -> List[bool]:
    """Mark whether each color block has a STOP command before its color change."""
    stop_flags = [False] * block_count
    thread_idx = 0

    for _, _, cmd in pattern.stitches:
        if cmd == STOP:
            if thread_idx < block_count:
                stop_flags[thread_idx] = True
        elif cmd == COLOR_CHANGE:
            thread_idx = min(thread_idx + 1, max(block_count - 1, 0))
        elif cmd == END:
            break

    return stop_flags


def compute_metrics(pattern) -> Dict[str, float]:
    """Compute high-level stitch metrics similar to extract_pes.py."""
    stitches = pattern.stitches or []
    if not stitches:
        return {
            "area_mm2": 0.0,
            "color_changes": 0,
            "stops": 0,
            "trims": 0,
            "appliques": 0,
        }

    UNITS_TO_MM = 0.1

    xs = [pt[0] for pt in stitches]
    ys = [pt[1] for pt in stitches]
    width_mm = (max(xs) - min(xs)) * UNITS_TO_MM if xs else 0.0
    height_mm = (max(ys) - min(ys)) * UNITS_TO_MM if ys else 0.0
    area_mm2 = round(width_mm * height_mm, 1)

    color_changes = sum(1 for _, _, cmd in stitches if cmd == COLOR_CHANGE)
    stops = sum(1 for _, _, cmd in stitches if cmd == STOP)
    trims = sum(1 for _, _, cmd in stitches if cmd == TRIM)
    appliques = (
        sum(1 for _, _, cmd in stitches if cmd == APPLIQUE)
        if APPLIQUE is not None
        else 0
    )

    return {
        "area_mm2": area_mm2,
        "color_changes": color_changes,
        "stops": stops,
        "trims": trims,
        "appliques": appliques,
    }


def build_color_blocks(pattern) -> List[Dict]:
    """Segment stitches into color blocks, capturing stop flag and stitch count per block."""
    blocks: List[Dict] = []
    thread_idx = 0
    stitch_count = 0

    def append_block(stop_flag: bool):
        nonlocal stitch_count, thread_idx
        thread = None
        if getattr(pattern, "threadlist", None):
            idx = min(thread_idx, len(pattern.threadlist) - 1)
            thread = pattern.threadlist[idx]
        blocks.append(
            {
                "thread": thread,
                "stop_funshion": stop_flag,
                "stitch_count": stitch_count,
            }
        )
        stitch_count = 0

    for _, _, cmd in pattern.stitches:
        if cmd == STITCH:
            stitch_count += 1
        elif cmd == STOP:
            append_block(True)
        elif cmd == COLOR_CHANGE:
            append_block(False)
            thread_idx += 1
        elif cmd == END:
            break

    if stitch_count:
        append_block(False)

    return blocks

def assign_colors_to_needles(colors):
    """
    Assign colors to 12 needles with smart placement:
    - Black colors (137) -> Needle 5
    - White colors (135) -> Needle 8  
    - Other colors -> Random assignment
    """
    import random
    
    needle_assignments = {}
    for i in range(1, 13):
        needle_assignments[str(i)] = None
    
    used_needles = set()
    assigned_colors = set()
    
    print("\n" + "="*50)
    print("NEEDLE ASSIGNMENT LOGIC")
    print("="*50)
    
    # Step 1: Force assign black to needle 5
    black_colors = []
    white_colors = []
    other_colors = []
    
    for color in colors:
        r = (color["rgb_int"] >> 16) & 0xFF
        g = (color["rgb_int"] >> 8) & 0xFF
        b = color["rgb_int"] & 0xFF
        
        # Check if it's black (code 137 or very dark RGB)
        if color["code"] == "137" or (r < 50 and g < 50 and b < 50):
            black_colors.append(color)
        # Check if it's white (code 135 or very light RGB)
        elif color["code"] == "135" or (r > 200 and g > 200 and b > 200):
            white_colors.append(color)
        else:
            other_colors.append(color)
    
    # Assign ALL black colors to needle 5
    if black_colors:
        first_black = black_colors[0]
        needle_assignments["5"] = {
            "code": first_black["code"],
            "name": first_black["name"],
            "rgb_hex": first_black["rgb_hex"]
        }
        used_needles.add(5)
        
        # Assign needle 5 to ALL black colors
        for black_color in black_colors:
            black_color["needle_number"] = 5
            assigned_colors.add(black_color["id"])
        
        print(f"✓ FORCED: {len(black_colors)} Black colors ({first_black['code']}) -> Needle 5")
    
    # Assign ALL white colors to needle 8
    if white_colors:
        first_white = white_colors[0]
        needle_assignments["8"] = {
            "code": first_white["code"],
            "name": first_white["name"],
            "rgb_hex": first_white["rgb_hex"]
        }
        used_needles.add(8)
        
        # Assign needle 8 to ALL white colors
        for white_color in white_colors:
            white_color["needle_number"] = 8
            assigned_colors.add(white_color["id"])
            
        print(f"✓ FORCED: {len(white_colors)} White colors ({first_white['code']}) -> Needle 8")
    
    # Step 2: Collect remaining colors (including remaining black/white if any)
    remaining_colors = []
    for color in colors:
        if color["id"] not in assigned_colors:
            remaining_colors.append(color)

    # Step 3: Group colors by code+rgb to handle duplicates smartly
    color_groups = {}
    for color in remaining_colors:
        color_key = f"{color['code']}_{color['rgb_hex']}"
        if color_key not in color_groups:
            color_groups[color_key] = []
        color_groups[color_key].append(color)
    
    print(f"📋 Found {len(color_groups)} unique colors, {len(remaining_colors)} total sequences")
    
    # Step 4: Assign needles to unique colors first
    available_needles = [i for i in range(1, 13) if i not in used_needles]    # Shuffle for random assignment but use consistent seed for reproducibility
    unique_color_keys = list(color_groups.keys())
    seed_value = hash(''.join(sorted(unique_color_keys))) % 2147483647
    random.seed(seed_value)
    random.shuffle(available_needles)
    
    print(f"🎲 Using seed {seed_value} for reproducible random assignment")
    print(f"📍 Available needles: {available_needles}")
    print(f"🎨 Unique color groups to assign: {len(unique_color_keys)}")
    
    # Assign each unique color group to a needle
    needle_assignments_made = {}
    for i, color_key in enumerate(unique_color_keys):
        if i < len(available_needles):
            needle_num = available_needles[i]
            colors_in_group = color_groups[color_key]
            representative_color = colors_in_group[0]  # Use first color as representative
            
            needle_assignments[str(needle_num)] = {
                "code": representative_color["code"],
                "name": representative_color["name"], 
                "rgb_hex": representative_color["rgb_hex"]
            }
            
            # Assign this needle to ALL colors in the group (including duplicates)
            for color in colors_in_group:
                color["needle_number"] = needle_num
            
            needle_assignments_made[color_key] = needle_num
            print(f"🎲 Random: {representative_color['code']} -> Needle {needle_num} ({len(colors_in_group)} sequences)")
        else:
            print(f"⚠ No more needles available for color group {color_key}")
            # Assign null to colors that couldn't get needles
            colors_in_group = color_groups[color_key]
            for color in colors_in_group:
                color["needle_number"] = None
    
    print("="*50)
    return needle_assignments

def process_pes_to_json(pes_path, output_path=None):
    """
    Convert PES file to JSON format
    
    Args:
        pes_path: Path to PES file
        output_path: Output JSON path (optional)
    
    Returns:
        dict: PES data in JSON format
    """
    print(f"Processing: {pes_path}")
    
    # Read PES file
    pattern = read(str(pes_path))
    if pattern is None:
        raise ValueError(f"Unable to read PES pattern from {pes_path}")

    file_hash8 = compute_hash8(pes_path)
    cache = load_cache()

    # Generate preview image using TrueView renderer
    preview_data = generate_preview_base64(pes_path)
    
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
    # Capture threads for code/name/chart extraction while keeping block segmentation
    threads = pattern.threadlist or []
    color_count = len({c for c in (thread_to_hex(t) for t in threads) if c})
    stop_flags = [block.get("stop_funshion", False) for block in color_blocks]
    metrics = compute_metrics(pattern)
    
    # Process color information
    colors = []
    for idx, block in enumerate(color_blocks):
        thread = block.get("thread")
        color_num = idx + 1
        color_rgb = thread.color if thread else 0
        st_count = block.get("stitch_count", 0)
        
        # Extract thread information
        code = getattr(thread, "catalog_number", "")
        if code and "-" in code:
            color_way = code.split("-")[1]
        else:
            color_way = code
        
        name = getattr(thread, "description", "")
        chart = getattr(thread, "brand", "")
        
        # Process display code for Metro Pro and Lemiex charts
        display_code = code
        if chart in ["Metro Pro", "Lemiex"] and "-" in code:
            parts = code.split("-")
            if len(parts) == 2:
                try:
                    num1, num2 = int(parts[0]), int(parts[1])
                    display_code = str(min(num1, num2))
                except ValueError:
                    display_code = code
        
        stop_flag = bool(stop_flags[idx]) if idx < len(stop_flags) else False
        if stop_flag:
            if name:
                name = f"{name}, Stop"
            else:
                name = "Stop"

        color_data = {
            "id": color_num,
            "sequence": color_num,
            "needle_number": None,  # Will be assigned by web interface
            "code": display_code,
            "original_code": code,
            "color_way": color_way,
            "name": name,
            "chart": chart,
            "rgb_int": color_rgb,
            "rgb_hex": rgb_to_hex(color_rgb),
            "stitch_count": st_count,
            "stop_funshion": stop_flag,
        }
        
        colors.append(color_data)
    
    # Create JSON structure
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
            "assignments": {},  # Will be populated by web interface
            "defaults": {
                "black_needle": 5,  # Default needle for black colors
                "white_needle": 8   # Default needle for white colors
            }
        },
        "metadata": {
            "generated_by": "pes_to_json.py",
            "version": "1.0",
            "pyembroidery_bounds": bounds
        }
    }
    
    # Auto-assign colors to needles with smart placement, unless cached
    cached_entry = cache.get(file_hash8)
    if cached_entry and cached_entry.get("assignments"):
        needle_assignments = cached_entry["assignments"]
        # Restore color needle_number from cache if available
        cached_colors = {c.get("sequence"): c.get("needle_number") for c in cached_entry.get("colors", [])}
        for color in colors:
            nn = cached_colors.get(color["sequence"])
            color["needle_number"] = nn if nn is not None else color.get("needle_number")
        print(f"📌 Cache hit for hash {file_hash8}, reusing needle assignments")
    else:
        needle_assignments = assign_colors_to_needles(colors)
        cache[file_hash8] = {
            "assignments": needle_assignments,
            "colors": [{"sequence": c["sequence"], "needle_number": c["needle_number"]} for c in colors],
        }
        save_cache(cache)
    
    # Update needle_assignment section with actual assignments
    pes_data["needle_assignment"]["assignments"] = needle_assignments
    
    # Save to JSON file if output path specified
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(pes_data, f, indent=2, ensure_ascii=False)
        print(f"JSON saved to: {output_path}")
    
    return pes_data

def main():
    parser = argparse.ArgumentParser(description='Convert PES files to JSON format')
    parser.add_argument('input', help='Input PES file path')
    parser.add_argument('-o', '--output', help='Output JSON file path')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: File not found: {args.input}")
        return 1
    
    # Generate output path if not specified
    if not args.output:
        base_name = os.path.splitext(args.input)[0]
        args.output = base_name + '.json'
    
    try:
        pes_data = process_pes_to_json(args.input, args.output)
        
        if args.verbose:
            print("\n" + "="*50)
            print("PES FILE ANALYSIS")
            print("="*50)
            print(f"File: {pes_data['file_info']['filename']}")
            print(f"Stitches: {pes_data['file_info']['stitch_count']:,}")
            print(f"Dimensions: {pes_data['file_info']['width_mm']} x {pes_data['file_info']['height_mm']} mm")
            print(f"Colors: {pes_data['file_info']['color_count']}")
            print("\nColor Details:")
            for color in pes_data['colors']:
                print(f"  {color['sequence']:2d}. Code {color['code']:>3} - {color['name']} ({color['chart']})")
            
        print(f"\n✅ Successfully converted PES to JSON!")
        print(f"📄 Input: {args.input}")
        print(f"💾 Output: {args.output}")
        
    except Exception as e:
        print(f"❌ Error processing PES file: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())