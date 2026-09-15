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
from PIL import Image, ImageTk

# 用户主动选择的本地长图可能超过 Pillow 默认像素阈值。
# 解码仍可能占用整张图的内存；一次仅创建一个切片。
Image.MAX_IMAGE_PIXELS = None
FORMATS = {"PNG", "JPEG", "WEBP"}
VERSION = "0.2"


def resource_path(name):
    """源码和 PyInstaller 单文件程序共用的资源路径。"""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / name


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
    BG = "#F3F5FA"
    INK = "#202840"
    MUTED = "#6E778D"
    ACCENT = "#5755D9"
    BORDER = "#E4E8F1"
    PREVIEW_PIXEL_LIMIT = 50_000_000

    def __init__(self, root):
        self.root, self.events, self.busy = root, queue.Queue(), False
        self.meta = self.completed_output = None
        self.preview_image = self.preview_photo = self.icon_image = None
        self.preview_loading, self.preview_token = False, 0
        self.preview_queue = queue.Queue()
        self.preview_worker = None
        self.preview_note = ""
        self._closed = False
        self._draw_after = None
        self._poll_after = None
        self._editable = []
        root.title(f"长截图切分器 v{VERSION}")
        root.geometry("1080x760")
        root.minsize(900, 620)
        root.configure(bg=self.BG)
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self.height = tk.StringVar(value="4000")
        self.overlap = tk.StringVar(value="100")
        self.use_overlap = tk.BooleanVar(value=True)
        self.prefix = tk.StringVar(value="截图")
        self.digits = tk.StringVar(value="3")
        self.format = tk.StringVar(value="PNG（无损，推荐）")
        self.info = tk.StringVar(value="支持 PNG、JPG / JPEG、WEBP 静态图片")
        self.plan = tk.StringVar(value="选择图片后，这里会显示切分方案。")
        self.status = tk.StringVar(value="准备就绪，请选择图片和输出目录。")
        self.validation = tk.StringVar()
        self.summary = tk.StringVar(value="等待导入")
        self.filename = tk.StringVar(value="文件名示例：截图_001.png")
        self._style()
        self._load_icon()
        self._build_header()
        self._build_footer()
        self._build_body()
        for var in (self.height, self.overlap, self.use_overlap, self.prefix,
                    self.digits, self.format, self.source, self.output):
            var.trace_add("write", self.refresh)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Destroy>", self._on_destroy, add="+")
        root.bind("<Control-o>", lambda event: self.choose_source())
        self.refresh()
        self._poll_after = root.after(100, self.poll)

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        self.root.option_add("*Font", ("Microsoft YaHei UI", 10))
        style.configure("TFrame", background="white")
        style.configure("TLabel", background="white", foreground=self.INK)
        style.configure("TButton", padding=(13, 8), background="#F7F8FC",
                        foreground=self.INK, borderwidth=1, bordercolor=self.BORDER,
                        lightcolor=self.BORDER, darkcolor=self.BORDER)
        style.map("TButton", background=[("active", "#EEF0FC"), ("disabled", "#F4F5F8")],
                  foreground=[("disabled", "#A0A7B7")])
        style.configure("Accent.TButton", background=self.ACCENT, foreground="white",
                        bordercolor=self.ACCENT, lightcolor=self.ACCENT,
                        darkcolor=self.ACCENT, padding=(25, 11), font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Accent.TButton", background=[("disabled", "#DBDCF0"), ("active", "#4543BE")],
                  foreground=[("disabled", "#9195B3"), ("!disabled", "white")])
        style.configure("TEntry", padding=7, fieldbackground="white", bordercolor=self.BORDER,
                        lightcolor=self.BORDER, darkcolor=self.BORDER, insertcolor=self.INK)
        style.configure("TCombobox", padding=6, fieldbackground="white", bordercolor=self.BORDER,
                        lightcolor=self.BORDER, darkcolor=self.BORDER, arrowsize=14)
        style.map("TCombobox", fieldbackground=[("readonly", "white"), ("disabled", "#F4F5F8")],
                  selectbackground=[("readonly", "white")], selectforeground=[("readonly", self.INK)])
        style.configure("TCheckbutton", background="white", foreground=self.INK, padding=0)
        style.map("TCheckbutton", background=[("active", "white")])
        style.configure("Horizontal.TProgressbar", troughcolor="#EBEDF6", background=self.ACCENT,
                        bordercolor="#EBEDF6", lightcolor=self.ACCENT, darkcolor=self.ACCENT,
                        thickness=5)
        style.configure("Vertical.TScrollbar", background="#DBDFE9", troughcolor=self.BG,
                        borderwidth=0, arrowsize=11)

    def _load_icon(self):
        try:
            self.icon_image = tk.PhotoImage(master=self.root, file=str(resource_path("assets/app-icon.png")))
            self.root.iconphoto(True, self.icon_image)
            if sys.platform == "win32":
                self.root.iconbitmap(str(resource_path("assets/app-icon.ico")))
        except (tk.TclError, OSError):
            # 源码检出暂时缺少资源时，仍能正常使用切分功能。
            pass

    def _label(self, parent, text=None, variable=None, *, muted=False, size=10,
               bold=False, bg="white", **kwargs):
        return tk.Label(parent, text=text, textvariable=variable, bg=bg,
                        fg=self.MUTED if muted else self.INK,
                        font=("Microsoft YaHei UI", size, "bold" if bold else "normal"),
                        anchor="w", **kwargs)

    def _build_header(self):
        header = tk.Frame(self.root, bg=self.BG)
        header.pack(fill="x", padx=26, pady=(20, 17))
        if self.icon_image is not None:
            with Image.open(resource_path("assets/app-icon.png")) as im:
                self._brand_icon = ImageTk.PhotoImage(im.resize((44, 44), Image.Resampling.LANCZOS), master=self.root)
            tk.Label(header, image=self._brand_icon, bg=self.BG).pack(side="left", padx=(0, 12))
        else:
            tk.Label(header, text="▤", bg=self.ACCENT, fg="white", font=("Segoe UI", 23),
                     width=2).pack(side="left", padx=(0, 12))
        titles = tk.Frame(header, bg=self.BG)
        titles.pack(side="left")
        self._label(titles, "长截图切分器", size=20, bold=True, bg=self.BG).pack(anchor="w")
        self._label(titles, "把长图，变成刚刚好的每一张。", muted=True, bg=self.BG).pack(anchor="w", pady=(3, 0))
        tk.Label(header, text=f"  v{VERSION}  ", bg="#E8E8FC", fg=self.ACCENT,
                 font=("Microsoft YaHei UI", 9, "bold"), pady=5).pack(side="right")
        self._label(header, "本地处理 · 原图不变", muted=True, bg=self.BG).pack(side="right", padx=16)

    def _build_footer(self):
        footer = tk.Frame(self.root, bg="white", highlightbackground=self.BORDER, highlightthickness=1)
        footer.pack(side="bottom", fill="x")
        self.bar = ttk.Progressbar(footer, maximum=100)
        self.bar.pack(fill="x")
        row = tk.Frame(footer, bg="white")
        row.pack(fill="x", padx=25, pady=15)
        actions = tk.Frame(row, bg="white")
        actions.pack(side="right", padx=(16, 0))
        self.start_button = ttk.Button(actions, text="开始切分", style="Accent.TButton", command=self.start)
        self.start_button.pack(side="right")
        self.open_button = ttk.Button(actions, text="打开输出文件夹", command=self.open_output, state="disabled")
        self.open_button.pack(side="right", padx=(0, 10))
        self.status_label = self._label(row, variable=self.status, muted=True, wraplength=520, justify="left")
        self.status_label.pack(side="left", fill="x", expand=True)
        row.bind("<Configure>", lambda event: self.status_label.configure(wraplength=max(180, event.width - actions.winfo_reqwidth() - 20)))

    def _card(self, parent, title, subtitle=None):
        card = tk.Frame(parent, bg="white", highlightbackground=self.BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(card, bg="white")
        inner.pack(fill="both", padx=16, pady=14)
        self._label(inner, title, bold=True, size=11).pack(anchor="w", pady=(0, 11))
        if subtitle:
            self._label(inner, subtitle, muted=True, size=9, wraplength=290, justify="left").pack(anchor="w", pady=(0, 10))
        return inner

    def _editable_widget(self, widget, state="normal"):
        self._editable.append((widget, state))
        return widget

    def _build_body(self):
        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=25, pady=(0, 18))
        body.columnconfigure(0, minsize=350, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=self.BG, width=363)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.grid_propagate(False)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.form_canvas = tk.Canvas(left, bg=self.BG, bd=0, highlightthickness=0, width=346)
        self.form_canvas.grid(row=0, column=0, sticky="nsew")
        form_scroll = ttk.Scrollbar(left, orient="vertical", command=self.form_canvas.yview)
        form_scroll.grid(row=0, column=1, sticky="ns", padx=(5, 0))
        self.form_canvas.configure(yscrollcommand=form_scroll.set)
        form = tk.Frame(self.form_canvas, bg=self.BG)
        form_window = self.form_canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind("<Configure>", lambda event: self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all")))
        self.form_canvas.bind("<Configure>", lambda event: self.form_canvas.itemconfigure(form_window, width=event.width))
        self.root.bind("<MouseWheel>", self._scroll_form, add="+")

        files = self._card(form, "01  选择文件")
        self._label(files, "输入图片", muted=True, size=9).pack(anchor="w")
        source_row = tk.Frame(files, bg="white")
        source_row.pack(fill="x", pady=(5, 10))
        self._editable_widget(ttk.Button(source_row, text="浏览…", command=self.choose_source)).pack(side="right", padx=(7, 0))
        ttk.Entry(source_row, textvariable=self.source, state="readonly").pack(fill="x", expand=True)
        self._label(files, "输出目录", muted=True, size=9).pack(anchor="w")
        output_row = tk.Frame(files, bg="white")
        output_row.pack(fill="x", pady=(5, 0))
        self._editable_widget(ttk.Button(output_row, text="浏览…", command=self.choose_output)).pack(side="right", padx=(7, 0))
        ttk.Entry(output_row, textvariable=self.output, state="readonly").pack(fill="x", expand=True)

        params = self._card(form, "02  切分设置")
        self._label(params, "每张切片高度", muted=True, size=9).pack(anchor="w")
        height_row = tk.Frame(params, bg="white")
        height_row.pack(fill="x", pady=(5, 12))
        self._label(height_row, "像素", muted=True, size=9).pack(side="right", padx=(8, 0))
        self._editable_widget(ttk.Combobox(height_row, textvariable=self.height, values=(2000, 3000, 4000, 5000), width=12)).pack(fill="x", expand=True)
        overlap_row = tk.Frame(params, bg="white")
        overlap_row.pack(fill="x")
        self._editable_widget(ttk.Checkbutton(overlap_row, text="保留重叠区域", variable=self.use_overlap)).pack(side="left")
        self._label(overlap_row, "px", muted=True, size=9).pack(side="right", padx=(6, 0))
        self.overlap_entry = self._editable_widget(ttk.Entry(overlap_row, textvariable=self.overlap, width=7))
        self.overlap_entry.pack(side="right", padx=(5, 0))
        self._label(params, "重复相邻切片交界处，方便连贯阅读。", muted=True, size=9,
                    wraplength=295, justify="left").pack(anchor="w", pady=(8, 0))

        naming = self._card(form, "03  导出选项")
        names_row = tk.Frame(naming, bg="white")
        names_row.pack(fill="x")
        names_row.columnconfigure(0, weight=1)
        self._label(names_row, "文件名前缀", muted=True, size=9).grid(row=0, column=0, sticky="w")
        self._label(names_row, "编号位数", muted=True, size=9).grid(row=0, column=1, sticky="w", padx=(10, 0))
        self._editable_widget(ttk.Entry(names_row, textvariable=self.prefix, width=15)).grid(row=1, column=0, sticky="ew", pady=(5, 10))
        self._editable_widget(ttk.Combobox(names_row, textvariable=self.digits, values=(2, 3, 4, 5), width=5)).grid(row=1, column=1, pady=(5, 10), padx=(10, 0))
        self._label(naming, "输出格式", muted=True, size=9).pack(anchor="w")
        self._editable_widget(ttk.Combobox(naming, textvariable=self.format,
            values=("PNG（无损，推荐）", "与原格式一致"), state="readonly"), "readonly").pack(fill="x", pady=(5, 8))
        self._label(naming, variable=self.filename, muted=True, size=9, wraplength=290, justify="left").pack(anchor="w")
        self._label(naming, "同名文件不会覆盖；JPEG 输出会重新有损编码。", muted=True, size=9,
                    wraplength=290, justify="left").pack(anchor="w", pady=(6, 0))
        tk.Label(form, textvariable=self.validation, bg=self.BG, fg="#BC3D50", anchor="w",
                 wraplength=315, justify="left", font=("Microsoft YaHei UI", 9)).pack(fill="x", padx=3, pady=(0, 8))

        preview = tk.Frame(body, bg="white", highlightbackground=self.BORDER, highlightthickness=1)
        preview.grid(row=0, column=1, sticky="nsew")
        preview_header = tk.Frame(preview, bg="white")
        preview_header.pack(fill="x", padx=20, pady=(17, 4))
        self._label(preview_header, "切分预览", size=12, bold=True).pack(side="left")
        tk.Label(preview_header, textvariable=self.summary, bg="#EEEEFF", fg=self.ACCENT,
                 font=("Microsoft YaHei UI", 9, "bold"), padx=10, pady=4).pack(side="right")
        self.info_label = self._label(preview, variable=self.info, muted=True, size=9, wraplength=570, justify="left")
        self.info_label.pack(fill="x", padx=20, pady=(4, 13))
        self.preview_canvas = tk.Canvas(preview, bg="#F6F7FB", bd=0, highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True, padx=18)
        self.preview_canvas.bind("<Configure>", self._schedule_preview)
        legend = tk.Frame(preview, bg="white")
        legend.pack(fill="x", padx=20, pady=(11, 7))
        self._label(legend, "┄  切分起点", muted=True, size=9).pack(side="left")
        self._label(legend, "▧  重叠区域", muted=True, size=9).pack(side="left", padx=17)
        self._label(legend, "按原始像素切分", muted=True, size=9).pack(side="right")
        self.plan_label = self._label(preview, variable=self.plan, muted=True, size=9, wraplength=570, justify="left")
        self.plan_label.pack(fill="x", padx=20, pady=(0, 15))
        preview.bind("<Configure>", lambda event: self._wrap_preview_labels(event.width))

    def _wrap_preview_labels(self, width):
        for label in (self.info_label, self.plan_label):
            label.configure(wraplength=max(250, width - 42))

    def _scroll_form(self, event):
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        while widget:
            if widget == self.form_canvas:
                self.form_canvas.yview_scroll(-int(event.delta / 120), "units")
                return "break"
            widget = widget.master

    def choose_source(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self.root, title="选择长截图",
            filetypes=[("支持的图片", "*.png *.jpg *.jpeg *.webp")])
        if path:
            self.load_source(path)

    def load_source(self, path):
        """读取文件头后异步生成缩略图；切换图片时只接收最新请求。"""
        if self.busy:
            return
        try:
            with Image.open(path) as im:
                if im.format not in FORMATS or getattr(im, "n_frames", 1) > 1:
                    raise ValueError("请选择 PNG / JPG / JPEG / WEBP 静态图片。")
                meta = (im.width, im.height, im.format)
            self.preview_token += 1
            self.meta = meta
            if self.preview_image is not None:
                self.preview_image.close()
            self.preview_image = self.preview_photo = None
            allow_preview = meta[0] * meta[1] <= self.PREVIEW_PIXEL_LIMIT
            # 即使新图跳过预览，也等待上一个解码任务退出后再允许切分。
            self.preview_loading = True
            self.preview_note = "正在生成缩略图…" if allow_preview else "图片较大，已跳过缩略图以节省内存。\n仍可按设置正常切分。"
            self.source.set(str(path))
            self.info.set(f"{Path(path).name}  ·  {meta[0]:,} × {meta[1]:,} px  ·  {meta[2]}")
            self.status.set("正在准备图片，请稍候。")
            self.preview_queue.put((self.preview_token, str(path), allow_preview))
            if self.preview_worker is None:
                self.preview_worker = threading.Thread(target=self._preview_worker,
                    args=(self.preview_queue, self.events), daemon=True)
                self.preview_worker.start()
            self.refresh()
        except Exception as exc:
            messagebox.showerror("无法读取图片", str(exc), parent=self.root)

    @staticmethod
    def _preview_worker(tasks, events):
        while True:
            task = tasks.get()
            # 合并排队的选择，避免重复解码已被替换的图片。
            while not tasks.empty():
                task = tasks.get_nowait()
            if task is None:
                return
            token, path, allow_preview = task
            if not allow_preview:
                events.put(("preview", (token, None, "图片较大，已跳过缩略图以节省内存。\n仍可按设置正常切分。")))
                continue
            thumbnail = None
            try:
                with Image.open(path) as im:
                    im.thumbnail((900, 1800), Image.Resampling.LANCZOS)
                    thumbnail = im.convert("RGBA")
                events.put(("preview", (token, thumbnail, "")))
            except Exception as exc:
                if thumbnail is not None:
                    thumbnail.close()
                events.put(("preview", (token, None, f"缩略图暂不可用：{exc}\n仍可尝试切分原图。")))

    def choose_output(self):
        if not self.busy:
            path = filedialog.askdirectory(parent=self.root, title="选择输出目录")
            if path:
                self.output.set(path)

    def settings(self):
        try:
            size = int(self.height.get())
            overlap = int(self.overlap.get()) if self.use_overlap.get() else 0
            digits = int(self.digits.get())
        except ValueError:
            raise ValueError("切片高度、重叠像素和编号位数必须是整数。") from None
        count_parts(1, size, overlap)
        if not 1 <= digits <= 10:
            raise ValueError("编号位数必须在 1–10 之间。")
        validate_prefix(self.prefix.get())
        return size, overlap, self.prefix.get(), digits, self.format.get() == "与原格式一致"

    def refresh(self, *_):
        valid = True
        try:
            size, overlap, prefix, digits, same = self.settings()
            self.validation.set("")
            fmt = self.meta[2] if self.meta and same else "PNG"
            ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[fmt]
            self.filename.set(f"文件名示例：{prefix}_{1:0{digits}d}.{ext}")
            if self.meta:
                height = self.meta[1]
                count = count_parts(height, size, overlap)
                last = (count - 1) * (size - overlap)
                self.summary.set(f"预计 {count:,} 张")
                self.plan.set(f"预计 {count} 张 · {prefix}_{1:0{digits}d}.{ext} … {prefix}_{count:0{digits}d}.{ext}\n"
                              f"首张 0–{min(size, height):,} px · 末张 {last:,}–{height:,} px（含起点，不含终点）")
            else:
                self.summary.set("等待导入")
                self.plan.set("选择图片后，这里会显示切分方案。")
        except ValueError as exc:
            valid = False
            self.validation.set(str(exc))
            self.plan.set(str(exc))
            self.summary.set("请检查设置")
        for widget, normal_state in self._editable:
            widget.configure(state="disabled" if self.busy else normal_state)
        self.overlap_entry.configure(state="disabled" if self.busy or not self.use_overlap.get() else "normal")
        ready = valid and bool(self.source.get()) and bool(self.output.get()) and not self.busy and not self.preview_loading
        self.start_button.configure(state="normal" if ready else "disabled", text="正在切分…" if self.busy else "开始切分")
        self.open_button.configure(state="normal" if self.completed_output and not self.busy else "disabled")
        self._schedule_preview()

    def _schedule_preview(self, *_):
        if not self._closed and self._draw_after is None:
            self._draw_after = self.root.after(45, self._draw_preview)

    def _draw_preview(self):
        self._draw_after = None
        if self._closed:
            return
        canvas = self.preview_canvas
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 20 or height < 20:
            return
        cx, cy = width / 2, height / 2
        if self.preview_image is None:
            if not self.meta:
                x, y = cx - 39, cy - 91
                canvas.create_rectangle(x + 6, y + 7, x + 84, y + 113, fill="#E7E8F8", outline="")
                canvas.create_rectangle(x, y, x + 78, y + 106, fill="white", outline="#D6DAEE", width=2)
                for offset, length in ((22, 40), (33, 50), (68, 46), (79, 32)):
                    canvas.create_line(x + 14, y + offset, x + 14 + length, y + offset, fill="#CFD3E7", width=3)
                canvas.create_line(x - 13, y + 51, x + 91, y + 51, fill=self.ACCENT, width=2, dash=(5, 4))
                canvas.create_text(cx, cy + 47, text="从一张长截图开始", fill=self.INK, font=("Microsoft YaHei UI", 13, "bold"))
                canvas.create_text(cx, cy + 80, text="在左侧选择图片，即可查看切片边界", fill=self.MUTED, font=("Microsoft YaHei UI", 10))
                canvas.create_text(cx, cy + 107, text="PNG  /  JPG  /  WEBP", fill="#979EB0", font=("Segoe UI", 9))
            else:
                canvas.create_text(cx, cy, text=self.preview_note, fill=self.MUTED,
                                   width=max(160, width - 70), justify="center", font=("Microsoft YaHei UI", 10))
            return
        thumb = self.preview_image
        scale = min((width - 108) / thumb.width, (height - 32) / thumb.height, 1.0)
        draw_width, draw_height = max(1, int(thumb.width * scale)), max(1, int(thumb.height * scale))
        resized = thumb.resize((draw_width, draw_height), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(resized, master=self.root)
        resized.close()
        x, y = (width - draw_width) / 2, (height - draw_height) / 2
        canvas.create_rectangle(x + 4, y + 4, x + draw_width + 4, y + draw_height + 4, fill="#DFE3EE", outline="")
        canvas.create_rectangle(x, y, x + draw_width, y + draw_height, fill="white", outline="#CDD3E3")
        canvas.create_image(x, y, image=self.preview_photo, anchor="nw")
        if not self.meta:
            return
        try:
            size, overlap, *_ = self.settings()
            original_height = self.meta[1]
            count = count_parts(original_height, size, overlap)
            pixel_scale = draw_height / original_height
            # 极多切片只显示均匀抽样的边界，避免 Canvas 堆积成千上万对象。
            stride = max(1, math.ceil(count / 35))
            for index in range(0, count, stride):
                top = index * (size - overlap)
                line_y = y + top * pixel_scale
                if index and overlap:
                    bottom_y = min(y + draw_height, line_y + overlap * pixel_scale)
                    canvas.create_rectangle(x, line_y, x + draw_width, max(line_y + 2, bottom_y),
                                            fill="#A9A7FA", stipple="gray50", outline="")
                canvas.create_line(x - 7, line_y, x + draw_width + 7, line_y,
                                   fill=self.ACCENT, dash=(5, 3), width=1)
                if count <= 12 or index % max(stride, math.ceil(count / 8)) == 0:
                    canvas.create_text(x + draw_width + 13, line_y + 6, text=f"{index + 1:02d}",
                                       anchor="nw", fill=self.ACCENT, font=("Segoe UI", 9, "bold"))
            if stride > 1:
                canvas.create_text(12, height - 12, anchor="sw", text=f"切片较多，仅显示部分边界 · 共 {count:,} 张",
                                   fill=self.MUTED, font=("Microsoft YaHei UI", 8))
        except ValueError:
            pass

    def start(self):
        if self.busy or self.preview_loading:
            return
        try:
            settings = self.settings()
            if not self.source.get() or not self.output.get():
                raise ValueError("请选择输入图片和输出目录。")
        except ValueError as exc:
            messagebox.showerror("请检查设置", str(exc), parent=self.root)
            return
        source, output = self.source.get(), self.output.get()
        self.busy = True
        self.completed_output = None
        self.bar["value"] = 0
        self.status.set("正在读取图片…大图首次解码可能需要一些时间。")
        self.refresh()
        def worker():
            try:
                n = split_image(source, output, *settings,
                    progress=lambda i, total: self.events.put(("progress", (i, total))))
                self.events.put(("done", (n, output)))
            except Exception as exc:
                self.events.put(("error", str(exc) or type(exc).__name__))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        self._poll_after = None
        if self._closed:
            return
        try:
            for _ in range(100):
                event, value = self.events.get_nowait()
                if event == "preview":
                    token, thumbnail, note = value
                    if token != self.preview_token:
                        if thumbnail is not None:
                            thumbnail.close()
                        continue
                    self.preview_loading = False
                    self.preview_image, self.preview_note = thumbnail, note
                    if not self.busy:
                        self.status.set("图片已就绪，请确认切分设置。" if thumbnail is not None else "图片已就绪；未显示缩略图，可继续切分。")
                    self.refresh()
                elif event == "progress":
                    i, total = value
                    self.bar["value"] = i * 100 / total
                    self.status.set(f"正在切分：{i} / {total}")
                elif event in ("done", "error"):
                    self.busy = False
                    if event == "done":
                        n, self.completed_output = value
                        self.status.set(f"完成，共 {n} 张。输出位置：{self.completed_output}")
                    else:
                        self.status.set("切分失败；已成功写出的切片保留，请更换前缀或目录后重试。")
                        messagebox.showerror("切分失败", value, parent=self.root)
                    self.refresh()
        except queue.Empty:
            pass
        self._poll_after = self.root.after(100, self.poll)

    def open_output(self):
        if self.busy or not self.completed_output:
            return
        try:
            os.startfile(self.completed_output)
        except Exception as exc:
            messagebox.showerror("无法打开目录", str(exc), parent=self.root)

    def _on_destroy(self, event):
        if event.widget == self.root:
            self._closed = True
            for after_id in (self._poll_after, self._draw_after):
                if after_id is not None:
                    self.root.after_cancel(after_id)
            self.preview_queue.put(None)
            if self.preview_image is not None:
                self.preview_image.close()

    def close(self):
        if self.busy:
            messagebox.showinfo("正在切分", "请等待切分完成后关闭窗口。", parent=self.root)
        else:
            self.root.destroy()

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from selftest import run
        sys.exit(run(App, Path(sys.argv[2])))
    root = tk.Tk()
    App(root)
    root.mainloop()
