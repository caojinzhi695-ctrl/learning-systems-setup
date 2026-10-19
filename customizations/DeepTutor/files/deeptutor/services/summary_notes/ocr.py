"""Local CPU OCR; no document data is transmitted to a model service."""
import threading
from functools import lru_cache

_LOCK = threading.Lock()

@lru_cache(maxsize=1)
def _engine():
    from rapidocr import RapidOCR
    return RapidOCR(params={
        "Global.log_level": "error",
        "EngineConfig.onnxruntime.intra_op_num_threads": 2,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    })

def image_text(image) -> str:
    from PIL import Image
    import io
    if isinstance(image, bytes):
        image = Image.open(io.BytesIO(image))
    if image.width * image.height > 20_000_000:
        raise ValueError("图片像素过大，请缩小到2000万像素以内。")
    from PIL import ImageOps
    image = ImageOps.exif_transpose(image).convert("RGB")
    with _LOCK:
        engine = _engine()
        def recognise(candidate):
            result = engine(candidate)
            return "\n".join(result.txts or ()).strip()
        text = recognise(image)
        if text:
            return text
        # Small text can disappear when a whole PDF page is resized by the detector.
        # Limit tile work; these are local OCR passes, never repeated model/API requests.
        if max(image.size) > 1600:
            tiles = []
            for y in range(0, image.height, 1200):
                for x in range(0, image.width, 1200):
                    tiles.append((x, y, min(x + 1400, image.width), min(y + 1400, image.height)))
            if len(tiles) > 12:
                raise ValueError("图片需分块识别但区域过多，请裁剪或分成较小图片后导入。")
            lines = []
            seen = set()
            for box in tiles:
                for line in recognise(image.crop(box)).splitlines():
                    if line not in seen:
                        seen.add(line)
                        lines.append(line)
            if lines:
                return "\n".join(lines)
        enhanced = ImageOps.autocontrast(ImageOps.grayscale(image)).convert("RGB")
        for candidate in [enhanced, ImageOps.invert(enhanced), enhanced.rotate(90, expand=True), enhanced.rotate(270, expand=True)]:
            text = recognise(candidate)
            if text:
                return text
    return ""
