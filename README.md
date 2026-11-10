# Video Downloader

Windows 繁體中文影音與文件工具：下載 YouTube／Shorts 影音，也能在本機轉換文件與圖片。

## 下載 App

[![下載 Windows 版](assets/download-windows.svg)](https://github.com/SKYMOPK/video-downloader-updates/releases/download/v0.3.2/VideoDownloader-0.3.2-win64-setup.exe)

**點上方藍色按鈕，下載後開啟安裝檔即可。**

目前版本：**0.3.2** · 一般使用者只需下載這一個安裝檔，不必下載 ZIP、原始碼或其他檔案。

安裝完成後，日後可在 App 內按「檢查更新」。

[查看更新內容與其他版本](https://github.com/SKYMOPK/video-downloader-updates/releases/latest)

需要 Windows 10（組建 19041 以上）或 Windows 11，x64。安裝後不需要另裝 Python 或 Office。

## App 更新

從 0.2.0 開始，主畫面「檢查更新」可更新整個 App：

- 啟動後背景檢查，有新版顯示紅點與一次性提示。
- 顯示版本、更新內容與實際下載進度，可取消更新。
- 等現有工作完成後安裝，保留設定、下載紀錄與檔案。
- 新版無法正常建立主視窗時，回復原版本。

設定內的「檢查核心更新」則只更新 yt-dlp，兩者分開。

## 目前功能

- YouTube／Shorts 影片與音訊下載。
- 依清晰度整理畫質選項，保留來源提供的高幀率。
- MP4、MKV、相容 WebM；音訊原始、MP3、M4A、Opus、WAV。
- 任務佇列、取消、重試、續傳暫存、完成通知及輸出驗證。
- 網址欄支援 Ctrl+V、右鍵貼上與自動解析。

### 文件轉換

- 拖曳或選擇檔案，自動辨識格式，只顯示可用的輸出選項。
- Word、Excel、PowerPoint 與 OpenDocument 文件轉 PDF。
- Word、ODT、RTF 與 TXT 的合理格式轉換。
- 圖片轉檔、調整順序並合併 PDF；PDF 轉逐頁圖片或擷取純文字。
- 批次處理、取消、結果驗證及同名保護；原始檔案保留。
- 轉換工作區位於 App 資料位置，輸出位置不會建立暫存資料夾；多頁圖片直接儲存在輸出位置。轉換結束後清理暫存，異常中斷後會在下次啟動時嘗試清理。

文件轉換在本機進行，無須上傳文件或另裝 Office。第一次使用 Office 轉換時會在背景準備內建引擎，約需 1.8 GB 可用空間，開啟 App 不等待此步驟。

單檔上限 **100 MB**、純文字 **10 MB**，PDF／圖片最多 **200 頁**。不提供 PDF 轉 Word、OCR、加密文件、巨集與動畫轉換。特殊字型與複雜版面可能有差異。

來源平台限制可能影響影音可下載性，請僅處理你有權下載的內容。

## 發布檔案

- `win64-setup.exe`：首次安裝。
- `win64-update.zip`：供 App 內更新使用，也可完整解壓至獨立資料夾執行。
- `source.zip`：對應版本的原始碼、建置說明與測試紀錄。
- `SHA256.json`：檔案完整性資訊。

程式透過固定 GitHub 發布位置的 HTTPS 與 SHA256 檢查更新包；目前未提供開發者數位簽章。實際驗證範圍與技術限制請見原始碼內的 `docs/VALIDATION.md`。

第三方元件的授權與來源列在原始碼的 `THIRD_PARTY_NOTICES.md`；隨附 FFmpeg 等工具保留各自授權。
