"""FastAPI web UI for image → DXF conversion."""

from __future__ import annotations

import base64
import re
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from img_to_dxf.convert import (
    contours_to_dxf_bytes,
    contours_to_svg,
    load_gray_from_bytes,
    preview_png_bytes,
    process_gray,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
JOB_TTL_SEC = 60 * 30
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

app = FastAPI(title="img-to-dxf", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_jobs: dict[str, dict] = {}


def _purge_jobs() -> None:
    now = time.time()
    expired = [jid for jid, job in _jobs.items() if now - job["created"] > JOB_TTL_SEC]
    for jid in expired:
        path: Path = _jobs[jid]["path"]
        path.unlink(missing_ok=True)
        _jobs.pop(jid, None)


def _safe_stem(name: str | None) -> str:
    stem = Path(name or "cut").stem
    stem = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("_")
    return (stem or "cut")[:80]


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


def _parse_optional_int(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


def _parse_bool(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@app.post("/api/convert")
async def convert(
    file: UploadFile = File(...),
    width_mm: float = Form(100.0),
    threshold: str | None = Form(None),
    invert: str = Form("false"),
    blur: int = Form(3),
    simplify: float = Form(0.002),
    min_area: float = Form(0.5),
) -> dict:
    _purge_jobs()

    if width_mm <= 0:
        raise HTTPException(400, "width_mm must be positive")
    if blur < 0:
        raise HTTPException(400, "blur must be >= 0")
    if simplify < 0:
        raise HTTPException(400, "simplify must be >= 0")
    if min_area < 0:
        raise HTTPException(400, "min_area must be >= 0")

    try:
        threshold_val = _parse_optional_int(threshold)
    except ValueError as exc:
        raise HTTPException(400, "threshold must be an integer") from exc
    if threshold_val is not None and not (0 <= threshold_val <= 255):
        raise HTTPException(400, "threshold must be 0–255")
    invert_val = _parse_bool(invert)

    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 15 MB)")

    try:
        gray = load_gray_from_bytes(data)
        artifacts = process_gray(
            gray,
            width_mm=width_mm,
            threshold=threshold_val,
            invert=invert_val,
            blur=blur,
            simplify=simplify,
            min_area_mm2=min_area,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(422, str(exc)) from exc

    dxf_bytes = contours_to_dxf_bytes(artifacts)
    preview = preview_png_bytes(artifacts)
    svg = contours_to_svg(artifacts)

    job_id = uuid.uuid4().hex
    stem = _safe_stem(file.filename)
    tmp = Path(tempfile.gettempdir()) / f"img2dxf_{job_id}.dxf"
    tmp.write_bytes(dxf_bytes)
    _jobs[job_id] = {
        "path": tmp,
        "filename": f"{stem}.dxf",
        "created": time.time(),
    }

    return {
        "job_id": job_id,
        "filename": f"{stem}.dxf",
        "contour_count": len(artifacts.contours),
        "width_mm": round(artifacts.width_mm, 3),
        "height_mm": round(artifacts.height_mm, 3),
        "image_size": {
            "width": artifacts.image_size[0],
            "height": artifacts.image_size[1],
        },
        "preview_png": base64.b64encode(preview).decode("ascii"),
        "preview_svg": svg,
        "download_url": f"/api/download/{job_id}",
    }


@app.get("/api/download/{job_id}")
def download(job_id: str) -> FileResponse:
    _purge_jobs()
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job expired or not found — convert again")
    path: Path = job["path"]
    if not path.exists():
        _jobs.pop(job_id, None)
        raise HTTPException(404, "File missing — convert again")
    return FileResponse(
        path,
        media_type="application/dxf",
        filename=job["filename"],
    )


def main() -> None:
    import uvicorn

    uvicorn.run("img_to_dxf.web:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
