"""验证打包后的 Tk、Pillow 编码器及后台切分，不修改用户图片。"""
import json
import tempfile
import time
import traceback
from pathlib import Path
import tkinter as tk
from PIL import Image


def run(app_class, report):
    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        app = app_class(root)
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for suffix in ('png', 'jpg', 'jpeg', 'webp'):
                source = base / ('input.' + suffix)
                with Image.new('RGB', (31, 251)) as original:
                    original.putdata([(x, y, (x + y) % 256) for y in range(251) for x in range(31)])
                    original.save(source)
                app.source.set(str(source))
                app.output.set(folder)
                app.prefix.set(suffix)
                app.height.set('100')
                app.overlap.set('10')
                app.start()
                deadline = time.monotonic() + 20
                while app.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                assert not app.busy, '后台切分超时'
                assert '完成，共 3 张' in app.status.get(), app.status.get()
                assert float(app.bar['value']) == 100
                with Image.open(source) as original:
                    for index, (top, bottom) in enumerate(((0, 100), (90, 190), (180, 251)), 1):
                        with Image.open(base / f'{suffix}_{index:03d}.png') as part:
                            assert part.size == (31, bottom - top)
                            with original.crop((0, top, 31, bottom)) as expected:
                                assert part.tobytes() == expected.tobytes()
            report.write_text(json.dumps({'ok': True, 'formats': ['PNG', 'JPG', 'JPEG', 'WEBP'], 'checks': ['Tk window', 'background worker', 'progress', 'overlap', 'pixel equality']}, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0
    except Exception:
        report.write_text(json.dumps({'ok': False, 'error': traceback.format_exc()}, ensure_ascii=False, indent=2), encoding='utf-8')
        return 1
    finally:
        if root is not None:
            root.destroy()
