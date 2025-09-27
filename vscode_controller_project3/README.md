# AI 自動化開發控制器 Pro v2.0

## 🚀 專案簡介

AI 自動化開發控制器 Pro 是一個整合了 Gemini AI 與 VS Code 自動化控制的智能開發助手。本專案透過獨立桌面視窗提供友善的操作介面，能夠自動生成程式碼、管理專案檔案、監控執行狀態，並支援螢幕擷取功能。

## ✨ 新版本特色 (v2.0)

### 前端改進
- **🎨 全新設計的明亮美觀界面**
  - 採用現代化的漸層配色方案（藍紫色系）
  - 卡片式布局設計，視覺層次分明
  - 動畫效果提升互動體驗
  - 響應式設計，支援不同螢幕尺寸

- **📊 多標籤頁管理系統**
  - 主控制台：核心功能操作
  - 設定頁面：完整的配置管理
  - 監控頁面：即時查看執行狀態
  - 自動化頁面：工作流程設定

- **🔄 即時狀態指示器**
  - 系統狀態即時顯示
  - 載入動畫與進度提示
  - 操作結果視覺化反饋

### 後端改進
- **📦 模塊化架構設計**
  - ConfigManager：配置文件管理
  - GeminiAI：AI API 整合
  - VSCodeController：VS Code 自動化控制
  - ScreenCapture：螢幕擷取功能
  - CodeProcessor：程式碼解析處理
  - TerminalMonitor：Terminal 輸出監控
  - ProcessManager：主流程管理

- **📝 完整的日誌系統**
  - 結構化日誌記錄
  - 時間戳記與級別標記
  - 錯誤追蹤與除錯支援

- **🛡️ 增強的錯誤處理**
  - 全面的異常捕獲
  - 友善的錯誤訊息
  - 失敗恢復機制

### 新增功能
- **📸 螢幕擷取功能 (使用 MSS)**
  - 支援多螢幕擷取
  - 特定視窗擷取（如 VS Code）
  - 截圖自動儲存與管理
  - 預覽功能整合

- **🔍 VS Code 操作透明性**
  - 詳細的操作步驟記錄
  - 視窗狀態即時追蹤
  - 文件開啟確認機制

- **⚡ Terminal 監控優化**
  - 執行超時控制（避免無限等待）
  - 輸出緩衝區管理
  - 錯誤輸出分離
  - 退出碼檢測

## 🔧 系統需求

- Python 3.8 或更高版本
- Visual Studio Code（需將 `code` 命令加入 PATH）
- Windows 10/11、macOS 10.14+ 或 Linux（Ubuntu 20.04+）
- Gemini API Key 或 Google Cloud 憑證

## 📦 安裝指南

### 步驟 1: 克隆專案
```bash
git clone https://github.com/your-repo/ai-controller-pro.git
cd ai-controller-pro
```

### 步驟 2: 建立虛擬環境
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 步驟 3: 安裝依賴套件
```bash
pip install -r requirements.txt
```

### 步驟 4: 配置 API 連接

#### 方式 A：使用 API Key
1. 訪問 [Google AI Studio](https://aistudio.google.com/app/apikey)
2. 獲取您的 Gemini API Key
3. 在應用程式設定中輸入 Key

#### 方式 B：使用 Google Cloud Auth
```bash
# 安裝 gcloud CLI 後執行
gcloud auth application-default login
```

## 🎮 使用說明

### 啟動應用程式
```bash
python app.py
```

### 基本操作流程

1. **選擇專案資料夾**
   - 點擊「瀏覽」按鈕選擇您的專案目錄

2. **輸入 AI 指令**
   - 在文字框中描述您需要的功能
   - 支援安裝指令格式：`;;;pip install package;;;`
   - 檔案名稱格式：`/*/filename.py/*/`

3. **執行自動化**
   - 點擊「執行 AI 自動化」按鈕
   - 系統將自動：
     - 呼叫 Gemini AI 生成程式碼
     - 安裝所需套件
     - 創建並儲存檔案
     - 啟動 VS Code 並打開檔案
     - 執行並監控程式

4. **螢幕擷取**
   - 點擊「擷取螢幕畫面」按鈕
   - 自動擷取所有螢幕和 VS Code 視窗
   - 截圖儲存在 `~/.ai_controller_v2/screenshots/`

## 📁 專案結構

```
ai_controller_pro/
│
├── app.py                  # 主程式（後端）
├── requirements.txt        # Python 套件列表
├── README.md              # 本說明文件
│
├── templates/
│   └── index.html         # 前端界面
│
└── .ai_controller_v2/     # 配置和數據目錄（自動創建）
    ├── config.json        # 使用者配置
    ├── screenshots/       # 螢幕截圖
    └── logs/             # 執行日誌
```

## ⚙️ 進階配置

### 生成參數調整
- **Temperature (0-2)**：控制輸出的隨機性
- **Top-P (0-1)**：核心採樣參數
- **Top-K (1-100)**：候選詞彙數量
- **Max Tokens**：最大輸出長度

### 自動化設定
- **自動錯誤修正**：檢測並修正執行錯誤
- **自動程式碼優化**：改善程式碼品質
- **自動測試執行**：執行單元測試
- **監控間隔**：設定檢查頻率

## 🔐 安全性考量

1. **檔案名稱驗證**
   - 禁止路徑遍歷攻擊
   - 過濾特殊字符

2. **程式執行控制**
   - 超時機制防止無限循環
   - 進程隔離執行
   - 資源使用限制

3. **API 金鑰保護**
   - 本地儲存加密（建議）
   - 支援環境變數配置

## 🐛 故障排除

### 問題：找不到 VS Code
**解決方案**：確保 `code` 命令已加入 PATH
```bash
# 測試命令
code --version
```

### 問題：螢幕擷取失敗
**解決方案**：檢查 mss 套件安裝
```bash
pip install --upgrade mss
```

### 問題：AI 回應格式錯誤
**解決方案**：確保提示詞包含正確格式指示
- 程式碼：\`\`\`python ... \`\`\`
- 檔案名：/*/filename.py/*/
- 安裝指令：;;;pip install package;;;

## 📈 未來規劃

- [ ] 支援更多 IDE（IntelliJ IDEA、Sublime Text）
- [ ] 整合版本控制（Git 自動提交）
- [ ] 支援多語言程式碼生成
- [ ] 加入程式碼審查功能
- [ ] 實現分散式執行
- [ ] 添加 Web API 介面
- [ ] 整合 CI/CD 流程
- [ ] 支援團隊協作功能

## 🤝 貢獻指南

歡迎提交 Pull Request 或開啟 Issue！

1. Fork 本專案
2. 創建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 開啟 Pull Request

## 📄 授權協議

本專案採用 MIT 授權協議 - 詳見 [LICENSE](LICENSE) 文件

## 🙏 致謝

- Google Gemini AI 團隊
- PyAutoGUI 和 PyGetWindow 開發者
- MSS 螢幕擷取庫作者
- Flask 和 pywebview 社群

## 📞 聯絡方式

- 專案網站：[https://your-project-site.com](https://your-project-site.com)
- 問題回報：[GitHub Issues](https://github.com/your-repo/issues)
- 電子郵件：contact@your-domain.com

---

**注意事項**：
- 本專案為教育和研究目的開發
- 使用時請遵守相關法律法規
- AI 生成的程式碼需要人工審查
- 建議在虛擬環境或容器中執行未經測試的程式碼

**版本歷史**：
- v2.0.0 (2024-11) - 全面改版，新增螢幕擷取和自動化功能
- v1.0.0 (2024-10) - 初始版本發布