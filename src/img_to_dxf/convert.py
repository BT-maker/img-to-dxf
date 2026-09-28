"""Core pipeline: silhouette image → closed polylines → DXF."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import cv2
import ezdxf
import numpy as np
from ezdxf import units


@dataclass
class ConvertArtifacts:
    contours: list[np.ndarray]
    scale: float
    width_mm: float
    height_mm: float
    image_size: tuple[int, int]  # (w, h) pixels
    gray: np.ndarray
    binary: np.ndarray


@dataclass
class ConvertResult:
    dxf_path: Path
    preview_path: Path | None
    contour_count: int
    width_mm: float
    height_mm: float
    image_size: tuple[int, int]


def load_gray_from_bytes(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError("Cannot decode image bytes")
    return _image_to_gray(image)


def load_gray(image_path: Path) -> np.ndarray:
    image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    return _image_to_gray(image)


def _image_to_gray(image: np.ndarray) -> np.ndarray:
    # Prefer alpha as mask when present (transparent PNGs / logos).
    if image.ndim == 3 and image.shape[2] == 4:
        bgr = image[:, :, :3]
        alpha = image[:, :, 3]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = np.where(alpha > 0, gray, 255).astype(np.uint8)
        return gray

    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    return image


def to_binary(
    gray: np.ndarray,
    *,
    threshold: int | None,
    invert: bool,
    blur: int,
) -> np.ndarray:
    work = gray
    if blur > 0:
        k = blur if blur % 2 == 1 else blur + 1
        work = cv2.GaussianBlur(work, (k, k), 0)

    # Default: dark shape on light bg → INV so the cut fill is white (255).
    # --invert: light shape on dark bg → plain BINARY.
    if invert:
        base = cv2.THRESH_BINARY
    else:
        base = cv2.THRESH_BINARY_INV

    if threshold is None:
        _, binary = cv2.threshold(work, 0, 255, base + cv2.THRESH_OTSU)
    else:
        _, binary = cv2.threshold(work, threshold, 255, base)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    return binary


def extract_contours(
    binary: np.ndarray,
    *,
    simplify: float,
    min_area_px: float,
) -> list[np.ndarray]:
    contours, hierarchy = cv2.findContours(
        binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE
    )
    if hierarchy is None:
        return []

    result: list[np.ndarray] = []
    for contour in contours:
        area = abs(cv2.contourArea(contour))
        if area < min_area_px:
            continue
        if len(contour) < 3:
            continue

        peri = cv2.arcLength(contour, True)
        epsilon = max(simplify * peri, 0.5)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx) < 3:
            continue
        result.append(approx.reshape(-1, 2))

    return result


def process_gray(
    gray: np.ndarray,
    *,
    width_mm: float | None = None,
    mm_per_pixel: float | None = None,
    threshold: int | None = None,
    invert: bool = False,
    blur: int = 3,
    simplify: float = 0.002,
    min_area_mm2: float = 0.5,
) -> ConvertArtifacts:
    if width_mm is None and mm_per_pixel is None:
        raise ValueError("Provide either width_mm or mm_per_pixel")
    if width_mm is not None and mm_per_pixel is not None:
        raise ValueError("Use only one of width_mm or mm_per_pixel")

    h, w = gray.shape[:2]

    if width_mm is not None:
        if width_mm <= 0:
            raise ValueError("width_mm must be positive")
        scale = width_mm / w
    else:
        assert mm_per_pixel is not None
        if mm_per_pixel <= 0:
            raise ValueError("mm_per_pixel must be positive")
        scale = mm_per_pixel

    binary = to_binary(gray, threshold=threshold, invert=invert, blur=blur)
    min_area_px = min_area_mm2 / (scale * scale)
    contours = extract_contours(binary, simplify=simplify, min_area_px=min_area_px)

    if not contours:
        raise RuntimeError(
            "No usable contours found. Try invert, adjust threshold, "
            "or lower min area."
        )

    return ConvertArtifacts(
        contours=contours,
        scale=scale,
        width_mm=w * scale,
        height_mm=h * scale,
        image_size=(w, h),
        gray=gray,
        binary=binary,
    )


def contours_to_dxf_bytes(artifacts: ConvertArtifacts) -> bytes:
    doc = ezdxf.new("R2010")
    doc.units = units.MM
    doc.header["$INSUNITS"] = units.MM

    if "CUT" not in doc.layers:
        doc.layers.add("CUT", color=1)

    msp = doc.modelspace()
    h = artifacts.image_size[1]
    scale = artifacts.scale
    for pts in artifacts.contours:
        points = [(float(x) * scale, float(h - y) * scale) for x, y in pts]
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": "CUT"})

    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def contours_to_dxf(
    contours: list[np.ndarray],
    *,
    scale: float,
    image_height: int,
    output_path: Path,
) -> None:
    artifacts = ConvertArtifacts(
        contours=contours,
        scale=scale,
        width_mm=0,
        height_mm=0,
        image_size=(0, image_height),
        gray=np.zeros((1, 1), np.uint8),
        binary=np.zeros((1, 1), np.uint8),
    )
    data = contours_to_dxf_bytes(artifacts)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)


def preview_png_bytes(artifacts: ConvertArtifacts) -> bytes:
    base = cv2.cvtColor(artifacts.gray, cv2.COLOR_GRAY2BGR)
    overlay = base.copy()
    mask = artifacts.binary > 0
    overlay[mask] = (40, 40, 40)
    for pts in artifacts.contours:
        cv2.polylines(
            overlay, [pts.astype(np.int32)], True, (0, 0, 255), 2, cv2.LINE_AA
        )
    ok, encoded = cv2.imencode(".png", overlay)
    if not ok:
        raise RuntimeError("Failed to encode preview PNG")
    return encoded.tobytes()


def draw_preview(
    gray: np.ndarray,
    binary: np.ndarray,
    contours: list[np.ndarray],
    preview_path: Path,
) -> None:
    artifacts = ConvertArtifacts(
        contours=contours,
        scale=1.0,
        width_mm=0,
        height_mm=0,
        image_size=(gray.shape[1], gray.shape[0]),
        gray=gray,
        binary=binary,
    )
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(preview_png_bytes(artifacts))


def contours_to_svg(artifacts: ConvertArtifacts, *, padding_mm: float = 2.0) -> str:
    """Vector preview of cut paths in mm coordinates (CAD orientation)."""
    w = artifacts.width_mm
    h = artifacts.height_mm
    scale = artifacts.scale
    img_h = artifacts.image_size[1]
    pad = padding_mm
    vb_w = w + pad * 2
    vb_h = h + pad * 2

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb_w:.4f} {vb_h:.4f}" '
        f'width="100%" height="100%" role="img" aria-label="DXF cut path preview">',
        f'<rect x="0" y="0" width="{vb_w:.4f}" height="{vb_h:.4f}" fill="#f4f2ee"/>',
        # subtle mm grid
        f'<g stroke="#d9d4cb" stroke-width="0.05">',
    ]

    step = 10.0 if max(w, h) >= 40 else 5.0
    x = 0.0
    while x <= w + 0.01:
        parts.append(
            f'<line x1="{pad + x:.4f}" y1="{pad:.4f}" '
            f'x2="{pad + x:.4f}" y2="{pad + h:.4f}"/>'
        )
        x += step
    y = 0.0
    while y <= h + 0.01:
        parts.append(
            f'<line x1="{pad:.4f}" y1="{pad + y:.4f}" '
            f'x2="{pad + w:.4f}" y2="{pad + y:.4f}"/>'
        )
        y += step
    parts.append("</g>")

    # Stock outline
    parts.append(
        f'<rect x="{pad:.4f}" y="{pad:.4f}" width="{w:.4f}" height="{h:.4f}" '
        f'fill="none" stroke="#b0a99c" stroke-width="0.15" stroke-dasharray="1 0.6"/>'
    )

    for pts in artifacts.contours:
        # CAD Y up → SVG Y down: flip within stock rect
        cmds: list[str] = []
        for i, (px, py) in enumerate(pts):
            x_mm = float(px) * scale
            y_mm = float(img_h - py) * scale  # CAD coords
            sx = pad + x_mm
            sy = pad + (h - y_mm)  # SVG flip
            cmds.append(("M" if i == 0 else "L") + f"{sx:.4f} {sy:.4f}")
        cmds.append("Z")
        d = " ".join(cmds)
        parts.append(
            f'<path d="{d}" fill="none" stroke="#e93323" stroke-width="0.25" '
            f'stroke-linejoin="round"/>'
        )

    parts.append(
        f'<text x="{pad:.4f}" y="{pad + h + pad * 0.75:.4f}" '
        f'font-family="ui-monospace, monospace" font-size="1.6" fill="#6b6560">'
        f"{w:.1f} × {h:.1f} mm · {len(artifacts.contours)} paths</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)


def convert_image(
    image_path: Path,
    output_path: Path,
    *,
    width_mm: float | None = None,
    mm_per_pixel: float | None = None,
    threshold: int | None = None,
    invert: bool = False,
    blur: int = 3,
    simplify: float = 0.002,
    min_area_mm2: float = 0.5,
    preview_path: Path | None = None,
) -> ConvertResult:
    gray = load_gray(image_path)
    artifacts = process_gray(
        gray,
        width_mm=width_mm,
        mm_per_pixel=mm_per_pixel,
        threshold=threshold,
        invert=invert,
        blur=blur,
        simplify=simplify,
        min_area_mm2=min_area_mm2,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(contours_to_dxf_bytes(artifacts))

    if preview_path is not None:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(preview_png_bytes(artifacts))

    return ConvertResult(
        dxf_path=output_path,
        preview_path=preview_path,
        contour_count=len(artifacts.contours),
        width_mm=artifacts.width_mm,
        height_mm=artifacts.height_mm,
        image_size=artifacts.image_size,
    )
