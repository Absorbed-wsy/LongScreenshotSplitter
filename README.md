# 长截图切分器 · LongScreenshotSplitter

<img src="assets/app-icon.png" alt="长截图切分器图标" width="88" />

把一张超长截图按原始像素切成多张小图，方便上传、阅读和整理。中文桌面界面，可自定义高度、重叠区域和文件名；所有图片都在本机处理。

**[下载 Windows v0.2](https://github.com/Absorbed-wsy/LongScreenshotSplitter/releases/tag/v0.2)** · [更新日志](CHANGELOG.md)

## v0.2 新变化

- **更清晰的操作界面**：左侧依次选择文件、调整切分设置和导出选项；右侧查看预览；底部显示进度与操作按钮。左侧可以滚动，`Ctrl+O` 快速选图。
- **看得到的切分方案**：异步加载缩略图，标记切分起点和重叠区域，实时更新预计数量与文件名。
- **更明确的操作反馈**：参数错误直接显示，关闭重叠后禁用像素输入；处理时锁定设置，失败后可以修正并重试。
- **专属软件图标**：透明 PNG、多尺寸 Windows ICO，同时用于窗口和 EXE。

## 下载与启动

普通用户无需安装 Python：

1. 打开上方 Release 页面，在 **Assets** 中下载 `LongScreenshotSplitter-v0.2-windows-x64.exe`。
2. 双击 EXE，直接打开软件，不显示终端窗口，也不需要安装。
3. 选择图片、输出目录，调整设置后点击 **开始切分**。

发布包为 Windows x64 版本，本次在 Windows 11 x64 上验证。也提供 SHA-256 校验文件。EXE 未进行代码签名。

## 功能

| 功能 | 说明 |
| --- | --- |
| 输入图片 | 单张静态 PNG、JPG、JPEG、WEBP |
| 输出目录 | 自行选择已有文件夹 |
| 切片高度 | 输入正整数，或选择 2000 / 3000 / 4000 / 5000px |
| 纵向切分 | 保留原始宽度，不缩放，末张自动保留剩余高度 |
| 重叠区域 | 默认 100px，可修改或关闭，方便阅读跨切片文字 |
| 输出格式 | 默认无损 PNG，也可与输入格式一致 |
| 文件命名 | 可自定义前缀及编号位数，从 1 开始编号 |
| 切分预览 | 缩略图显示切分边界与重叠，提供原图尺寸、预计数量、命名示例和首尾范围 |
| 后台处理 | 显示进度与状态，完成后可打开输出文件夹 |
| 文件保护 | 遇到同名文件停止，不覆盖已有文件 |

## 两个常见设置

### 编号位数是什么？

它决定文件名中数字的最小长度，只影响命名，不影响图片质量。

| 设置 | 文件名示例 |
| --- | --- |
| 前缀 `截图`，2 位 | `截图_01.png`、`截图_02.png` |
| 前缀 `截图`，3 位（默认） | `截图_001.png`、`截图_002.png` |

编号超过设置的位数会自然增长，不会截断或重复。

### 保留重叠区域是什么？

下一张图片开头会重复上一张末尾的一小段内容。这样，文字被切到两张图片的边缘时，更容易接着阅读。文字长截图可保留默认的 **100px**；不需要重复内容时取消勾选。

例如原图高度 **8000px**，切片高度 **4000px**：

| 设置 | 切片范围（从 0 开始，含起点、不含终点） |
| --- | --- |
| 无重叠 | `[0, 4000)`、`[4000, 8000)`，共 2 张 |
| 重叠 100px | `[0, 4000)`、`[3900, 7900)`、`[7800, 8000)`，共 3 张 |

重叠像素必须小于切片高度。重叠可能增加切片数量；上一张已经到达底部时，不再生成冗余尾片。

## 输出格式与限制

- **默认 PNG**：无损保存解码后的像素，不缩放；输入 JPEG 已经丢失的细节无法恢复。
- **原格式输出**：PNG 无损，WEBP 使用无损编码；JPEG 以质量 95 重新编码，仍会产生有损压缩。
- **图片方向与颜色**：按文件原始像素方向切分，不自动应用 EXIF 旋转。保留 ICC 色彩配置，不复制 EXIF/GPS 元数据。CMYK 转 PNG 时会转换到 RGB。
- **超大图片**：原图只打开一次，每次处理一个切片，不把全部切片同时留在内存。但 Pillow 通常仍需要解码整张图片，因此内存占用会随原图大小增长，并非恒定内存的流式裁切。为支持超长图取消了默认像素上限，请使用可信的本地图片。
- **不支持动画与多帧图片**。WEBP 等编码器也可能限制输出尺寸，保存失败会提示错误。
- **失败与重试**：已完成的切片保留，当前失败切片会清理。请根据提示修正设置，或换前缀、换目录后重试。
- **预览限制**：超过 5000 万像素时跳过缩略图，仍可正常切分；切片过多时仅显示部分边界，实际导出包含全部切片。预览缩放不影响输出像素。
- 切分期间锁定设置，请等待完成后关闭。生成预览时也会暂时禁用开始按钮，避免预览与切分同时解码大图。

## 从源码运行

需要 Python 3.10+，且包含 tkinter。唯一第三方运行依赖为 Pillow。

```powershell
git clone git@github.com:Absorbed-wsy/LongScreenshotSplitter.git
cd LongScreenshotSplitter
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

无终端启动可双击 `launch.vbs`，它使用项目 `.venv` 中的 `pythonw.exe`。`run.bat` 为兼容入口，可能短暂闪过终端后退出；希望完全不显示终端时请使用 EXE 或 `launch.vbs`。

## 构建 Windows EXE

在 Windows x64 上创建上述 `.venv` 后运行：

```powershell
.\build.bat
```

脚本安装独立的构建依赖，再生成：

```text
dist/LongScreenshotSplitter-v0.2-windows-x64.exe
```

打包使用 [PyInstaller](https://pyinstaller.org/en/stable/usage.html) 的单文件、无控制台模式。构建依赖不影响源码运行时仅依赖 Pillow 的要求。

## 测试

```powershell
.venv\Scripts\python.exe -m unittest -v test_splitter.py test_gui.py
```

23 项测试覆盖切片边界、重叠、像素一致性、透明度、输入格式、同名文件保护、保存失败清理，以及真实 Tk 窗口中的后台任务、快速切换图片、参数校验、忙碌保护和失败恢复。GUI 测试需要可用的桌面会话。

对打包后的 EXE 进行独立自测：

```powershell
Start-Process -FilePath .\dist\LongScreenshotSplitter-v0.2-windows-x64.exe -ArgumentList '--self-test self-test.json' -Wait
Get-Content .\self-test.json
```

自测只使用临时生成的图片，成功时报告包含 `"ok": true` 和 `"frozen": true`。它检查打包后的 Tk、版本与图标、四种输入格式、预览、PNG 和原格式编码、后台切分、像素一致性，以及同名冲突后的恢复。

也可以运行 `.\verify-release.ps1`，自动核对 EXE 版本、执行自测，并在 `dist/` 生成 `self-test.json` 和 `SHA256SUMS.txt`。

## 发布流程

`.github/workflows/release.yml` 在推送 `v*` 标签时执行 Windows x64 回归测试、构建、EXE 自测与发布。发布前同步 `main.py`、`version_info.txt`、`build.bat` 中的版本号和 `docs/releases/<标签>.md` 更新说明；更新自测中的预期版本。只有全部验证成功后才公开 Release，附件包括 EXE、SHA-256 校验文件和自测报告。

## 项目结构

```text
main.py                 界面和切分逻辑
selftest.py             打包后的程序自测
test_splitter.py         核心功能测试
test_gui.py              GUI 测试
requirements.txt        运行依赖
requirements-build.txt  构建依赖
build.bat               Windows 打包脚本
verify-release.ps1      发布包验证与校验文件生成
version_info.txt        EXE 版本信息
assets/                 软件图标与设计提示词
docs/releases/          各版本发布说明
.github/workflows/      自动构建与发布流程
launch.vbs              源码无终端启动入口
run.bat                 兼容启动入口
CHANGELOG.md            更新日志
LICENSE                 仓库原有许可证
```

## 许可证

沿用本仓库的 [GNU AGPL v3 许可证](LICENSE)。
