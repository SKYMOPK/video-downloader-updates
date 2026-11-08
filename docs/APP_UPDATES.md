# 整個 App 的更新與發布

此機制更新 Video Downloader 的介面、Python 程式與隨附元件。與 `app/updater.py` 的 yt-dlp 核心更新分開。

## 正式更新來源

固定倉庫：`SKYMOPK/video-downloader-updates`。一般使用者不需要 GitHub 帳號，也不會在 App 內保存 GitHub Token。

版本號使用三段式數字，識別檔在 `app/release.json`。正式版不接受 prerelease 或 draft。比對版本使用數值順序，不以字串或檔案時間判斷。

GitHub Release 必須包含 `VideoDownloader-<版本>-win64-update.zip`，其 Release Asset 必須具有 GitHub 提供的 `sha256:` digest。程式只接受該倉庫對應 tag 的固定下載位置。下載採串流寫入，驗證大小與 SHA256，限制大小、逾時及 HTTPS 重新導向來源。

## 使用者體驗

啟動後延遲檢查，不阻擋主畫面。成功檢查快取六小時，手動檢查可立即重新查詢。同一新版只自動提示一次，稍後仍保留紅點。設定可關閉自動檢查與提示視窗。

下載更新時可取消。確認更新後不接受新的解析／下載任務，既有工作繼續執行；待佇列、解析、核心更新與工具啟動檢查結束，再準備安裝。關閉 App 時會先取消仍在執行的更新網路工作，避免 QThread 在使用中被銷毀。

## 安裝交易

1. 將獨立、無 Qt 的 `app-updater.exe` 複製到本機 App 資料目錄，讓它不占用要替換的程式資料夾。
2. 更新程式再次驗證更新 ZIP。所有檔案限定在 `VideoDownloader/` 下，不允許路徑穿越、Windows 保留檔名、重複檔名、符號連結或加密項目。
3. 在安裝位置的同一磁碟建立暫存資料夾。驗證產品 ID、版本、完整檔案清單及每個檔案的 SHA256。
4. 準備成功後寫入交接狀態，原 App 保存紀錄後結束。更新程式以 Windows 程序 Handle 等待原程序退出。
5. 保留非程式管理的自建檔案及 Inno Setup 解除安裝資訊；若與新版檔案衝突則中止，不覆蓋。
6. 原安裝資料夾改名為帶有唯一識別碼的備份，新版資料夾原子改名至原位置。既有捷徑不需要更新。
7. 新版建立 QML 主視窗後回傳啟動驗證。若 45 秒內無回應或退出，更新程式還原舊版並重新開啟。

啟動驗證代表主視窗可建立，不代表所有網站與功能皆已驗證。磁碟故障、斷電、其他程式鎖住檔案或防毒隔離可能影響自動回復；交接狀態保存在 `%LOCALAPPDATA%\VideoDownloader\app-updates\<工作>\result.json`。完整前版保留於安裝資料夾旁，未自動刪除其中可能有的使用者檔案。

## 發布步驟

1. 修改 `app/release.json` 的版本，同步 `pyproject.toml`，執行 `uv lock`。
2. 更新更新說明，執行 `scripts/build.ps1`，包含測試、工具校驗、獨立更新程式、App、完整更新包與安裝包。
3. 在隔離資料目錄執行真實更新與失敗回復驗收，保留證據。
4. 執行 `scripts/release_inventory.py`，產生原始碼 ZIP 與 `dist/SHA256.json`。
5. 在 GitHub 建立對應 `v<版本>` 的 Release 草稿，上傳安裝包、更新包、原始碼 ZIP、SHA256.json，確認所有檔案上傳完成才正式發布。
6. 確認 GitHub API 提供更新包的 SHA256 digest；以已發布的正式版檢查確認顯示「目前已是最新版本」。

App 更新不會讀取 GitHub 預設分支的零散檔案，也不會將開發過程中的 commit 自動推送到使用者電腦。
