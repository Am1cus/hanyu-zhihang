"""Crop actual browser captures without repainting or changing screenshot pixels."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/4C/.build/presentation/screens"
OUT.mkdir(parents=True, exist_ok=True)
regions = {
    "map": ("preview-evaluated.png", (585, 261, 1368, 696)),
    "budget": ("budget-minus20.png", (564, 513, 1389, 893)),
    "runtime": ("manual-obstacle-reroute.png", (285, 454, 1029, 889)),
    "result": ("archive-result.png", (586, 312, 1370, 385)),
    "events": ("archive-events.png", (565, 414, 1389, 584)),
}
for name, (source, box) in regions.items():
    with Image.open(ROOT / "output/playwright/4C" / source) as image:
        if box[2] > image.width or box[3] > image.height:
            raise ValueError(f"Screenshot geometry changed: {source}")
        image.crop(box).save(OUT / f"{name}.png")
print(f"Cropped {len(regions)} actual screenshot regions to {OUT}")
