"""创建真实 Tk 窗口并验证后台切分完成状态；测试后自动关闭。"""
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from PIL import Image
from main import App


class GuiTests(unittest.TestCase):
    def test_background_split(self):
        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk()
            root.withdraw()
            try:
                app = App(root)
                src = Path(folder) / 'source.png'
                with Image.new('RGB', (80, 250), 'white') as im:
                    im.save(src)
                app.source.set(str(src))
                app.output.set(folder)
                app.meta = (80, 250, 'PNG')
                app.height.set('100')
                app.overlap.set('10')
                app.refresh()
                self.assertIn('预计 3 张', app.plan.get())
                app.start()
                deadline = time.monotonic() + 15
                while app.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                self.assertFalse(app.busy)
                self.assertIn('完成，共 3 张', app.status.get())
                self.assertEqual(float(app.bar['value']), 100)
                self.assertNotIn('disabled', app.open_button.state())
                self.assertTrue((Path(folder) / '截图_003.png').exists())
            finally:
                root.destroy()


if __name__ == '__main__':
    unittest.main()
