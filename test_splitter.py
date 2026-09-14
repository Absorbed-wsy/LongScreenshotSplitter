import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from main import ranges, split_image


class SplitTests(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(list(ranges(8000, 4000, 0)), [(0, 4000), (4000, 8000)])
        self.assertEqual(list(ranges(8000, 4000, 100)), [(0, 4000), (3900, 7900), (7800, 8000)])
        self.assertEqual(list(ranges(100, 4000, 100)), [(0, 100)])
        for size, overlap in [(0, 0), (100, 100), (100, -1)]:
            with self.assertRaises(ValueError):
                list(ranges(200, size, overlap))

    def test_pixels_formats_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            original = Image.new('RGB', (17, 91))
            original.putdata([(x, y, (x+y) % 256) for y in range(91) for x in range(17)])
            source = base / 'input.png'
            original.save(source)
            seen = []
            self.assertEqual(split_image(source, base, 40, 10, '测试', 3, progress=lambda i, n: seen.append((i,n))), 3)
            self.assertEqual(seen[-1], (3, 3))
            for i, (top, bottom) in enumerate(ranges(91, 40, 10), 1):
                with Image.open(base / f'测试_{i:03d}.png') as part:
                    self.assertEqual(part.size, (17, bottom-top))
                    self.assertEqual(part.tobytes(), original.crop((0, top, 17, bottom)).tobytes())
            with self.assertRaises(FileExistsError):
                split_image(source, base, 40, 10, '测试', 3)
            for suffix in ('jpg', 'jpeg', 'webp'):
                src = base / f'input.{suffix}'
                original.save(src)
                self.assertEqual(split_image(src, base, 100, 0, suffix, 2, True), 1)
                self.assertEqual(split_image(src, base, 100, 0, suffix+'png', 2), 1)
            for args in [(base/'missing.png', base, 40, 0, 'a', 3), (source, base/'missing', 40, 0, 'a', 3), (source, base, 40, 0, 'bad/name', 3), (source, base, 40, 0, 'a', 0)]:
                with self.assertRaises(ValueError):
                    split_image(*args)
            original.save(base/'bad.bmp')
            with self.assertRaises(ValueError):
                split_image(base/'bad.bmp', base, 40, 0, 'bmp', 3)
            with patch.object(Path, 'open', side_effect=PermissionError('不可写')):
                with self.assertRaises(PermissionError):
                    split_image(source, base, 40, 0, 'denied', 3)
            original.close()


if __name__ == '__main__':
    unittest.main()
