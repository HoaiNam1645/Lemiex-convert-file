import argparse
import base64
import io
import pathlib
from typing import List, Optional, Tuple

from pyembroidery import STITCH, read


def _parse_color_tuple(hex_str: str) -> Tuple[int, int, int, int]:
    hs = hex_str.lstrip("#")
    if len(hs) == 6:
        r, g, b = int(hs[0:2], 16), int(hs[2:4], 16), int(hs[4:6], 16)
        a = 255
    elif len(hs) == 8:
        a, r, g, b = int(hs[0:2], 16), int(hs[2:4], 16), int(hs[4:6], 16), int(hs[6:8], 16)
    else:
        raise ValueError(f"Invalid color: {hex_str}")
    return (r, g, b, a)


def _ensure_pillow():
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Pillow is required for the pillow engine. pip install pillow") from exc
    return Image, ImageDraw


def _gradient_factor(t: float) -> float:
    """Piecewise curve for TrueView-like brightness along path (0..1)."""
    t = max(0.0, min(1.0, t))
    shade_ends = 0.65
    shade_edge = 1.1
    shade_center = 1.55
    p1, p2, p3 = 0.40, 0.50, 0.70
    if t <= p1:
        fr, to, rng = shade_ends, shade_edge, p1
        amt = t / rng if rng else 0.0
    elif t <= p2:
        fr, to, rng = shade_edge, shade_center, (p2 - p1)
        amt = (t - p1) / rng if rng else 0.0
    elif t <= p3:
        fr, to, rng = shade_center, shade_edge, (p3 - p2)
        amt = (t - p2) / rng if rng else 0.0
    else:
        fr, to, rng = shade_edge, shade_ends, (1 - p3)
        amt = (t - p3) / rng if rng else 0.0
    v = fr + amt * (to - fr)
    return max(min(v, 1.55), 0.0)


def _direction_gain(dx: float, dy: float) -> float:
    """Directional lighting gain (light from top-left)."""
    lx, ly = 0.70710678, -0.70710678
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    dot = (dx * lx + dy * ly) / length
    return 0.6 + 0.4 * abs(dot)


def _apply_shade(rgb: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    """Apply shade with additive highlight so dark threads still show sheen."""
    r, g, b = rgb
    if factor >= 1.0:
        boost = factor - 1.0
        mix = min(boost, 1.0)
        # multiplicative lift + additive blend toward highlight
        r = r * (1.0 + 0.6 * boost) + (255 - r) * (0.7 * mix)
        g = g * (1.0 + 0.6 * boost) + (255 - g) * (0.7 * mix)
        b = b * (1.0 + 0.6 * boost) + (255 - b) * (0.7 * mix)
    else:
        r = r * factor
        g = g * factor
        b = b * factor
    r = max(0, min(int(r), 255))
    g = max(0, min(int(g), 255))
    b = max(0, min(int(b), 255))
    return (r, g, b)


def _extract_satin_columns(block: List[Tuple[float, float, int]]):
    """Detect satin columns as alternating zig-zag STITCH pairs.

    Tighten opposite-direction requirement to avoid mis-labeling tatami as satin.
    """
    dirs = []
    for (x0, y0, c0), (x1, y1, c1) in zip(block, block[1:]):
        if c0 != STITCH or c1 != STITCH:
            continue
        dx, dy = x1 - x0, y1 - y0
        mag = (dx * dx + dy * dy) ** 0.5
        if mag == 0:
            continue
        dirs.append((dx / mag, dy / mag))

    if len(dirs) < 4:
        return []

    opposite = 0
    for (dx1, dy1), (dx2, dy2) in zip(dirs, dirs[1:]):
        if dx1 * dx2 + dy1 * dy2 < -0.2:
            opposite += 1

    if opposite / len(dirs) < 0.55:
        return []

    columns = []
    i = 0
    n = len(block)
    while i < n - 1:
        x1, y1, c1 = block[i]
        x2, y2, c2 = block[i + 1]
        if c1 == STITCH and c2 == STITCH:
            columns.append(((float(x1), float(y1)), (float(x2), float(y2))))
            i += 2
        else:
            i += 1
    return columns


def _satin_shade(color: Tuple[int, int, int]):
    dark = 0.55
    bright = 1.65

    def shade_at(t: float) -> Tuple[int, int, int]:
        k = 1.0 - abs(t - 0.5) * 2.0
        factor = dark + (bright - dark) * k
        return _apply_shade(color, factor)

    return shade_at


def _render_satin_column(draw, left, right, color, width):
    shade = _satin_shade(color)
    steps = max(8, min(24, width * 2))
    lx, ly = left
    rx, ry = right
    for i in range(steps):
        t0 = i / steps
        t1 = (i + 1) / steps
        mid_t = (t0 + t1) * 0.5
        c = shade(mid_t)
        x0 = lx + (rx - lx) * t0
        y0 = ly + (ry - ly) * t0
        x1 = lx + (rx - lx) * t1
        y1 = ly + (ry - ly) * t1
        draw.line((x0, y0, x1, y1), fill=c + (255,), width=width, joint="curve")


def _render_tatami_block(draw, pts: List[Tuple[float, float]], color: Tuple[int, int, int], width: int):
    """Render tatami as alternating low-contrast rows."""
    if len(pts) < 2:
        return
    shades = (0.92, 1.0)
    run_idx = 0
    last_dir = None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        mag = (dx * dx + dy * dy) ** 0.5
        if mag == 0:
            continue
        dir_vec = (dx / mag, dy / mag)
        if last_dir is not None:
            dot = dir_vec[0] * last_dir[0] + dir_vec[1] * last_dir[1]
            if dot < -0.2:
                run_idx ^= 1
        last_dir = dir_vec
        rgb = _apply_shade(color, shades[run_idx])
        draw.line((x0, y0, x1, y1), fill=rgb + (255,), width=width, joint="curve")


def _tatami_score(block: List[Tuple[float, float, int]]) -> float:
    """Score how tatami-like a block is based on long, straight runs."""
    if len(block) < 15:
        return 0.0

    dirs = []
    for (x0, y0, c0), (x1, y1, c1) in zip(block, block[1:]):
        if c0 != STITCH or c1 != STITCH:
            continue
        dx, dy = x1 - x0, y1 - y0
        mag = (dx * dx + dy * dy) ** 0.5
        if mag == 0:
            continue
        dirs.append((dx / mag, dy / mag))

    if len(dirs) < 12:
        return 0.0

    run_lengths = []
    run = 1
    reversals = 0
    for (dx1, dy1), (dx2, dy2) in zip(dirs, dirs[1:]):
        dot = dx1 * dx2 + dy1 * dy2
        if dot > 0.93:
            run += 1
        else:
            run_lengths.append(run)
            run = 1
        if dot < -0.2:
            reversals += 1
    run_lengths.append(run)

    if not run_lengths:
        return 0.0

    median_run = sorted(run_lengths)[len(run_lengths) // 2]
    long_runs = sum(1 for r in run_lengths if r >= 3)
    straight_fraction = long_runs / len(run_lengths)
    reversal_rate = reversals / max(1, len(run_lengths))

    # Higher when there are many straight runs, modest reversals (row flips), and longer median.
    score = 0.5 * straight_fraction + 0.3 * min(median_run / 6.0, 1.0) + 0.2 * min(reversal_rate / 0.6, 1.0)
    return max(0.0, min(score, 1.0))


def render_pes(
    pes_path: pathlib.Path,
    png_path: pathlib.Path,
    *,
    background: Optional[str] = None,
    linewidth: Optional[int] = 2,
    scale: Optional[float] = None,
    margin: int = 20,
    max_size: int = 1200,
    native_size: bool = False,
    output_base64: bool = False,
) -> pathlib.Path:
    """Render a PES to a TrueView-like PNG. Defaults to transparent background."""

    pattern = read(str(pes_path))
    if pattern is None:
        raise ValueError(f"Unable to read PES file: {pes_path}")

    pattern = pattern.copy()
    min_x, min_y, max_x, max_y = pattern.bounds()
    width = max_x - min_x
    height = max_y - min_y

    if native_size:
        base_scale = 0.35
        if max(width, height):
            usable = max_size - 2 * margin
            usable = max(1, usable)
            fit_scale = usable / max(width, height)
            scale = max(base_scale, fit_scale)
        else:
            scale = base_scale
    elif scale is None:
        usable = max_size - 2 * margin
        usable = max(1, usable)
        scale = usable / max(width, height) if max(width, height) else 1.0

    if scale != 1.0 or margin or min_x or min_y:
        pattern.stitches = [
            ((x - min_x) * scale + margin, (y - min_y) * scale + margin, cmd)
            for (x, y, cmd) in pattern.stitches
        ]

    Image, ImageDraw = _ensure_pillow()
    bg = _parse_color_tuple(background) if background else (0, 0, 0, 0)
    min_x, min_y, max_x, max_y = 0, 0, 0, 0
    if pattern.stitches:
        xs = [s[0] for s in pattern.stitches]
        ys = [s[1] for s in pattern.stitches]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
    width_px = int(max_x - min_x + margin * 2 + 2)
    height_px = int(max_y - min_y + margin * 2 + 2)
    width_px = max(width_px, 1)
    height_px = max(height_px, 1)

    img = Image.new("RGBA", (width_px, height_px), bg)
    draw = ImageDraw.Draw(img, "RGBA")

    lw = linewidth if linewidth is not None else 2
    if native_size:
        base_scale = 0.35
        if base_scale > 0:
            lw = max(1, int(round(lw * scale / base_scale)))

    for block, thread in pattern.get_as_stitchblock():
        if len(block) < 2:
            continue
        color = (thread.get_red(), thread.get_green(), thread.get_blue())

        columns = _extract_satin_columns(block)
        if columns:
            for left, right in columns:
                _render_satin_column(draw, left, right, color, lw)
            continue

        is_tatami = _tatami_score(block) >= 0.45
        if not is_tatami and len(block) >= 50 and not columns:
            is_tatami = True
        pts: List[Tuple[float, float]] = [(float(x), float(y)) for (x, y, _cmd) in block]

        if is_tatami:
            _render_tatami_block(draw, pts, color, lw)
            continue

        seg_lengths = []
        total_len = 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            dx, dy = x1 - x0, y1 - y0
            dist = (dx * dx + dy * dy) ** 0.5
            seg_lengths.append(dist)
            total_len += dist
        if total_len == 0:
            continue
        cum = 0.0
        for (x0, y0), (x1, y1), seg_len in zip(pts, pts[1:], seg_lengths):
            if seg_len == 0:
                continue
            t0 = cum / total_len
            cum += seg_len
            t1 = cum / total_len
            mid_t = (t0 + t1) * 0.5
            base = _gradient_factor(mid_t)
            gain = _direction_gain(x1 - x0, y1 - y0)
            shade = max(min(base * gain, 1.8), 0.2)
            rgb = _apply_shade(color, shade)
            draw.line((x0, y0, x1, y1), fill=rgb + (255,), width=lw, joint="curve")

    img.save(png_path)

    if output_base64:
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        print(encoded)

    return png_path


def main():
    parser = argparse.ArgumentParser(description="Render a PES file to a TrueView-style PNG (Pillow engine).")
    parser.add_argument("pes_file", type=pathlib.Path, help="Path to .PES file")
    parser.add_argument("-o", "--output", type=pathlib.Path, help="Output PNG file (default: same name with .png)")
    parser.add_argument("--background", help="Background color hex (#RRGGBB or #AARRGGBB). Omit for transparent.")
    parser.add_argument("--linewidth", type=int, help="Line width in pixels (default: 2)")
    parser.add_argument("--scale", type=float, help="Fixed scale. If omitted, auto-fit to max-size (or baseline 0.35 when native).")
    parser.add_argument("--margin", type=int, help="Margin in pixels around design (default: 20)")
    parser.add_argument("--max-size", type=int, help="Max rendered dimension in px (default: 1200)")
    parser.add_argument("--native-size", action="store_true", help="Render at baseline scale 0.35; if small, scale up to fit max-size")
    parser.add_argument("--output-base64", action="store_true", help="Print PNG as base64 to stdout (file still written if -o set)")
    args = parser.parse_args()

    png_path = args.output or args.pes_file.with_suffix(".png")
    render_pes(
        args.pes_file,
        png_path,
        background=args.background,
        linewidth=args.linewidth,
        scale=args.scale,
        margin=args.margin if args.margin is not None else 20,
        max_size=args.max_size if args.max_size is not None else 1200,
        native_size=args.native_size,
        output_base64=args.output_base64,
    )
    print(f"Wrote {png_path}")


if __name__ == "__main__":
    main()
