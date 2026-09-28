"""CLI for image → DXF laser-cut conversion."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from img_to_dxf import __version__
from img_to_dxf.convert import convert_image


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="img-to-dxf",
        description="Convert a silhouette image to DXF polylines for laser cutting.",
    )
    p.add_argument("input", type=Path, help="Input image (PNG/JPG recommended)")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output DXF path (default: <input>.dxf)",
    )
    p.add_argument(
        "--width-mm",
        type=float,
        default=None,
        help="Target width of the image in millimeters (sets scale)",
    )
    p.add_argument(
        "--mm-per-pixel",
        type=float,
        default=None,
        help="Scale as millimeters per pixel (alternative to --width-mm)",
    )
    p.add_argument(
        "--threshold",
        type=int,
        default=None,
        metavar="0-255",
        help="Manual threshold; omit for Otsu auto",
    )
    p.add_argument(
        "--invert",
        action="store_true",
        help="Treat light shapes on dark background as cut fill",
    )
    p.add_argument(
        "--blur",
        type=int,
        default=3,
        help="Gaussian blur kernel size (odd, 0=off). Default: 3",
    )
    p.add_argument(
        "--simplify",
        type=float,
        default=0.002,
        help="Contour simplification ratio (0=none). Default: 0.002",
    )
    p.add_argument(
        "--min-area",
        type=float,
        default=0.5,
        dest="min_area_mm2",
        help="Drop contours smaller than this area in mm². Default: 0.5",
    )
    p.add_argument(
        "--preview",
        type=Path,
        default=None,
        help="Write contour preview PNG (default: <output>_preview.png)",
    )
    p.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip writing preview image",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.input.exists():
        print(f"Error: input not found: {args.input}", file=sys.stderr)
        return 1

    if args.width_mm is None and args.mm_per_pixel is None:
        args.width_mm = 100.0  # sensible laser-cut default

    if args.threshold is not None and not (0 <= args.threshold <= 255):
        print("Error: --threshold must be 0–255", file=sys.stderr)
        return 1

    output = args.output or args.input.with_suffix(".dxf")
    preview: Path | None
    if args.no_preview:
        preview = None
    elif args.preview is not None:
        preview = args.preview
    else:
        preview = output.with_name(output.stem + "_preview.png")

    try:
        result = convert_image(
            args.input,
            output,
            width_mm=args.width_mm,
            mm_per_pixel=args.mm_per_pixel,
            threshold=args.threshold,
            invert=args.invert,
            blur=args.blur,
            simplify=args.simplify,
            min_area_mm2=args.min_area_mm2,
            preview_path=preview,
        )
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"DXF:      {result.dxf_path}")
    if result.preview_path:
        print(f"Preview:  {result.preview_path}")
    print(f"Contours: {result.contour_count}")
    print(
        f"Size:     {result.width_mm:.2f} × {result.height_mm:.2f} mm "
        f"({result.image_size[0]}×{result.image_size[1]} px)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
