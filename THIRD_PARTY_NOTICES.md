# 第三方元件

本軟體由使用者本機執行，下載元件不代表來源影片的使用授權。請依來源授權、適用法律與平台規則使用。

實際下載元件的版本、官方取得位置及 SHA256 記錄於 `tools/manifest.json`。Python 套件版本見 `requirements-lock.txt`。

- Qt / PySide6 / Shiboken6：Qt 公司與貢獻者；依實際模組採 LGPLv3 或其適用授權。使用動態 Qt libraries，未修改 Qt。授權與來源入口：[Qt licensing](https://www.qt.io/licensing/)、[Qt for Python source](https://code.qt.io/pyside/pyside-setup.git/)。發行物保留隨套件提供的授權文件，並允許依授權要求替換相容動態函式庫。不要對 Qt 元件加入限制使用者依其授權修改、替換或除錯的條款。
- Python：Python Software Foundation License。[授權](https://docs.python.org/3/license.html)、[原始碼](https://www.python.org/downloads/source/)。
- yt-dlp：原始專案採 Unlicense；官方 Windows 執行檔包含其他元件，其完整授權以該發行版本的第三方聲明為準。[專案與授權](https://github.com/yt-dlp/yt-dlp)、[第三方元件](https://github.com/yt-dlp/yt-dlp/blob/master/THIRD_PARTY_LICENSES.txt)。EJS 隨所選官方執行檔配置，依該發行版本的適用授權。
- Deno：MIT 及其第三方元件適用授權。[授權與原始碼](https://github.com/denoland/deno)。
- FFmpeg / FFprobe：此建置使用 Gyan essentials GPL build，GPLv3 及其隨附文件見 `tools/LICENSE`。原始碼與對應建置資料：[Gyan builds](https://www.gyan.dev/ffmpeg/builds/)、[FFmpeg](https://ffmpeg.org/)。完整對應來源與第三方配置應與重新散布的具體版本一併封存；不能僅以一般首頁取代散布時必要的來源義務。
- PyInstaller：GPLv2 或更新版，具有允許封裝應用程式的例外。[授權與例外](https://pyinstaller.org/en/stable/license.html)。
- 自製 SVG 操作圖示及 App 圖示：本專案程式產生。

UI 品質工作流程參考 unslop，Damir Sokolovsky，CC BY 4.0：[專案來源](https://heydamir.design/unslop)。此處為工作流程致謝，不表示 App 介面含該專案程式碼。

安裝程式使用 Inno Setup 6.7.4 建置。繁體中文翻譯取自 [Inno Setup 對應版本的翻譯檔](https://github.com/jrsoftware/issrc/blob/is-6_7_4/Files/Languages/Unofficial/ChineseTraditional.isl)，保留原作者聲明，並補齊該版本缺少的訊息翻譯。

目前產物供個人本機使用。對外重新散布前，需確認具體打包內容及完整授權／對應來源交付要求。此文件不代表已完成對外散布授權稽核。
