"""核心回归：像素和边界正确，以及失败时保护已有文件。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from main import count_parts, ranges, split_image


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)
        self.source = self.base / "input.png"
        self.original = Image.new("RGB", (17, 91))
        self.original.putdata([(x, y, (x + y) % 256) for y in range(91) for x in range(17)])
        self.addCleanup(self.original.close)
        self.original.save(self.source)

    def test_ranges_cover_every_row_without_redundant_tail(self):
        for height in (1, 2, 39, 40, 41, 80, 91, 8000):
            for size in (1, 2, 40, 4000):
                for overlap in sorted({0, size // 2, size - 1}):
                    with self.subTest(height=height, size=size, overlap=overlap):
                        parts = list(ranges(height, size, overlap))
                        self.assertEqual(count_parts(height, size, overlap), len(parts))
                        self.assertEqual(parts[0][0], 0)
                        self.assertEqual(parts[-1][1], height)
                        for top, bottom in parts:
                            self.assertLess(top, bottom)
                            self.assertLessEqual(bottom - top, size)
                        for previous, current in zip(parts, parts[1:]):
                            self.assertLess(previous[1], height)
                            self.assertEqual(previous[1] - current[0], overlap)
        self.assertEqual(list(ranges(8000, 4000, 0)), [(0, 4000), (4000, 8000)])
        self.assertEqual(list(ranges(8000, 4000, 100)), [(0, 4000), (3900, 7900), (7800, 8000)])

    def test_invalid_ranges(self):
        for height, size, overlap in ((0, 40, 0), (-1, 40, 0), (200, 0, 0),
                                      (200, -1, 0), (200, 100, 100), (200, 100, -1)):
            with self.subTest(height=height, size=size, overlap=overlap):
                with self.assertRaises(ValueError):
                    list(ranges(height, size, overlap))
                with self.assertRaises(ValueError):
                    count_parts(height, size, overlap)

    def test_exact_pixels_and_progress(self):
        seen = []
        self.assertEqual(split_image(self.source, self.base, 40, 10, "测试", 3,
                                     progress=lambda i, n: seen.append((i, n))), 3)
        self.assertEqual(seen, [(1, 3), (2, 3), (3, 3)])
        for i, (top, bottom) in enumerate(ranges(91, 40, 10), 1):
            with Image.open(self.base / f"测试_{i:03d}.png") as part:
                self.assertEqual(part.size, (17, bottom - top))
                with self.original.crop((0, top, 17, bottom)) as expected:
                    self.assertEqual(part.tobytes(), expected.tobytes())

    def test_transparent_and_palette_pixels_survive(self):
        for mode in ("RGBA", "P", "L"):
            with self.subTest(mode=mode):
                with Image.new(mode, (9, 23)) as original:
                    if mode == "RGBA":
                        original.putdata([(x, y, x + y, y * 10) for y in range(23) for x in range(9)])
                    elif mode == "P":
                        original.putpalette([channel for value in range(256) for channel in (value, 255 - value, value)])
                        original.putdata([(x + y) % 3 for y in range(23) for x in range(9)])
                        original.info["transparency"] = 0
                    else:
                        original.putdata([(x + y) % 256 for y in range(23) for x in range(9)])
                    source = self.base / f"{mode}.png"
                    original.save(source)
                    split_image(source, self.base, 10, 2, mode, 2)
                    for i, (top, bottom) in enumerate(ranges(23, 10, 2), 1):
                        with Image.open(self.base / f"{mode}_{i:02d}.png") as part:
                            with original.crop((0, top, 9, bottom)) as expected:
                                self.assertEqual(part.convert("RGBA").tobytes(), expected.convert("RGBA").tobytes())

    def test_supported_formats_and_same_format_output(self):
        for suffix, image_format in (("png", "PNG"), ("jpg", "JPEG"), ("jpeg", "JPEG"), ("webp", "WEBP")):
            with self.subTest(suffix=suffix):
                source = self.base / f"format.{suffix}"
                self.original.save(source)
                self.assertEqual(split_image(source, self.base, 100, 0, suffix, 2, True), 1)
                extension = "jpg" if image_format == "JPEG" else suffix
                with Image.open(self.base / f"{suffix}_01.{extension}") as part:
                    self.assertEqual(part.format, image_format)
                    self.assertEqual(part.size, self.original.size)
                split_image(source, self.base, 100, 0, suffix + "png", 2)
                with Image.open(source) as decoded, Image.open(self.base / f"{suffix}png_01.png") as part:
                    self.assertEqual(part.tobytes(), decoded.tobytes())

    def test_metadata_keeps_icc_without_exif_and_preserves_raw_direction(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[305] = "private metadata marker"
        profile = b"ICC profile regression marker"
        for suffix in ("png", "jpg", "webp"):
            with self.subTest(suffix=suffix):
                source = self.base / f"metadata.{suffix}"
                self.original.save(source, exif=exif, icc_profile=profile)
                split_image(source, self.base, 40, 0, "metadata" + suffix, 3)
                with Image.open(self.base / f"metadata{suffix}_001.png") as part, Image.open(source) as decoded:
                    self.assertEqual(part.size, (17, 40))
                    self.assertEqual(part.info.get("icc_profile"), profile)
                    self.assertFalse(part.getexif())
                    with decoded.crop((0, 0, 17, 40)) as expected:
                        self.assertEqual(part.tobytes(), expected.tobytes())

    def test_late_conflict_is_detected_before_writing_any_slice(self):
        existing = self.base / "part_003.png"
        existing.write_bytes(b"do not replace this file")
        with self.assertRaises(FileExistsError):
            split_image(self.source, self.base, 40, 10, "part", 3)
        self.assertEqual(existing.read_bytes(), b"do not replace this file")
        self.assertFalse((self.base / "part_001.png").exists())
        self.assertFalse((self.base / "part_002.png").exists())

    def test_source_cannot_be_overwritten(self):
        source = self.base / "input_001.png"
        self.original.save(source)
        before = source.read_bytes()
        with self.assertRaises(FileExistsError):
            split_image(source, self.base, 40, 10, "input", 3)
        self.assertEqual(source.read_bytes(), before)

    def test_file_created_after_preflight_is_not_overwritten(self):
        original_open = Path.open
        contested = self.base / "race_002.png"

        def competing_open(path, mode="r", *args, **kwargs):
            if path == contested and mode == "xb":
                with original_open(path, "wb") as stream:
                    stream.write(b"created by another process")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", competing_open):
            with self.assertRaises(FileExistsError):
                split_image(self.source, self.base, 40, 10, "race", 3)
        self.assertEqual(contested.read_bytes(), b"created by another process")
        self.assertTrue((self.base / "race_001.png").is_file())
        self.assertFalse((self.base / "race_003.png").exists())

    def test_failed_save_removes_only_incomplete_slice(self):
        original_save = Image.Image.save
        seen = []

        def interrupted_save(im, destination, *args, **kwargs):
            if str(getattr(destination, "name", "")).endswith("failure_002.png"):
                destination.write(b"incomplete encoded image")
                raise OSError("simulated full disk")
            return original_save(im, destination, *args, **kwargs)

        with patch.object(Image.Image, "save", interrupted_save):
            with self.assertRaisesRegex(OSError, "simulated full disk"):
                split_image(self.source, self.base, 40, 10, "failure", 3,
                            progress=lambda i, n: seen.append((i, n)))
        self.assertEqual(seen, [(1, 3)])
        with Image.open(self.base / "failure_001.png") as saved:
            self.assertEqual(saved.size, (17, 40))
        self.assertFalse((self.base / "failure_002.png").exists())
        self.assertFalse((self.base / "failure_003.png").exists())

    def test_rejects_invalid_settings_and_unsupported_images(self):
        cases = [
            (self.base / "missing.png", self.base, 40, 0, "part", 3),
            (self.source, self.base / "missing", 40, 0, "part", 3),
            (self.source, self.base, 0, 0, "part", 3),
            (self.source, self.base, 40, 40, "part", 3),
            (self.source, self.base, 40, -1, "part", 3),
        ]
        cases += [(self.source, self.base, 40, 0, prefix, 3)
                  for prefix in ("", "bad/name", "bad\\name", "bad?name", "bad\x00name", "name.", "name ", "x" * 101)]
        cases += [(self.source, self.base, 40, 0, "part", digits) for digits in (0, 11)]
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    split_image(*args)
        self.original.save(self.base / "unsupported.bmp")
        with self.assertRaises(ValueError):
            split_image(self.base / "unsupported.bmp", self.base, 40, 0, "bmp", 3)
        self.assertFalse(list(self.base.glob("part_*.png")))

    def test_rejects_animation_and_corrupt_input(self):
        source = self.base / "animated.webp"
        with Image.new("RGB", (17, 91), "red") as second:
            self.original.save(source, save_all=True, append_images=[second], duration=80, loop=0)
        with self.assertRaisesRegex(ValueError, "静态"):
            split_image(source, self.base, 40, 0, "animated", 3)
        source = self.base / "corrupt.png"
        source.write_bytes(b"this is not a PNG image")
        with self.assertRaises(OSError):
            split_image(source, self.base, 40, 0, "corrupt", 3)
        self.assertFalse(list(self.base.glob("animated_*.png")))
        self.assertFalse(list(self.base.glob("corrupt_*.png")))

    def test_unwritable_output(self):
        original_open = Path.open

        def denied_open(path, mode="r", *args, **kwargs):
            if mode == "xb":
                raise PermissionError("不可写")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", denied_open):
            with self.assertRaises(PermissionError):
                split_image(self.source, self.base, 40, 0, "denied", 3)
        self.assertFalse(list(self.base.glob("denied_*.png")))


if __name__ == "__main__":
    unittest.main()
