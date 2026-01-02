# utils/image_proc.py
import os
import hashlib
from PIL import Image
from io import BytesIO
import logging

logger = logging.getLogger(__name__)


def md5_bytes(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def process_image(image_bytes: bytes, max_mb: int = 5) -> tuple[str, str]:
    """
    Save to /tmp/<md5>.jpg, compress if needed, return (path, md5).
    """
    md5_hash = md5_bytes(image_bytes)
    temp_dir = "/tmp"
    os.makedirs(temp_dir, exist_ok=True)
    temp_filename = os.path.join(temp_dir, f"{md5_hash}.jpg")

    img = Image.open(BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")

    quality = 95
    img.save(temp_filename, "JPEG", quality=quality, optimize=True)

    # compress loop
    while os.path.getsize(temp_filename) > max_mb * 1024 * 1024 and quality > 20:
        quality -= 10
        img.save(temp_filename, "JPEG", quality=quality, optimize=True)

    # final fallback: resize
    if os.path.getsize(temp_filename) > max_mb * 1024 * 1024:
        w, h = img.size
        new_w = int(w * 0.8)
        new_h = int(h * 0.8)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        img.save(temp_filename, "JPEG", quality=85, optimize=True)

    logger.info(
        "Saved processed image %s size=%d bytes",
        temp_filename,
        os.path.getsize(temp_filename),
    )
    return temp_filename, md5_hash
