@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create .venv first: python -m venv .venv
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --noupx --name LongScreenshotSplitter-v0.2-windows-x64 --version-file version_info.txt --icon assets/app-icon.ico --add-data "assets/app-icon.png;assets" --add-data "assets/app-icon.ico;assets" main.py
exit /b %errorlevel%
