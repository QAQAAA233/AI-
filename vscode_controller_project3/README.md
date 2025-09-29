# AI 自動化開發控制器 Pro v3.2

AI 自動化開發控制器 Pro 是一套整合 Gemini AI 與 VS Code 自動化能力的桌面輔助工具。最新版本針對後端重新模組化，將高頻共享變量集中管理，避免跨檔案重複儲存，並補強偵錯與日誌資訊，協助開發者快速定位問題。

## 🔧 核心特色

- **單一來源的資料模型**：所有 JSON 解析、專案結構與目錄設定皆集中於 `core.py`，確保 AI 回應的重點資訊不再分散。
- **明確的服務分層**：
  - `services.py` 專責設定檔存取與 Gemini API 呼叫。
  - `automation.py` 提供 VS Code 操控、程式執行、螢幕擷取與整體流程管理。
  - `app.py` 僅負責 Flask/Webview 入口與 API 路由，維持總檔案數量不超過 5。
- **強化偵錯訊息**：流程關鍵步驟皆納入結構化日誌與錯誤說明，包含 AI 解析失敗時的可能原因與排錯建議。
- **變量單點維護**：常用狀態（如螢幕截圖路徑、視窗標題、伺服器資訊）只在後端建立一次並全程沿用，避免跨層重複傳遞造成不一致。

## 📁 專案結構

```text
vscode_controller_project3/
├── app.py                # Flask + Webview 入口
├── automation.py         # VS Code、自動化流程、螢幕擷取與程式管理
├── core.py               # 日誌設定、資料模型、JSON 解析工具
├── services.py           # 配置存取與 Gemini API 客戶端
├── requirements.txt      # 套件需求
├── templates/
│   └── index.html        # 前端介面
└── ~/.ai_controller_v3/  # 執行時自動建立的資料目錄
    ├── config.json       # 使用者設定
    ├── logs/             # 日誌檔案
    ├── projects/         # 生成專案
    └── screenshots/      # 螢幕截圖
```

> 📌 **檔案數量限制**：核心邏輯集中在四個 Python 檔案內，符合「不超過 5 個代碼檔案」的需求。

## 🚀 安裝與啟動

1. **建立虛擬環境並安裝依賴**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows 使用 .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **設定 Gemini API**
   - 於介面設定頁輸入 API Key，或
   - 透過 `gcloud auth application-default login` 設定 Google Cloud 憑證。

3. **啟動系統**
   ```bash
   python app.py
   ```
   Flask 伺服器會在背景啟動，並透過 PyWebview 開啟桌面視窗。

## 🧭 操作流程

1. **選擇專案資料夾**：於主控制台點擊「瀏覽」，選定生成程式碼要儲存的位置。
2. **撰寫 AI 指令**：輸入需求描述，可一併宣告安裝需求（例：`pip install fastapi`）。
3. **執行自動化**：
   - 呼叫 Gemini 產出 JSON 化專案結構。
   - 安裝依賴並寫入檔案。
   - 自動啟動 VS Code 並開啟核心檔案。
   - 如主檔案會啟動視窗或網頁，系統會紀錄 PID、開啟網址並擷取畫面。
4. **擷取截圖**：可指定視窗標題或專案名稱，後端會在完成程式啟動後統一擷取，避免前端重複回填變量。

## 🧱 模組詳解

### `core.py`
- 定義日誌設定與執行資料夾。
- 集中 `AIConfig`、`FileOutput`、`ProjectOutput`、`ProcessResult` 等資料模型。
- 提供 JSON Schema、系統指令、安裝與檔案儲存工具，確保解析後的資料維持單一來源。

### `services.py`
- `ConfigManager`：負責讀寫 `config.json`，寫入時使用 `asdict` 確保結構一致。
- `GeminiAI`：封裝 API Key 與 Google Cloud Auth 兩種連線方式，並依回應模式切換生成參數。

### `automation.py`
- `VSCodeController`：啟動 VS Code、搜尋視窗與自動開啟多個檔案。
- `ScreenCapture`：以 PyWinCtl + MSS 擷取指定視窗，統一由後端儲存檔名與路徑。
- `ProgramManager`：追蹤與終止子行程，並提供 PID、執行狀態與運行時間。
- `ProcessManager`：整合呼叫 AI、解析、安裝、寫檔、啟動程式、擷取畫面等完整流程，若解析失敗會給出建議與偵錯資訊。

### `app.py`
- 建立 Flask 路由與 PyWebview 視窗。
- 轉交請求給服務與自動化模組，確保路由層僅負責資料整合與回應序列化。

## 🛠 偵錯與日誌

- 所有模組共用 `core.py` 初始化的 `logger`，輸出格式包含時間戳與級別。
- `ProcessManager` 在每個主要步驟皆有 `Step` 紀錄；解析失敗時會回傳「解析錯誤」區塊，包含可能原因與建議。
- `ProgramManager` 會把執行中的程式以 PID 為 key 儲存在單一定義的字典內，並提供 `/running-programs` API 查詢。

## 🐛 常見問題

| 問題 | 可能原因 | 建議處理 |
| --- | --- | --- |
| 無法找到 VS Code 視窗 | `code` 指令未加入 PATH 或啟動時間過長 | 執行 `code --version` 確認；視情況增加等待時間 |
| JSON 解析失敗 | 模型輸出非預期格式 | 檢查 `result.output` 內的錯誤說明，改用文本模式或調整提示 |
| 螢幕截圖為空 | 視窗尚未建立或標題不符 | 於擷取 API 加入正確的視窗標題，或延長等待時間 |

## ✅ 測試建議

1. **API Key 模式**：輸入有效 Key，建立簡單 Python 專案。
2. **Google Auth 模式**：以 `gcloud` 登入後，確認能生成專案並啟動 VS Code。
3. **GUI/Web 專案**：測試會開啟視窗的程式，確認自動擷取畫面與 PID 管理功能。

---

如需延伸或整合其他自動化流程，可在既有模組內擴充，並持續遵循「核心變量集中、檔案數量精簡、完整偵錯資訊」的設計原則。
