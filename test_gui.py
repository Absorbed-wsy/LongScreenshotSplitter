"""真实 Tk 窗口中的后台处理、预览竞争、校验与失败恢复。"""
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from main import App, split_image


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.base = Path(self.folder.name)
        self.source = self.base / "source.png"
        with Image.new("RGB", (80, 250), "white") as im:
            im.save(self.source)
        self.root = tk.Tk()
        self.root.withdraw()
        self.callback_errors = []
        self.root.report_callback_exception = lambda *args: self.callback_errors.append(args)
        self.app = App(self.root)
        self.app.output.set(self.folder.name)
        self.app.height.set("100")
        self.app.overlap.set("10")

    def tearDown(self):
        self.root.destroy()
        self.folder.cleanup()
        self.assertEqual(self.callback_errors, [], "Tk callback raised an exception")

    def wait_until(self, condition, timeout=10):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        self.assertTrue(condition(), "后台任务超时")

    def load_source(self):
        self.app.load_source(self.source)
        self.wait_until(lambda: not self.app.preview_loading)

    def test_background_split(self):
        self.load_source()
        self.assertEqual(self.app.meta, (80, 250, "PNG"))
        self.assertIsNotNone(self.app.preview_image)
        self.assertIn("预计 3 张", self.app.plan.get())
        self.app.start()
        self.wait_until(lambda: not self.app.busy)
        self.assertIn("完成，共 3 张", self.app.status.get())
        self.assertEqual(float(self.app.bar["value"]), 100)
        self.assertNotIn("disabled", self.app.open_button.state())
        self.assertEqual(self.app.completed_output, self.folder.name)
        self.assertTrue((self.base / "截图_003.png").exists())
        with patch("main.os.startfile", create=True) as startfile:
            self.app.open_output()
            startfile.assert_called_once_with(self.folder.name)

    def test_invalid_settings_block_work_and_recover_immediately(self):
        self.load_source()
        for variable, bad_value in ((self.app.height, "abc"), (self.app.height, "0"),
                                    (self.app.overlap, "100"), (self.app.overlap, "-1"),
                                    (self.app.digits, "0"), (self.app.digits, "11"),
                                    (self.app.prefix, "bad/name")):
            with self.subTest(value=bad_value):
                previous = variable.get()
                variable.set(bad_value)
                self.assertIn("disabled", self.app.start_button.state())
                self.assertTrue(self.app.validation.get())
                with patch("main.split_image") as splitter, patch("main.messagebox.showerror") as error:
                    self.app.start()
                    self.assertFalse(self.app.busy)
                    splitter.assert_not_called()
                    error.assert_called_once()
                variable.set(previous)
                self.assertNotIn("disabled", self.app.start_button.state())
                self.assertEqual(self.app.validation.get(), "")

    def test_disabled_overlap_ignores_its_unfinished_input(self):
        self.load_source()
        self.app.overlap.set("unfinished")
        self.assertIn("disabled", self.app.start_button.state())
        self.app.use_overlap.set(False)
        self.assertEqual(self.app.settings()[1], 0)
        self.assertIn("disabled", self.app.overlap_entry.state())
        self.assertNotIn("disabled", self.app.start_button.state())
        self.app.start()
        self.wait_until(lambda: not self.app.busy)
        with Image.open(self.base / "截图_003.png") as last:
            self.assertEqual(last.size, (80, 50))

    def test_busy_guard_and_settings_snapshot(self):
        self.load_source()
        entered, release = threading.Event(), threading.Event()

        def delayed_split(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test worker was not released")
            return split_image(*args, **kwargs)

        with patch("main.split_image", side_effect=delayed_split) as splitter:
            try:
                self.app.start()
                self.assertTrue(entered.wait(5))
                self.assertTrue(self.app.busy)
                self.assertIn("disabled", self.app.start_button.state())
                self.assertIn("disabled", self.app.overlap_entry.state())
                self.app.start()
                self.app.height.set("200")
                self.app.prefix.set("next-run")
                self.app.load_source(self.base / "missing.png")
                with patch("main.filedialog.askopenfilename") as choose:
                    self.app.choose_source()
                    choose.assert_not_called()
                with patch("main.messagebox.showinfo") as info:
                    self.app.close()
                    info.assert_called_once()
                    self.assertTrue(self.root.winfo_exists())
                splitter.assert_called_once()
            finally:
                release.set()
                self.wait_until(lambda: not self.app.busy)
        self.assertIn("完成，共 3 张", self.app.status.get())
        self.assertTrue((self.base / "截图_003.png").exists())
        self.assertFalse(list(self.base.glob("next-run_*.png")))
        self.assertNotIn("disabled", self.app.start_button.state())

    def test_async_error_restores_controls_and_allows_retry(self):
        self.load_source()
        with patch("main.split_image", side_effect=OSError("simulated full disk")), \
                patch("main.messagebox.showerror") as error:
            self.app.start()
            self.wait_until(lambda: not self.app.busy)
            error.assert_called_once()
            self.assertIn("simulated full disk", error.call_args.args[1])
        self.assertIn("切分失败", self.app.status.get())
        self.assertIsNone(self.app.completed_output)
        self.assertIn("disabled", self.app.open_button.state())
        self.assertNotIn("disabled", self.app.start_button.state())
        self.assertNotIn("disabled", self.app.overlap_entry.state())
        self.app.start()
        self.wait_until(lambda: not self.app.busy)
        self.assertIn("完成，共 3 张", self.app.status.get())
        self.assertTrue((self.base / "截图_003.png").exists())

    def test_file_conflict_does_not_reuse_previous_success_state(self):
        self.load_source()
        self.app.start()
        self.wait_until(lambda: not self.app.busy)
        previous = (self.base / "截图_001.png").read_bytes()
        with patch("main.messagebox.showerror") as error:
            self.app.start()
            self.wait_until(lambda: not self.app.busy)
            error.assert_called_once()
        self.assertIsNone(self.app.completed_output)
        self.assertIn("disabled", self.app.open_button.state())
        self.assertEqual((self.base / "截图_001.png").read_bytes(), previous)
        self.app.prefix.set("retry")
        self.app.start()
        self.wait_until(lambda: not self.app.busy)
        self.assertTrue((self.base / "retry_003.png").exists())

    def test_latest_preview_wins_after_rapid_source_change(self):
        second = self.base / "second.png"
        with Image.new("RGB", (40, 80), "red") as im:
            im.save(second)
        entered, release = threading.Event(), threading.Event()
        original_thumbnail = Image.Image.thumbnail

        def delayed_thumbnail(im, *args, **kwargs):
            if Path(im.filename) == self.source:
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("test preview was not released")
            return original_thumbnail(im, *args, **kwargs)

        with patch.object(Image.Image, "thumbnail", delayed_thumbnail):
            try:
                self.app.load_source(self.source)
                self.assertTrue(entered.wait(5))
                self.assertTrue(self.app.preview_loading)
                self.assertIn("disabled", self.app.start_button.state())
                with patch("main.split_image") as splitter:
                    self.app.start()
                    splitter.assert_not_called()
                self.app.load_source(second)
            finally:
                release.set()
                self.wait_until(lambda: not self.app.preview_loading)
        self.assertEqual(self.app.meta, (40, 80, "PNG"))
        self.assertEqual(self.app.source.get(), str(second))
        self.assertEqual(self.app.preview_image.size, (40, 80))
        self.assertEqual(self.app.preview_image.getpixel((0, 0)), (255, 0, 0, 255))
        self.assertFalse(self.app.busy)
        self.assertNotIn("disabled", self.app.start_button.state())

    def test_preview_failure_does_not_block_split(self):
        with patch.object(Image.Image, "thumbnail", side_effect=OSError("preview decoder failed")):
            self.load_source()
        self.assertIsNone(self.app.preview_image)
        self.assertIn("preview decoder failed", self.app.preview_note)
        self.assertNotIn("disabled", self.app.start_button.state())
        self.app.start()
        self.wait_until(lambda: not self.app.busy)
        self.assertIn("完成，共 3 张", self.app.status.get())

    def test_large_source_waits_for_previous_preview_decoder(self):
        second = self.base / "large.png"
        with Image.new("RGB", (40, 80), "red") as im:
            im.save(second)
        entered, release = threading.Event(), threading.Event()
        original_thumbnail = Image.Image.thumbnail

        def delayed_thumbnail(im, *args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test preview was not released")
            return original_thumbnail(im, *args, **kwargs)

        with patch.object(Image.Image, "thumbnail", delayed_thumbnail) as thumbnail:
            try:
                self.app.load_source(self.source)
                self.assertTrue(entered.wait(5))
                with patch.object(App, "PREVIEW_PIXEL_LIMIT", 100):
                    self.app.load_source(second)
                self.assertTrue(self.app.preview_loading)
                self.assertIn("disabled", self.app.start_button.state())
                with patch("main.split_image") as splitter:
                    self.app.start()
                    splitter.assert_not_called()
            finally:
                release.set()
                self.wait_until(lambda: not self.app.preview_loading)
        self.assertEqual(self.app.meta, (40, 80, "PNG"))
        self.assertIsNone(self.app.preview_image)
        self.assertIn("跳过", self.app.preview_note)
        self.assertNotIn("disabled", self.app.start_button.state())

    def test_large_image_skips_preview_and_remains_ready(self):
        with patch.object(App, "PREVIEW_PIXEL_LIMIT", 100), \
                patch.object(Image.Image, "thumbnail") as thumbnail:
            self.app.load_source(self.source)
            self.wait_until(lambda: not self.app.preview_loading)
            thumbnail.assert_not_called()
        self.assertFalse(self.app.preview_loading)
        self.assertIsNone(self.app.preview_image)
        self.assertIn("跳过", self.app.preview_note)
        self.assertNotIn("disabled", self.app.start_button.state())


if __name__ == "__main__":
    unittest.main()
