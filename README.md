# Video Downloader

Windows 繁體中文影音下載器，支援 YouTube 一般影片與 Shorts，下載影片或音訊到電腦。

## 下載 App

[![下載 Windows 版](assets/download-windows.svg)](https://github.com/SKYMOPK/video-downloader-updates/releases/download/v0.2.0/VideoDownloader-0.2.0-win64-setup.exe)

**點上方藍色按鈕，下載後開啟安裝檔即可。**

目前版本：**0.2.0** · 一般使用者只需下載這一個安裝檔，不必下載 ZIP、原始碼或其他檔案。

安裝完成後，日後可在 App 內按「檢查更新」。

[查看更新內容與其他版本](https://github.com/SKYMOPK/video-downloader-updates/releases/latest)

需要 Windows 10（組建 19041 以上）或 Windows 11，x64。安裝後不需要另裝 Python。

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

文件格式轉換尚未加入。來源平台限制可能影響可下載性，請僅處理你有權下載的內容。

## 發布檔案

- `win64-setup.exe`：首次安裝。
- `win64-update.zip`：供 App 內更新使用，也可完整解壓至獨立資料夾執行。
- `source.zip`：對應版本的原始碼、建置說明與測試紀錄。
- `SHA256.json`：檔案完整性資訊。

程式透過固定 GitHub 發布位置的 HTTPS 與 SHA256 檢查更新包；目前未提供開發者數位簽章。實際驗證範圍與技術限制請見原始碼內的 `docs/VALIDATION.md`。

第三方元件的授權與來源列在原始碼的 `THIRD_PARTY_NOTICES.md`；隨附 FFmpeg 等工具保留各自授權。
