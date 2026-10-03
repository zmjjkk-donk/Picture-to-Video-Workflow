"""Small copies for local browser upload checks; never alter original assets."""
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[2]
target = Path(__file__).resolve().parent / "browser-inputs"
target.mkdir(exist_ok=True)
for name in ("model", "clothes_1", "clothes_2", "clothes_3"):
    with Image.open(root / "data" / "text_picture" / "2" / f"{name}.png") as source:
        image = source.convert("RGB")
        image.thumbnail((360, 600))
        image.save(target / f"{name}.jpg", quality=85)
        print(name, image.size, (target / f"{name}.jpg").stat().st_size)
