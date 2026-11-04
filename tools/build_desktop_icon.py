"""Render the original Sentinel camera icon; small sizes use a simplified silhouette."""
import io
import struct
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 24, 32, 48, 256)


def draw_camera(size):
    # Draw on a 256-unit grid, with deliberate detail changes for the smallest frames.
    image = Image.new("RGBA", (256, 256))
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 204, 237, 235), fill=(17, 34, 70, 70))
    draw.rounded_rectangle((54, 47, 131, 106), 16, fill="#18375d", outline="#112748", width=7)
    draw.rounded_rectangle((15, 70, 242, 211), 27, fill="#143963", outline="#102c54", width=8)
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).rounded_rectangle((23, 78, 234, 202), 19, fill=255)
    gradient = Image.new("RGBA", image.size)
    gd = ImageDraw.Draw(gradient)
    for y in range(78, 203):
        t = (y - 78) / 124
        gd.line((23, y, 234, y), fill=(int(123 - 95*t), int(190 - 97*t), int(247 - 66*t), 255))
    image.paste(gradient, (0, 0), mask)
    draw.rounded_rectangle((26, 82, 231, 199), 18, outline="#b5e1ff", width=4)
    draw.ellipse((68, 78, 188, 198), fill="#172743", outline="#e7f1fb", width=7)
    draw.ellipse((81, 91, 175, 185), fill="#234878", outline="#85a7c6", width=5)
    draw.ellipse((92, 102, 164, 174), fill="#0c2148", outline="#48a1d8", width=5)
    draw.ellipse((104, 114, 150, 160), fill="#135a94")
    draw.ellipse((105, 113, 126, 132), fill="#c2f2ff")
    if size >= 24:
        draw.ellipse((136, 146, 150, 159), fill="#6dbaff")
        draw.rounded_rectangle((191, 92, 219, 109), 6, fill="#e5f6ff", outline="#246090", width=3)
        draw.ellipse((195, 124, 214, 143), fill="#9ce784", outline="#234f52", width=4)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def build(path):
    frames = []
    for size in SIZES:
        stream = io.BytesIO()
        draw_camera(size).save(stream, format="PNG")
        frames.append((size, stream.getvalue()))
    offset = 6 + 16 * len(frames)
    directory = []
    for size, image in frames:
        edge = 0 if size == 256 else size
        directory.append(struct.pack("<BBBBHHII", edge, edge, 0, 0, 1, 32, len(image), offset))
        offset += len(image)
    path.write_bytes(struct.pack("<HHH", 0, 1, len(frames)) + b"".join(directory) +
                     b"".join(image for _, image in frames))


if __name__ == "__main__":
    build(ROOT / "assets/sentinel-camera.ico")
