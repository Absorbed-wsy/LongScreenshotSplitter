"""验证发布包的窗口、图标、预览和编码器；只使用临时生成的图片。"""
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk


def run(app_class, report):
    root = None
    checks = []
    dialogs = []
    callback_errors = []
    original_showerror = messagebox.showerror

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    def wait_until(condition, message):
        deadline = time.monotonic() + 20
        while not condition() and time.monotonic() < deadline:
            root.update()
            require(not callback_errors, "Tk callback error: " + "\n".join(callback_errors))
            time.sleep(0.01)
        root.update()
        require(condition(), message)
        require(not callback_errors, "Tk callback error: " + "\n".join(callback_errors))

    try:
        # 自测失败时写报告，避免无控制台的发布包被模态错误框卡住。
        messagebox.showerror = lambda title, message, **kwargs: dialogs.append((title, str(message)))
        root = tk.Tk()
        root.withdraw()
        root.report_callback_exception = lambda kind, value, tb: callback_errors.append(
            "".join(traceback.format_exception(kind, value, tb)))
        app = app_class(root)
        module = sys.modules[app_class.__module__]
        require(module.VERSION == "0.2", "Unexpected application version")
        require("v0.2" in root.title(), "Window version missing")
        checks.append("Tk window and version")

        require(app.icon_image is not None, "Bundled window icon did not load")
        require(app.icon_image.width() >= 256, "PNG icon is missing or too small")
        icon_path = module.resource_path("assets/app-icon.ico")
        with Image.open(icon_path) as icon:
            required_sizes = {(16, 16), (32, 32), (48, 48), (256, 256)}
            require(required_sizes.issubset(icon.ico.sizes()), "ICO is missing Windows icon sizes")
        if sys.platform == "win32":
            # Windows Tk 的 iconbitmap getter 返回空串；显式加载可验证 ICO 能被窗口系统读取。
            root.iconbitmap(str(icon_path))
        checks.append("bundled PNG and multi-size Windows ICO")

        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for suffix in ("png", "jpg", "jpeg", "webp"):
                source = base / ("input." + suffix)
                with Image.new("RGB", (31, 251)) as original:
                    original.putdata([(x, y, (x + y) % 256) for y in range(251) for x in range(31)])
                    original.save(source)
                source_bytes = source.read_bytes()
                app.output.set(folder)
                app.prefix.set(suffix)
                app.height.set("100")
                app.overlap.set("10")
                app.format.set("PNG（无损，推荐）")
                app.load_source(source)
                wait_until(lambda: not app.preview_loading, "后台预览超时")
                require(app.preview_image is not None, "Preview failed for " + suffix)
                preview_photo = ImageTk.PhotoImage(app.preview_image, master=root)
                require(preview_photo.width() == 31, "Tk preview image failed")
                require("预计 3 张" in app.plan.get(), app.plan.get())
                app.start()
                wait_until(lambda: not app.busy, "后台切分超时")
                require("完成，共 3 张" in app.status.get(), app.status.get())
                require(float(app.bar["value"]) == 100, "Progress did not reach 100%")
                require("disabled" not in app.open_button.state(), "Completed output button disabled")
                with Image.open(source) as original:
                    for index, (top, bottom) in enumerate(((0, 100), (90, 190), (180, 251)), 1):
                        with Image.open(base / f"{suffix}_{index:03d}.png") as part:
                            require(part.size == (31, bottom - top), "Incorrect slice dimensions")
                            with original.crop((0, top, 31, bottom)) as expected:
                                require(part.tobytes() == expected.tobytes(), "Output pixels changed")
                require(source.read_bytes() == source_bytes, "Source image was modified")

                app.prefix.set(suffix + "same")
                app.format.set("与原格式一致")
                app.start()
                wait_until(lambda: not app.busy, "原格式切分超时")
                require("完成，共 3 张" in app.status.get(), app.status.get())
                extension = "jpg" if suffix == "jpeg" else suffix
                expected_format = "JPEG" if suffix in ("jpg", "jpeg") else suffix.upper()
                with Image.open(base / f"{suffix}same_003.{extension}") as part:
                    require(part.format == expected_format, "Incorrect original-format encoder")
                    require(part.size == (31, 71), "Incorrect original-format final slice")
            require(not dialogs, "Unexpected dialogs: " + repr(dialogs))
            checks.extend(["PNG/JPG/JPEG/WEBP preview and encoders", "background worker and progress",
                           "overlap and pixel equality", "source file unchanged"])

            # 重复任务必须报同名冲突，并清除上一次成功状态；改名前缀后能够恢复。
            existing = base / "webpsame_001.webp"
            existing_bytes = existing.read_bytes()
            app.start()
            wait_until(lambda: not app.busy, "同名文件检查超时")
            require(len(dialogs) == 1 and "同名" in dialogs[0][1], "Conflict was not reported")
            require(app.completed_output is None, "Failure retained a stale success state")
            require("disabled" in app.open_button.state(), "Failure retained output navigation")
            require(existing.read_bytes() == existing_bytes, "Existing output was overwritten")
            app.prefix.set("retry")
            app.start()
            wait_until(lambda: not app.busy, "重试超时")
            require("完成，共 3 张" in app.status.get(), app.status.get())
            require((base / "retry_003.webp").is_file(), "Retry did not produce output")
            require(len(dialogs) == 1, "Unexpected error after retry")
            checks.append("existing-file protection and error recovery")

        report.write_text(json.dumps({"ok": True, "version": module.VERSION,
            "frozen": bool(getattr(sys, "frozen", False)),
            "formats": ["PNG", "JPG", "JPEG", "WEBP"], "checks": checks},
            ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except Exception:
        report.write_text(json.dumps({"ok": False, "checks_passed": checks,
            "dialogs": dialogs, "error": traceback.format_exc()},
            ensure_ascii=False, indent=2), encoding="utf-8")
        return 1
    finally:
        messagebox.showerror = original_showerror
        if root is not None:
            root.destroy()
