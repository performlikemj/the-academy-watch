#!/usr/bin/env python3
"""Build the loader's logo layers from the real Academy Watch artwork.

The brand master is the 512px web favicon: the iOS AppIcon-1024 and LaunchBoot images
are generated from it by academy-watch-ios/scripts/generate_brand_assets.swift, and no
vector or larger original exists. Nothing here is traced or redrawn: every visible pixel
of the loader is the master's own shading, resampled once (Lanczos) to 3x of 144 CSS px.

Layers (written into src/lib/academy-watch-logo.js as WebP data URIs):
  art   - the mark itself, greyscale + alpha: white embossed boot and wing, dark lace
          slots and seams, and the thin dark outline the icon draws around every shape
  boot  - alpha mask of the boot (not the wing); painted with the dark detail colour
  shade - the boot's own light-to-dark range as alpha; painted with the club colour
  light - the boot's embossed highlights as alpha; painted white, never animated
Stacked, the boot becomes the icon recoloured: club colour where the icon is white,
lighter on its highlights, darker on its bevels, the detail colour on the lace slots.

The wing / boot split uses the master's own regions: the wing is the two bright pieces
(curled arm + feathers) that the artwork's dark seam already separates from the boot, so
the wing keeps its original white pixels in every phase.

Run with the repo's backend venv (Pillow + numpy):
  ../.loan/bin/python scripts/build-loader-logo.py [--preview out_dir]
"""

import base64
import hashlib
import io
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / 'public/assets/loan_army_assets/favicon-512x512.png'
OUT_JS = ROOT / 'src/lib/academy-watch-logo.js'
OUT_WIDTH = 432  # 3x of the 144 CSS px loader
BRIGHT = 128  # the white boot / wing pieces in the master
SHAPE = 60  # their anti-aliased edges, above the #1A1A1A background
LINE_CLOSE = 4  # output px: the thin dark outline the icon draws around every shape
SLOT_CLOSE = 9  # output px: closes lace slots/seams (<18 px), not the stud gaps (~26 px)
# Boot luminance -> colour ramp: slots/seams 0, bevel ~0.8, body 1; highlights above it.
SHADE_DARK, SHADE_LIGHT = 25, 236
HIGHLIGHT_FROM, HIGHLIGHT_ALPHA = 236, 0.32


def disk(r):
    y, x = np.mgrid[-r : r + 1, -r : r + 1]
    return [(dy, dx) for dy, dx in zip(y.ravel(), x.ravel()) if dy * dy + dx * dx <= r * r + 0.5]


def dilate(mask, r):
    h, w = mask.shape
    padded = np.pad(mask, r)
    out = np.zeros_like(mask)
    for dy, dx in disk(r):
        out |= padded[r + dy : r + dy + h, r + dx : r + dx + w]
    return out


def erode(mask, r):
    return ~dilate(~mask, r)


def flood(owner, passable):
    """Breadth-first fill from labelled pixels through passable pixels."""
    h, w = passable.shape
    owner = owner.copy()
    queue = deque(zip(*np.nonzero(owner)))
    while queue:
        y, x = queue.popleft()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and passable[ny, nx] and not owner[ny, nx]:
                owner[ny, nx] = owner[y, x]
                queue.append((ny, nx))
    return owner


def fill_holes(mask):
    border = np.zeros(mask.shape, np.int8)
    border[[0, -1], :] = ~mask[[0, -1], :]
    border[:, [0, -1]] |= ~mask[:, [0, -1]]
    return flood(border, ~mask) == 0


def components(mask):
    labels = np.zeros(mask.shape, np.int32)
    count = 0
    for y, x in zip(*np.nonzero(mask)):
        if not labels[y, x]:
            count += 1
            seed = np.zeros(mask.shape, np.int32)
            seed[y, x] = count
            labels |= flood(seed, mask & (labels == 0))
    return [labels == i for i in range(1, count + 1)]


def build():
    rgb = np.asarray(Image.open(MASTER).convert('RGB')).astype(np.float32)
    assert rgb.shape == (512, 512, 3), rgb.shape
    luma = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]

    pieces = [piece for piece in components(luma > BRIGHT) if piece.sum() >= 50]
    wing, boot_pieces = [], []
    for piece in pieces:
        ys, xs = np.nonzero(piece)
        (wing if xs.max() < 230 and ys.min() < 200 else boot_pieces).append(piece)
    # The master has a two-piece wing (curled arm + feathers); fail loudly if it changes.
    assert len(wing) == 2 and len(boot_pieces) == 9, (len(wing), len(boot_pieces))
    wing_px, boot_px = np.logical_or.reduce(wing), np.logical_or.reduce(boot_pieces)

    ys, xs = np.nonzero(dilate(wing_px | boot_px, 6))
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    scale = OUT_WIDTH / (box[2] - box[0])
    size = (OUT_WIDTH, round((box[3] - box[1]) * scale))

    def resample(values, method=Image.LANCZOS):
        image = Image.fromarray(values.astype(np.float32), 'F').crop(box).resize(size, method)
        return np.asarray(image)

    # Everything below runs at output resolution, so contours are smooth curves.
    grey = np.clip(resample(luma), 0, 255)
    shapes = grey > SHAPE
    mark = fill_holes(dilate(shapes, LINE_CLOSE) | erode(dilate(shapes, SLOT_CLOSE), SLOT_CLOSE))
    seeds = np.where(resample(wing_px, Image.NEAREST) > 0.5, 1, 0) + np.where(resample(boot_px, Image.NEAREST) > 0.5, 2, 0)
    owner = flood((seeds * shapes).astype(np.int8), mark)
    boot = owner == 2

    def soft(mask):
        """Anti-aliased alpha from a hard mask: supersampled, then box-filtered."""
        big = Image.fromarray((mask * 255).astype(np.uint8)).resize((size[0] * 4, size[1] * 4), Image.BILINEAR)
        big = big.point(lambda v: 255 if v >= 128 else 0)
        return np.asarray(big.resize(size, Image.BOX), dtype=np.float32) / 255

    boot_alpha = soft(boot)
    shade = np.clip((grey - SHADE_DARK) / (SHADE_LIGHT - SHADE_DARK), 0, 1) * boot_alpha
    light = np.clip((grey - HIGHLIGHT_FROM) / (255 - HIGHLIGHT_FROM), 0, 1) * HIGHLIGHT_ALPHA * boot_alpha

    def layer(alpha, values=None):
        values = np.full_like(alpha, 255) if values is None else values
        return Image.fromarray(np.dstack([values, alpha * 255]).round().clip(0, 255).astype(np.uint8), 'LA').convert('RGBA')

    layers = {
        'art': layer(soft(mark), grey),
        # Its edges sit under the dark outline/seams, so half resolution is invisible.
        'boot': layer(boot_alpha).resize((size[0] // 2, size[1] // 2), Image.LANCZOS),
        'shade': layer(shade),
        'light': layer(light),
    }

    # Probe points for tests, as fractions of the logo box: well inside the white wing,
    # the white boot body, and the dark lace slots/seams inside the boot.
    def probes(region, count=12, inset=4):
        ys, xs = np.nonzero(erode(region, inset))
        order = np.argsort(xs * 1000 + ys)
        picks = order[np.linspace(0, len(order) - 1, count).round().astype(int)]
        return [(round((xs[i] + 0.5) / size[0], 4), round((ys[i] + 0.5) / size[1], 4)) for i in picks]

    samples = {
        'wing': probes((owner == 1) & (grey > 245)),
        'body': probes(boot & (grey > 240)),
        'detail': probes(boot & (grey < 40), inset=2),
    }
    return layers, size, samples


ENCODING = {
    'art': {'quality': 90, 'alpha_quality': 100},
    'boot': {'lossless': True},
    'shade': {'quality': 90, 'alpha_quality': 90},
    'light': {'quality': 90, 'alpha_quality': 80},
}


def encode(name, image):
    buffer = io.BytesIO()
    image.save(buffer, 'WEBP', method=6, exact=True, **ENCODING[name])
    return buffer.getvalue()


def main():
    layers, size, samples = build()
    encoded = {name: encode(name, image) for name, image in layers.items()}
    digest = hashlib.sha256(MASTER.read_bytes()).hexdigest()
    lines = [
        '// Generated by scripts/build-loader-logo.py from the brand master',
        '// public/assets/loan_army_assets/favicon-512x512.png (the source of AppIcon-1024).',
        '// Real artwork only: the master resampled once; nothing traced or redrawn.',
        f'export const LOGO_SOURCE_SHA256 = "{digest}"',
        f'export const LOGO_PIXEL_SIZE = Object.freeze({{ width: {size[0]}, height: {size[1]} }})',
        'export const LOGO_LAYERS = Object.freeze({',
    ]
    for name, data in encoded.items():
        lines.append(f"  {name}: 'data:image/webp;base64,{base64.b64encode(data).decode()}',")
    lines.append('})')
    lines.append('// Test probes: [x, y] fractions of the logo box.')
    lines.append('export const LOGO_SAMPLES = Object.freeze({')
    for name, points in samples.items():
        lines.append(f'  {name}: {json.dumps(points, separators=(",", ":"))},')
    lines.append('})')
    OUT_JS.write_text('\n'.join(lines) + '\n')
    for name, data in encoded.items():
        print(f'{name}: {len(data)} bytes ({len(base64.b64encode(data))} base64)')
    print(f'size: {size[0]}x{size[1]} px; wrote {OUT_JS.relative_to(ROOT)}')
    if '--preview' in sys.argv:
        out = Path(sys.argv[sys.argv.index('--preview') + 1])
        out.mkdir(parents=True, exist_ok=True)
        for name, image in layers.items():
            image.save(out / f'{name}.png')


if __name__ == '__main__':
    main()
