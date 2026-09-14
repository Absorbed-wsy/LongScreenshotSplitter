"""中文长截图切分器；只依赖 Pillow，Python 3.10+。"""
import math
import os
import queue
import re
import threading
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image

# 用户主动选择的本地长图可能超过 Pillow 默认像素阈值。
# 解码仍可能占用整张图的内存；一次仅创建一个切片。
Image.MAX_IMAGE_PIXELS = None
FORMATS = {"PNG", "JPEG", "WEBP"}
VERSION = "0.1"


def ranges(height, size, overlap):
    if height <= 0 or size <= 0 or not 0 <= overlap < size:
        raise ValueError("高度必须大于 0，重叠必须大于等于 0 且小于切片高度。")
    top = 0
    while True:
        bottom = min(top + size, height)
        yield top, bottom
        if bottom == height:
            break
        top += size - overlap


def count_parts(height, size, overlap):
    next(ranges(height, size, overlap))
    return 1 + max(0, math.ceil((height - size) / (size - overlap)))


def validate_prefix(prefix):
    if not prefix or re.search(r'[<>:"/\\|?*\x00-\x1f]', prefix) or prefix.endswith((' ', '.')):
        raise ValueError("前缀不能为空或包含 Windows 文件名非法字符，末尾不能是空格或点。")
    if len(prefix) > 100:
        raise ValueError("文件名前缀请限制在 100 个字符内。")


def split_image(source, output, size, overlap, prefix, digits, same=False, progress=None):
    validate_prefix(prefix)
    if not 1 <= digits <= 10:
        raise ValueError("编号位数必须在 1–10 之间。")
    source, output = Path(source), Path(output)
    if not source.is_file():
        raise ValueError("输入图片不存在。")
    if not output.is_dir():
        raise ValueError("请先选择一个存在的输出目录。")
    with Image.open(source) as im:
        if im.format not in FORMATS:
            raise ValueError("仅支持 PNG / JPG / JPEG / WEBP。")
        if getattr(im, 'n_frames', 1) > 1:
            raise ValueError("请选择静态图片，暂不支持动画或多帧图片。")
        total = count_parts(im.height, size, overlap)
        fmt = im.format if same else "PNG"
        ext = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[fmt]
        def target(i):
            return output / f"{prefix}_{i:0{digits}d}{ext}"
        for i in range(1, total + 1):
            if target(i).exists():
                raise FileExistsError(f"已有同名文件：{target(i).name}。请更换前缀或目录。")
        options = {"PNG": {"compress_level": 3}, "JPEG": {"quality": 95, "subsampling": 0}, "WEBP": {"lossless": True}}[fmt]
        if im.info.get("icc_profile"):
            options["icc_profile"] = im.info["icc_profile"]
        for i, (top, bottom) in enumerate(ranges(im.height, size, overlap), 1):
            dest = target(i)
            created = False
            try:
                with dest.open("xb") as stream:
                    created = True
                    with im.crop((0, top, im.width, bottom)) as part:
                        if (fmt == "PNG" and part.mode == "CMYK") or (fmt == "JPEG" and part.mode not in ("RGB", "L", "CMYK")):
                            with part.convert("RGB") as converted:
                                converted.save(stream, format=fmt, **options)
                        else:
                            part.save(stream, format=fmt, **options)
            except BaseException:
                if created:
                    dest.unlink(missing_ok=True)
                raise
            if progress:
                progress(i, total)
    return total


class App:
    def __init__(self, root):
        self.root, self.events, self.busy = root, queue.Queue(), False
        self.meta = None
        self.completed_output = None
        root.title(f"长截图切分器 v{VERSION}")
        root.geometry("800x640")
        root.minsize(760, 620)
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self.height = tk.StringVar(value="4000")
        self.overlap = tk.StringVar(value="100")
        self.use_overlap = tk.BooleanVar(value=True)
        self.prefix = tk.StringVar(value="截图")
        self.digits = tk.StringVar(value="3")
        self.format = tk.StringVar(value="PNG（无损，推荐）")
        self.info = tk.StringVar(value="请选择一张长截图。")
        self.plan = tk.StringVar()
        self.status = tk.StringVar(value="就绪")
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="长截图切分器", font=("Microsoft YaHei UI", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 15))
        for row, label, var, command in [(1, "输入图片", self.source, self.choose_source), (2, "输出目录", self.output, self.choose_output)]:
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10))
            ttk.Entry(frame, textvariable=var, state="readonly").grid(row=row, column=1, sticky="ew", pady=5)
            ttk.Button(frame, text="选择…", command=command).grid(row=row, column=2, padx=(8, 0))
        ttk.Label(frame, textvariable=self.info).grid(row=3, column=0, columnspan=3, sticky="w", pady=8)
        for row, label, var, values in [(4, "切片高度（px）", self.height, (2000, 3000, 4000, 5000)), (5, "编号位数", self.digits, (2, 3, 4, 5)), (7, "输出格式", self.format, ("PNG（无损，推荐）", "与原格式一致"))]:
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
            ttk.Combobox(frame, textvariable=var, values=values, state="readonly" if row == 7 else "normal").grid(row=row, column=1, sticky="ew", pady=5)
        ttk.Label(frame, text="文件名前缀").grid(row=6, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.prefix).grid(row=6, column=1, sticky="ew", pady=5)
        ttk.Checkbutton(frame, text="保留重叠区域", variable=self.use_overlap).grid(row=8, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.overlap, width=10).grid(row=8, column=1, sticky="w", pady=5)
        ttk.Label(frame, text="编号位数：2 位为 01、02；3 位为 001、002，只影响文件名。\n重叠 100px：下一张开头重复上一张末尾的 100 像素，方便阅读跨边界文字；关闭则不重复。\nJPEG 同格式输出会重新有损编码。", wraplength=710).grid(row=9, column=0, columnspan=3, sticky="w", pady=5)
        ttk.Label(frame, textvariable=self.plan, justify="left", wraplength=680).grid(row=10, column=0, columnspan=3, sticky="w", pady=10)
        self.bar = ttk.Progressbar(frame, maximum=100)
        self.bar.grid(row=11, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(frame, textvariable=self.status, wraplength=680).grid(row=12, column=0, columnspan=3, sticky="w", pady=5)
        self.start_button = ttk.Button(frame, text="开始切分", command=self.start)
        self.start_button.grid(row=13, column=0, pady=12)
        self.open_button = ttk.Button(frame, text="打开输出文件夹", command=self.open_output, state="disabled")
        self.open_button.grid(row=13, column=1, sticky="e")
        for var in (self.height, self.overlap, self.use_overlap, self.prefix, self.digits, self.format):
            var.trace_add("write", self.refresh)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def choose_source(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(filetypes=[("图片", "*.png *.jpg *.jpeg *.webp")])
        if not path:
            return
        try:
            with Image.open(path) as im:
                if im.format not in FORMATS or getattr(im, "n_frames", 1) > 1:
                    raise ValueError("请选择受支持的静态图片。")
                self.meta = (im.width, im.height, im.format)
            self.source.set(path)
            self.info.set(f"原图：{self.meta[0]} × {self.meta[1]} 像素 · {self.meta[2]}（按文件原始像素方向切分）")
            self.refresh()
        except Exception as exc:
            messagebox.showerror("无法读取图片", str(exc))

    def choose_output(self):
        if not self.busy:
            path = filedialog.askdirectory()
            if path:
                self.output.set(path)

    def settings(self):
        try:
            size, overlap, digits = int(self.height.get()), int(self.overlap.get()) if self.use_overlap.get() else 0, int(self.digits.get())
        except ValueError:
            raise ValueError("切片高度、重叠像素和编号位数必须是整数。") from None
        count_parts(1, size, overlap)
        if not 1 <= digits <= 10:
            raise ValueError("编号位数必须在 1–10 之间。")
        validate_prefix(self.prefix.get())
        return size, overlap, self.prefix.get(), digits, self.format.get() == "与原格式一致"

    def refresh(self, *_):
        try:
            size, overlap, prefix, digits, same = self.settings()
            if not self.meta:
                return
            _, height, fmt = self.meta
            count = count_parts(height, size, overlap)
            last = (count - 1) * (size - overlap)
            ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[fmt if same else "PNG"]
            self.plan.set(f"预计 {count} 张 · 命名：{prefix}_{1:0{digits}d}.{ext} … {prefix}_{count:0{digits}d}.{ext}\n首张范围：[0, {min(size, height)}) px；末张范围：[{last}, {height}) px\n范围从 0 开始，含起点、不含终点；编号超出位数时自动扩展。")
        except ValueError as exc:
            self.plan.set(str(exc))

    def start(self):
        if self.busy:
            return
        try:
            settings = self.settings()
            if not self.source.get() or not self.output.get():
                raise ValueError("请选择输入图片和输出目录。")
        except ValueError as exc:
            messagebox.showerror("请检查设置", str(exc))
            return
        source, output = self.source.get(), self.output.get()
        self.busy = True
        self.start_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.bar["value"] = 0
        self.status.set("正在读取图片…大图首次解码可能需要一些时间。")
        def worker():
            try:
                n = split_image(source, output, *settings, progress=lambda i, total: self.events.put(("progress", (i, total))))
                self.events.put(("done", (n, output)))
            except Exception as exc:
                self.events.put(("error", str(exc) or type(exc).__name__))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            for _ in range(100):
                event, value = self.events.get_nowait()
                if event == "progress":
                    i, total = value
                    self.bar["value"] = i * 100 / total
                    self.status.set(f"正在切分：{i} / {total}")
                else:
                    self.busy = False
                    self.start_button.configure(state="normal")
                    if event == "done":
                        n, self.completed_output = value
                        self.status.set(f"完成，共 {n} 张。输出位置：{self.completed_output}")
                        self.open_button.configure(state="normal")
                    else:
                        self.status.set("切分失败；已成功写出的切片保留，请更换前缀或目录后重试。")
                        messagebox.showerror("切分失败", value)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def open_output(self):
        try:
            os.startfile(self.completed_output)
        except Exception as exc:
            messagebox.showerror("无法打开目录", str(exc))

    def close(self):
        if self.busy:
            messagebox.showinfo("正在切分", "请等待切分完成后关闭窗口。")
        else:
            self.root.destroy()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from selftest import run
        sys.exit(run(App, Path(sys.argv[2])))
    root = tk.Tk()
    App(root)
    root.mainloop()
