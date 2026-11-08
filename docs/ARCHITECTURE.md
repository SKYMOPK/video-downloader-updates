# 架構決策：PySide6 + QML

日期：2026-11-09。這份決策依據本機實際工具鏈與產品用途，不把框架的一般宣傳數字當成本產品量測。

## 比較與選擇

1. **視覺能力**：QML 與 React 均能滿足深色設計系統、動畫與自訂元件。本專案採 QML，保留原生視窗操作，避免自行重製 Windows 標題列細節。
2. **操作流暢度**：兩者都需要將下載與轉換移出 UI 工作。此實作使用非同步 QProcess，核心、FFmpeg 及 runtime 各自執行，更新網路工作另用 QThread。
3. **Windows 整合**：Qt 提供視窗、檔案對話框、通知與 DPI 支援；Tauri 提供對應插件與 WebView2。此處 Qt 可用同一套 API 接合 Python 任務管理。
4. **記憶體及 CPU**：不假定 Qt 必定較省或 Tauri 必定較快。量測實際主程序與子程序；下載數預設 1、最多 3，重新編碼另限制一次 1 項。
5. **啟動**：PyInstaller 採資料夾式封裝，避免每次啟動都解壓大型工具的一檔式設計。Tauri 亦可快速啟動，但需處理 WebView2 首次部署。
6. **大小**：本產品包含 Deno 及兩個靜態 FFmpeg 工具，核心工具已占相當大小；單比較 GUI 框架空殼沒有意義。記錄完整產物大小，後續可評估 shared FFmpeg，但不得未驗證就更換部署形式。
7. **yt-dlp 整合**：採官方 Windows 執行檔及結構化進度輸出；與 Python API 相比，方便獨立更新和中止整個工作，不會在 App 程序內污染匯入狀態。Tauri 也能採同一 sidecar 方法，但需多一層 Rust／TypeScript 通訊與資料模型維護。
8. **依賴部署**：yt-dlp、Deno、FFmpeg、FFprobe 全部使用受控明確路徑，不依賴 PATH。官方 yt-dlp 執行檔的 EJS 配置依所選版本官方說明；本機已驗證解析成功。
9. **核心更新**：版本化目錄與原子 active pointer，先下載、雜湊及啟動檢查再切換；保留隨附版本及舊版本。未將同源雜湊描述為獨立密碼學簽章驗證。
10. **Skills**：unslop 用於留白、配色、圖示與視覺檢查；computer-use 用於原生視窗、模式切換與設定檢查。沒有假設存在特定桌面開發 Skill。
11. **維護成本**：本機有 uv、Python 與 Node，沒有現成 Rust 工具鏈。兩個方案皆可開發，但 Qt 可減少本專案需維護的語言與通訊邊界，因此選擇 PySide6 + QML。
12. **封裝可靠性**：先完成 PyInstaller 封裝及真實下載流程。早期測試發現宿主 Poppler 的 ICU DLL 被誤收；透過明確隔離建置 PATH 與排除錯誤 ICU 修正。Inno Setup 產生一般使用者安裝包。

## 邊界與資料流

- `app/formats.py`：純資料整理、網址驗證、編碼／容器相容性與明確輸出計畫。
- `app/storage.py`：原子 JSON 保存、固定工具位置、檔名與不覆蓋落檔。
- `app/process.py`：QProcess、逾時、Windows Job Object 與程序樹生命週期。
- `app/engine.py`：來源重新確認 → 下載 → 合併／轉換 → FFprobe → 安全落檔。
- `app/controller.py`：UI 介面、任務模型、佇列、設定、恢復、通知、轉碼排程。
- `app/updater.py`：明確發起的官方核心檢查、下載、驗證及版本切換。
- `app/app_updates.py`：整個 App 的 GitHub 版本檢查、提示快取、可取消下載與外部更新交接。
- `app/update_protocol.py`：正式版比較、來源及完整更新包驗證。
- `app/update_helper.py`：獨立執行檔，等待 App 退出、替換完整目錄、啟動驗證與失敗回復。詳細發布流程見 `APP_UPDATES.md`。
- `qml/`：Tokens、共用元件與主介面，沒有下載引擎實作。

每個下載保存自己的來源及規格快照。新解析有輪次識別，舊解析完成不能覆蓋新來源。下載百分比只描述當前來源串流；後處理另顯示階段，不偽造整體百分比。

## 品質方向與初始預算

產品：偶爾使用、只需貼網址與選規格的本機影音工具。

性格：沉穩、準確、克制。素材世界是影片封面與媒體檔案，介面採中性石墨灰，藍色只標記主要操作及處理狀態。來源縮圖承擔畫面的色彩；下載階段文字是貫穿任務區的辨識細節。

一般視窗 1120 × 850，最小 900 × 640 邏輯像素；內容較長時使用捲動。以 100%、125%、150% 有效 DPR 檢查。

初始效能預算（以目前開發電腦測試，非跨硬體保證）：

- 冷啟動至主視窗可建立，目標 3 秒內。
- 初始化結束後閒置平均 CPU 目標低於單一邏輯核心 1%。
- 閒置主程序記憶體目標低於 300 MiB，不含系統共享資源重複計算。
- 完整安裝大小初始上限 600 MiB；不得以忽略大型 sidecar 美化數字。
- 取消後目標 3 秒內終止相關程序樹；實際逾時由測試證據記錄。

未達預算時先調查，任何調整需記錄理由。不同硬體、系統、顯示驅動與防毒環境的量測不能直接混為同一結果。

## 官方文件

- [Qt for Python deployment](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)
- [Qt high DPI testing](https://doc.qt.io/qt-6/highdpi.html)
- [yt-dlp EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
- [Tauri Windows deployment](https://v2.tauri.app/distribute/windows-installer/)
