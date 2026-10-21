"""Build the kiosk's fish illustrations from the client's master artwork.

The masters in ``fishes/`` are 8185 x 5787 px RGBA files of ~5-11 MB each. The
screen draws them inside an 823 x 313 px box, so this script trims each master to
its ink, scales the long edge to 1600 px (~2x for a 1080-wide kiosk) and writes a
few hundred KB per fish.

    pip install pillow            # desktop only; the Pi does not need Pillow
    python tools/build_fish_assets.py
    python tools/build_fish_assets.py --src "D:\\项目\\新加坡博物馆2\\fishes"

Why the alpha threshold: the masters carry a sprinkle of near-transparent
speckle across the whole canvas. The paddlefish master measures 6933 x 3688 at
alpha > 8 but 6932 x 1414 at alpha > 64, i.e. a naive trim would shrink the fish
to a third of its size on screen.
"""

import argparse
import os

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = os.path.normpath(os.path.join(HERE, "..", "fishes"))
DEFAULT_OUT = os.path.join(HERE, "static", "images", "fish")
LONG_EDGE = 1600
ALPHA_THRESHOLD = 64

# The four species the weighing scale needs, and the master each comes from.
FISH = [
    ("goonch", "Goonch.png"),
    ("american-paddlefish", "American Paddlefish.png"),
    ("arapaima", "Pirarucu.png"),          # arapaima = pirarucu
    ("giant-barb", "Giant Barb.png"),
]


def ink_box(im, threshold=ALPHA_THRESHOLD):
    """Bounding box of the pixels whose alpha clears `threshold`."""
    mask = im.getchannel("A").point(lambda v: 255 if v > threshold else 0)
    box = mask.getbbox()
    if box is None:
        raise SystemExit("artwork is fully transparent")
    return box


def build(src_dir, out_dir, long_edge=LONG_EDGE):
    os.makedirs(out_dir, exist_ok=True)
    for key, filename in FISH:
        src = os.path.join(src_dir, filename)
        if not os.path.isfile(src):
            raise SystemExit("missing master: " + src)
        im = Image.open(src).convert("RGBA")
        trimmed = im.crop(ink_box(im))

        scale = long_edge / max(trimmed.size)
        size = (max(1, round(trimmed.width * scale)),
                max(1, round(trimmed.height * scale)))
        resized = trimmed.resize(size, Image.LANCZOS)

        dst = os.path.join(out_dir, key + ".png")
        resized.save(dst, optimize=True)
        print("%-20s %-24s %5dx%-5d -> %4dx%-4d  %6.1f KB  aspect %.2f"
              % (key, filename, im.width, im.height, resized.width, resized.height,
                 os.path.getsize(dst) / 1024, resized.width / resized.height))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default=DEFAULT_SRC, help="folder with the masters")
    parser.add_argument("--out", default=DEFAULT_OUT, help="output folder")
    args = parser.parse_args()
    build(args.src, args.out)


if __name__ == "__main__":
    main()
