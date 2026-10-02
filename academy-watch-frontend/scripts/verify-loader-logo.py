"""Compare browser-rendered 600px SVG to the unchanged iOS launch brand ink.

Usage: .loan/bin/python scripts/verify-loader-logo.py /path/to/shots/N6
The browser spec produces logo-600.png without rescaling/alignment optimisation.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / 'academy-watch-ios/AcademyWatch/Assets.xcassets/LaunchBoot.imageset/LaunchBoot@3x.png'
output = Path(sys.argv[1]).expanduser()
reference = np.array(Image.open(source).convert('RGBA'))
rendered = np.array(Image.open(output / 'logo-600.png').convert('RGBA'))
assert reference.shape == rendered.shape == (600, 600, 4)
def white_ink(image):
    return (image[:, :, 3] >= 128) & (image[:, :, 0] >= 128)
a, b = white_ink(reference), white_ink(rendered)
intersection, union = int((a & b).sum()), int((a | b).sum())
diff = a ^ b
metrics = {
    'source': str(source.relative_to(ROOT)),
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'render_size': [600, 600],
    'mask': 'alpha >=128 AND red >=128 (white logo ink, including all original seams)',
    'alignment': 'original 600x600 coordinates; no fit, warp or registration',
    'intersection_pixels': intersection, 'union_pixels': union,
    'iou': intersection / union,
    'different_mask_pixels': int(diff.sum()),
    'mask_diff_percent_of_canvas': 100 * int(diff.sum()) / a.size,
    'mask_diff_percent_of_union': 100 * int(diff.sum()) / union,
}
overlay = np.full((600, 600, 3), 20, dtype='uint8')
overlay[a & ~b] = [0, 230, 255]
overlay[b & ~a] = [255, 0, 190]
overlay[a & b] = [243, 240, 232]
Image.fromarray(overlay).save(output / 'logo-overlay-600.png')
diff_image = np.full((600, 600, 3), 20, dtype='uint8')
diff_image[diff] = [255, 90, 70]
Image.fromarray(diff_image).save(output / 'logo-diff-600.png')
shutil.copyfile(source, output / 'LaunchBoot-reference-600.png')
(output / 'match.json').write_text(json.dumps(metrics, indent=2) + '\n')
print(json.dumps(metrics, indent=2))
