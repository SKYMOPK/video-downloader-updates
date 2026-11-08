# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
datas = [(str(root / "qml"), "qml"), (str(root / "assets"), "assets"),
         (str(root / "app" / "release.json"), "app"),
         (str(root / "tools" / "manifest.json"), "tools"),
         (str(root / "tools" / "LICENSE"), "tools"),
         (str(root / "THIRD_PARTY_NOTICES.md"), ".")]
datas += collect_data_files("PySide6", subdir="qml", excludes=["**/objects-Debug/**", "**/objects-Release/**", "**/*.cpp", "**/*.obj", "**/*.pdb"])
binaries = [(str(root / "tools" / name), "tools") for name in ("yt-dlp.exe", "deno.exe", "ffmpeg.exe", "ffprobe.exe")]
binaries.append((str(root / "build" / "updater-dist" / "app-updater.exe"), "tools"))
a = Analysis([str(root / "main.py")], pathex=[str(root)], binaries=binaries, datas=datas,
             hiddenimports=["PySide6.QtQuick", "PySide6.QtQuickControls2", "PySide6.QtSvg", "PySide6.QtNetwork"],
             excludes=["tkinter", "PySide6.QtPdf", "PySide6.QtTest"], noarchive=False)
# Qt on supported Windows uses the OS ICU ABI. A foreign Poppler/Conda ICU on
# the build host PATH can shadow it and exports suffixed, incompatible symbols.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in ("icuuc.dll", "icudt78.dll")]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VideoDownloader", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / "assets" / "app.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VideoDownloader")
