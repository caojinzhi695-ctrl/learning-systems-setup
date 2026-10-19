import io
import unittest
from unittest.mock import patch
import pymupdf
from PIL import Image
from deeptutor.services.summary_notes.import_material import extract_material

class OcrImportTests(unittest.TestCase):
    def test_mixed_pdf_keeps_native_and_image_text(self):
        image = io.BytesIO()
        Image.new("RGB", (300, 100), "white").save(image, format="PNG")
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((40, 40), "Native source")
            page.insert_image(pymupdf.Rect(40, 80, 340, 180), stream=image.getvalue())
            with patch("deeptutor.services.summary_notes.ocr.image_text", return_value="图片中的中文") as ocr:
                text = extract_material("mixed.pdf", doc.tobytes())
            self.assertIn("Native source", text)
            self.assertIn("图片中的中文", text)
            self.assertIn("OCR，需核对", text)
            ocr.assert_called_once()

    def test_long_pdf_is_cropped_before_resize(self):
        image = io.BytesIO()
        Image.new("RGB", (200, 4000), "white").save(image, format="PNG")
        sizes = []
        def recognise(image):
            sizes.append(image.size)
            return f"第{len(sizes)}段完整内容"
        with pymupdf.open() as doc:
            page = doc.new_page(width=200, height=4000)
            page.insert_image(page.rect, stream=image.getvalue())
            with patch("deeptutor.services.summary_notes.ocr.image_text", side_effect=recognise):
                text = extract_material("long.pdf", doc.tobytes())
        self.assertGreater(len(sizes), 1)
        self.assertTrue(all(width >= 1000 and height <= 1900 for width, height in sizes))
        self.assertIn("第1段完整内容", text)
        self.assertIn(f"第{len(sizes)}段完整内容", text)

    def test_scan_requires_usable_text(self):
        with pymupdf.open() as doc:
            doc.new_page()
            with patch("deeptutor.services.summary_notes.ocr.image_text", return_value=""):
                with self.assertRaisesRegex(ValueError, "未识别到"):
                    extract_material("empty.pdf", doc.tobytes())

    def test_direct_image_ocr(self):
        image = io.BytesIO()
        Image.new("RGB", (300, 100), "white").save(image, format="PNG")
        with patch("deeptutor.services.summary_notes.ocr.image_text", return_value="图片文字"):
            self.assertIn("图片文字", extract_material("photo.png", image.getvalue()))


class OcrFallbackTests(unittest.TestCase):
    def test_no_text_attempts_are_bounded(self):
        from types import SimpleNamespace
        from deeptutor.services.summary_notes.ocr import image_text
        with patch("deeptutor.services.summary_notes.ocr._engine") as factory:
            factory.return_value.return_value = SimpleNamespace(txts=None)
            self.assertEqual(image_text(Image.new("RGB", (400, 300), "white")), "")
            self.assertEqual(factory.return_value.call_count, 5)

    def test_large_empty_detection_uses_tiles(self):
        from types import SimpleNamespace
        from deeptutor.services.summary_notes.ocr import image_text
        with patch("deeptutor.services.summary_notes.ocr._engine") as factory:
            factory.return_value.side_effect = [SimpleNamespace(txts=None)] + [SimpleNamespace(txts=("小字识别",))] * 4
            text = image_text(Image.new("RGB", (2000, 2000), "white"))
            self.assertIn("小字识别", text)
            self.assertEqual(factory.return_value.call_count, 5)
