# img-to-dxf

Silhouette image → DXF polylines for **laser cutting**.

Designed for filled black shapes on a light (or transparent) background — logos, icons, cut silhouettes — not photographs.

## Setup

```bash
# requires uv (https://docs.astral.sh/uv/)
cd img-to-dxf
uv sync
```

## Web UI

```bash
uv run img-to-dxf-web
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765) — upload an image, tweak parameters, preview cut paths, download DXF.

## CLI

```bash
uv run img-to-dxf input.png --width-mm 80
```

Writes `input.dxf` and `input_preview.png` (red cut paths overlaid).

### Options

| Flag | Meaning |
|------|---------|
| `-o out.dxf` | Output path |
| `--width-mm 100` | Target width in mm (default: 100) |
| `--mm-per-pixel 0.1` | Scale instead of width |
| `--threshold 127` | Manual threshold (default: Otsu auto) |
| `--invert` | Light shape on dark background |
| `--blur 3` | Gaussian blur kernel (0 = off) |
| `--simplify 0.002` | Polyline simplification ratio |
| `--min-area 0.5` | Drop tiny contours (mm²) |
| `--preview path.png` | Custom preview path |
| `--no-preview` | Skip preview |

### Examples

```bash
# 50 mm wide logo, auto threshold
uv run img-to-dxf logo.png --width-mm 50

# White icon on black
uv run img-to-dxf icon.png --width-mm 40 --invert

# More detail (less simplification)
uv run img-to-dxf shape.png --width-mm 100 --simplify 0.0005
```

## Output

- DXF R2010, units = mm (`$INSUNITS`)
- Closed `LWPOLYLINE` entities on layer `CUT`
- Image Y flipped so orientation matches CAD

Open the DXF in LightBurn, LaserGRBL, LibreCAD, or similar. Check the preview PNG before cutting.

## Tips for good cuts

1. Prefer **filled silhouettes**, not thin outline strokes.
2. Use PNG with transparent background when possible.
3. Always review `*_preview.png` before sending to the laser.
4. Raise `--simplify` if the machine chokes on too many nodes.
5. Raise `--min-area` to drop dust / speckles.

## License

MIT
