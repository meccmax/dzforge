"""
Map tiler — slices a square map render into a Leaflet XYZ tile pyramid that lines
up with DZ Forge's world coordinates.

  build_tiles(src, out, world) -> writes out/{z}/{x}/{y}.jpg (y=0 at top); the pyramid
  is sized so the top zoom equals `world` metres (1 px = 1 m), matching the map view.

Callable from the app (POST /api/gentiles) or run standalone: python tiler.py
"""
import os
import sys
import time
import math
import shutil
from PIL import Image
import config

# Disable the decompression-bomb guard; these are trusted local map renders.
Image.MAX_IMAGE_PIXELS = None
TILE = 256
JPEG_QUALITY = 80


def build_tiles(src, out, world, tile=TILE, quality=JPEG_QUALITY, log=lambda *a: None):
    """Slice `src` into a tile pyramid under `out`, sized to `world` metres. Returns stats."""
    img = Image.open(src).convert("RGB")
    w, h = img.size
    max_zoom = max(0, round(math.log2(max(1, int(world)) / tile)))
    native = tile * (2 ** max_zoom)                       # top-level px = world metres
    base = img if (w == native and h == native) else img.resize((native, native), Image.Resampling.LANCZOS)
    if os.path.isdir(out):
        shutil.rmtree(out, ignore_errors=True)            # clear stale tiles (e.g. a previous map)
    total = 0
    for z in range(max_zoom + 1):
        side = tile * (2 ** z)
        ntiles = 2 ** z
        level = base if side == native else base.resize((side, side), Image.Resampling.LANCZOS)
        for tx in range(ntiles):
            col = os.path.join(out, str(z), str(tx))
            os.makedirs(col, exist_ok=True)
            for ty in range(ntiles):
                level.crop((tx * tile, ty * tile, tx * tile + tile, ty * tile + tile)).save(
                    os.path.join(col, f"{ty}.jpg"), "JPEG", quality=quality)
                total += 1
        if level is not base:
            level.close()
        log(f"zoom {z}: {ntiles}x{ntiles} = {ntiles * ntiles} tiles")
    if base is not img:
        base.close()
    img.close()
    return {"tiles": total, "maxZoom": max_zoom, "source": [w, h], "world": int(world)}


def main():
    cfg = config.load()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiles")
    if not cfg.get("mapImage"):
        print("No mapImage set in dzforge.config.json — set one (or use the in-app setup).", flush=True)
        return 1
    t0 = time.time()
    print(f"Tiling {cfg['mapImage']} (world {cfg['worldSize']}) ...", flush=True)
    r = build_tiles(cfg["mapImage"], out, cfg["worldSize"], log=lambda m: print("  " + m, flush=True))
    print(f"DONE: {r['tiles']} tiles (max zoom {r['maxZoom']}) in {time.time() - t0:.1f}s -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
