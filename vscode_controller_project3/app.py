"""
AI 自動化開發控制器 Pro v3.1 - 改進視窗檢測版本
功能：整合 Gemini AI 與 VS Code 自動化控制，支援 JSON 結構化輸出與多檔案專案
使用 PyWinCtl 改進視窗檢測和擷取功能
作者：AI Controller Development Team
版本：3.1.0
"""

import sys
import os
import subprocess
import threading
import time
import re
import json
import platform
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict, field
from enum import Enum

# Web framework imports
from flask import Flask, render_template, jsonify, request, send_file
import webview

# AI and automation imports
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold

# 改用 PyWinCtl 替代 pygetwindow
import pywinctl as pwc
import pyautogui
import pyperclip

# Screen capture imports
import mss
import mss.tools
from PIL import Image
import io
import base64

# 模糊字符串匹配
from difflib import SequenceMatcher

# Optional Google Cloud Auth support
try:
    import google.auth
    HAS_GOOGLE_AUTH = True
except ImportError:
    HAS_GOOGLE_AUTH = False

# ============================================
# 配置和常量
# ============================================

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Flask 配置
app = Flask(__name__)
HOST = '127.0.0.1'
PORT = 5001

# 系統配置
CONFIG_DIR = Path.home() / '.ai_controller_v3'
CONFIG_FILE = CONFIG_DIR / 'config.json'
SCREENSHOT_DIR = CONFIG_DIR / 'screenshots'
LOG_DIR = CONFIG_DIR / 'logs'
PROJECTS_DIR = CONFIG_DIR / 'projects'

# 確保必要目錄存在
for directory in [CONFIG_DIR, SCREENSHOT_DIR, LOG_DIR, PROJECTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ============================================
# 數據模型（保持不變）
# ============================================

class ResponseMode(Enum):
    """AI 回應模式"""
    TEXT = "text"
    JSON = "json"

class FileType(Enum):
    """支援的檔案類型"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    HTML = "html"
    CSS = "css"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CPP = "cpp"
    C = "c"
    GO = "go"
    RUST = "rust"
    RUBY = "ruby"
    PHP = "php"
    SWIFT = "swift"
    KOTLIN = "kotlin"
    SQL = "sql"
    SHELL = "shell"
    YAML = "yaml"
    JSON = "json"
    XML = "xml"
    MARKDOWN = "markdown"
    TEXT = "text"

@dataclass
class FileOutput:
    """單個檔案輸出結構"""
    filename: str
    filetype: str
    code: str
    opens_window: bool = False
    window_title: Optional[str] = None
    install_requirements: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    description: Optional[str] = None
    run_command: Optional[str] = None
    # 新增：前端應用支援
    is_web_app: bool = False
    can_open_standalone: bool = False
    server_address: Optional[str] = None
    web_title: Optional[str] = None

@dataclass
class ProjectOutput:
    """專案輸出結構（支援多檔案）"""
    project_name: str
    description: str
    files: List[FileOutput]
    main_file: Optional[str] = None
    setup_instructions: Optional[List[str]] = None
    run_instructions: Optional[List[str]] = None

@dataclass
class AIConfig:
    """AI 配置數據模型"""
    connection_method: str = "api_key"
    gemini_api_key: str = ""
    model_name: str = "gemini-2.5-pro"
    response_mode: str = "json"  # 新增：回應模式
    system_instruction: str = ""
    generation_params: Dict[str, Any] = None
    safety_settings: Dict[str, str] = None
    automation_settings: Dict[str, Any] = None

    def __post_init__(self):
        if self.generation_params is None:
            self.generation_params = {
                "temperature": 0.7,  # 降低溫度以獲得更一致的 JSON
                "top_p": 0.95,
                "top_k": 64,
                "max_output_tokens": 8192,
                "candidate_count": 1,
                "stop_sequences": [],
                "response_mime_type": "application/json" if self.response_mode == "json" else "text/plain"
            }
        if self.safety_settings is None:
            self.safety_settings = {
                "HARM_CATEGORY_HARASSMENT": "BLOCK_MEDIUM_AND_ABOVE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_MEDIUM_AND_ABOVE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_MEDIUM_AND_ABOVE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_MEDIUM_AND_ABOVE"
            }
        if self.automation_settings is None:
            self.automation_settings = {
                "auto_error_fix": False,
                "auto_optimize": False,
                "auto_test": False,
                "monitor_interval": 5
            }

@dataclass
class ProcessResult:
    """處理結果數據模型"""
    success: bool
    output: str = ""
    files_created: List[str] = field(default_factory=list)
    project_data: Optional[ProjectOutput] = None
    ai_response: str = ""
    ai_response_json: Optional[Dict] = None
    installation_logs: List[str] = field(default_factory=list)
    error: str = ""
    screenshots: List[str] = field(default_factory=list)

# ============================================
# JSON Schema 定義（保持不變）
# ============================================

def get_json_schema():
    """獲取 Gemini API 的 JSON Schema"""
    return {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "專案名稱"
            },
            "description": {
                "type": "string",
                "description": "專案描述"
            },
            "main_file": {
                "type": "string",
                "description": "主要執行檔案"
            },
            "setup_instructions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "設置指令"
            },
            "run_instructions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "執行指令"
            },
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "檔案名稱（含副檔名）"
                        },
                        "filetype": {
                            "type": "string",
                            "enum": ["python", "javascript", "html", "css", "typescript", "java", "cpp", "c", "go", "rust", "ruby", "php", "swift", "kotlin", "sql", "shell", "yaml", "json", "xml", "markdown", "text"],
                            "description": "檔案類型"
                        },
                        "code": {
                            "type": "string",
                            "description": "完整程式碼內容"
                        },
                        "opens_window": {
                            "type": "boolean",
                            "description": "是否會開啟視窗"
                        },
                        "window_title": {
                            "type": ["string", "null"],
                            "description": "視窗標題（如果有）"
                        },
                        "install_requirements": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "安裝需求（如 pip install package）"
                        },
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "相依套件"
                        },
                        "description": {
                            "type": "string",
                            "description": "檔案描述"
                        },
                        "run_command": {
                            "type": ["string", "null"],
                            "description": "執行命令"
                        },
                        "is_web_app": {
                            "type": "boolean",
                            "description": "是否為網頁應用"
                        },
                        "can_open_standalone": {
                            "type": "boolean",
                            "description": "主程式是否能自動開啟獨立瀏覽器視窗"
                        },
                        "server_address": {
                            "type": ["string", "null"],
                            "description": "伺服器地址（如 http://localhost:5000）"
                        },
                        "web_title": {
                            "type": ["string", "null"],
                            "description": "網頁標題"
                        }
                    },
                    "required": ["filename", "filetype", "code", "opens_window"]
                }
            }
        },
        "required": ["project_name", "description", "files"]
    }

def get_json_system_instruction():
    """獲取 JSON 模式的系統指令"""
    return """You are an expert coding assistant that generates complete, working code projects.

When responding, you MUST output a valid JSON object following this exact structure:
{
    "project_name": "descriptive_project_name",
    "description": "Brief description of what the project does",
    "main_file": "main.py",
    "setup_instructions": ["pip install package1", "pip install package2"],
    "run_instructions": ["python main.py", "Open browser to http://localhost:5000"],
    "files": [
        {
            "filename": "main.py",
            "filetype": "python",
            "code": "import flask\n\napp = flask.Flask(__name__)\n\n@app.route('/')\ndef home():\n    return 'Hello World'\n\nif __name__ == '__main__':\n    app.run()",
            "opens_window": false,
            "window_title": null,
            "install_requirements": ["pip install flask"],
            "dependencies": ["flask"],
            "description": "Main application file",
            "run_command": "python main.py",
            "is_web_app": true,
            "can_open_standalone": false,
            "server_address": "http://localhost:5000",
            "web_title": "My Web App"
        }
    ]
}

CRITICAL FORMATTING RULES:
1. The "code" field MUST contain properly formatted code with real newlines and indentation
2. Use actual newline characters (\\n) and tabs (\\t) in the code string, NOT literal \\n strings
3. Code must be valid JSON string - escape quotes properly
4. Ensure proper indentation is preserved in the code
5. Each line of code should be on its own line within the JSON string

WEB APPLICATION RULES:
1. Set "is_web_app": true for HTML files or server applications (Flask, Node.js, etc.)
2. Set "can_open_standalone": true ONLY if your code includes automatic browser opening:
   - Python: webbrowser.open() or Flask with app.run(debug=False, port=5000) + webbrowser
   - Node.js: using 'open' package or similar
   - HTML: if it's a standalone HTML that can be opened directly
3. If "can_open_standalone" is false but "is_web_app" is true, provide:
   - "server_address": the URL where the app will be served (e.g., "http://localhost:5000")
   - "web_title": the title of the web page
4. For standalone HTML files, set both opens_window and is_web_app to true
5. For server apps, the controller will handle opening a standalone browser window

IMPORTANT RULES:
1. Always generate COMPLETE, WORKING code - no placeholders or ellipsis
2. For GUI applications (pygame/tkinter), set window title to match the project name
3. For web apps, ensure the HTML has proper <title> tags
4. Include all necessary imports and error handling
5. Specify accurate file types (python, javascript, html, etc.)
6. Set opens_window to true for GUI apps OR standalone HTML files
7. List all package installation commands in install_requirements
8. Provide clear descriptions for each file
9. For multi-file projects, ensure files are properly linked

SUPPORTED FILE TYPES:
python, javascript, html, css, typescript, java, cpp, c, go, rust, ruby, php, swift, kotlin, sql, shell, yaml, json, xml, markdown, text

REMEMBER: 
- Output ONLY valid JSON, no additional text or markdown formatting
- Ensure code is properly formatted with correct indentation
- Use real newlines in code strings, not \\n text
- For web apps, think carefully about standalone browser window capability"""

# ============================================
# 配置管理模組（保持不變）
# ============================================

class ConfigManager:
    """配置文件管理器"""
    
    @staticmethod
    def load() -> AIConfig:
        """讀取配置文件"""
        if not CONFIG_FILE.exists():
            logger.info("配置文件不存在，使用默認配置")
            return AIConfig()
        
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return AIConfig(**data)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"讀取配置文件失敗: {e}")
            return AIConfig()
    
    @staticmethod
    def save(config: AIConfig) -> bool:
        """儲存配置文件"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(asdict(config), f, indent=4, ensure_ascii=False)
            logger.info("配置文件已儲存")
            return True
        except IOError as e:
            logger.error(f"儲存配置文件失敗: {e}")
            return False

# ============================================
# Gemini AI 模組（保持不變）
# ============================================

class GeminiAI:
    """Gemini AI API 管理器"""
    
    @staticmethod
    def configure(config: AIConfig) -> None:
        """配置 Gemini API 連接"""
        if config.connection_method == 'api_key':
            if not config.gemini_api_key:
                raise ValueError("API Key 模式需要提供有效的 API Key")
            genai.configure(api_key=config.gemini_api_key)
            logger.info("已使用 API Key 連接 Gemini")
            
        elif config.connection_method == 'gcloud_auth':
            if not HAS_GOOGLE_AUTH:
                raise ImportError("缺少 google-auth 套件，請執行: pip install google-auth")
            try:
                credentials, project_id = google.auth.default()
                genai.configure(credentials=credentials)
                logger.info(f"已使用 Google Cloud Auth 連接 (專案: {project_id})")
            except google.auth.exceptions.DefaultCredentialsError:
                raise ConnectionError(
                    "找不到 Google Cloud 憑證，請執行: gcloud auth application-default login"
                )
        else:
            raise ValueError(f"不支援的連接模式: {config.connection_method}")
    
    @staticmethod
    def generate_content(prompt: str, config: AIConfig) -> Tuple[str, Optional[Dict]]:
        """呼叫 Gemini API 生成內容"""
        try:
            # 配置連接
            GeminiAI.configure(config)
            
            # 準備生成配置
            gen_params = dict(config.generation_params)
            
            # 如果使用 JSON 模式
            if config.response_mode == "json":
                gen_params["response_mime_type"] = "application/json"
                # 使用 JSON 專用的系統指令
                system_instruction = get_json_system_instruction()
            else:
                gen_params["response_mime_type"] = "text/plain"
                system_instruction = config.system_instruction or get_json_system_instruction()
            
            gen_config = GenerationConfig(**{
                k: v for k, v in gen_params.items() if v is not None
            })
            
            # 準備安全設置
            safety_settings = {
                HarmCategory[category]: HarmBlockThreshold[threshold]
                for category, threshold in config.safety_settings.items()
            }
            
            # 創建模型實例
            model_name = f"models/{config.model_name}"
            logger.info(f"使用模型: {model_name}, 模式: {config.response_mode}")
            
            # 構建模型配置
            model_kwargs = {
                "model_name": model_name,
                "safety_settings": safety_settings
            }
            
            # 添加系統指令
            if system_instruction:
                model_kwargs["system_instruction"] = system_instruction
            
            # 如果是 JSON 模式且模型支援，添加 response_schema
            if config.response_mode == "json" and config.model_name in ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"]:
                try:
                    # 注意：實際使用時可能需要調整 schema 格式
                    model_kwargs["generation_config"] = gen_config
                except Exception as e:
                    logger.warning(f"無法設置 response_schema: {e}")
            
            model = genai.GenerativeModel(**model_kwargs)
            
            # 生成內容
            response = model.generate_content(prompt, generation_config=gen_config)
            response_text = response.text
            
            # 嘗試解析 JSON
            json_data = None
            if config.response_mode == "json":
                try:
                    json_data = json.loads(response_text)
                    logger.info("成功解析 JSON 回應")
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON 解析失敗，將作為純文本處理: {e}")
            
            return response_text, json_data
            
        except Exception as e:
            logger.error(f"Gemini API 呼叫失敗: {e}")
            raise

# ============================================
# 改進的 VS Code 自動化控制模組
# ============================================

class VSCodeController:
    """VS Code 自動化控制器"""
    
    @staticmethod
    def find_vscode_window(folder_name: str, timeout: int = 15) -> Optional[pwc.Window]:
        """使用 PyWinCtl 尋找 VS Code 視窗"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # 獲取所有視窗
            all_windows = pwc.getAllWindows()
            
            for window in all_windows:
                if window.title:
                    title_lower = window.title.lower()
                    # 檢查是否為 VS Code 視窗
                    if 'visual studio code' in title_lower:
                        # 檢查是否包含資料夾名稱
                        if folder_name.lower() in title_lower:
                            return window
            
            time.sleep(0.5)
        
        # 如果找不到特定資料夾的視窗，嘗試找任何 VS Code 視窗
        vscode_windows = pwc.getWindowsWithTitle("Visual Studio Code", condition=pwc.Re.CONTAINS)
        if vscode_windows:
            return vscode_windows[0]
        
        return None
    
    @staticmethod
    def launch_and_open(folder_path: str, filenames: List[str]) -> Dict[str, Any]:
        """啟動 VS Code 並打開指定檔案"""
        result = {
            "success": False,
            "window_found": False,
            "files_opened": [],
            "message": ""
        }
        
        try:
            # 啟動 VS Code 並打開專案資料夾
            logger.info(f"正在啟動 VS Code，資料夾: {folder_path}")
            
            # 直接打開專案資料夾和第一個檔案
            if filenames and len(filenames) > 0:
                first_file = Path(folder_path) / filenames[0]
                # 使用 code 命令直接打開檔案
                subprocess.Popen(
                    ['code', folder_path, str(first_file)],
                    shell=(platform.system() == 'Windows')
                )
            else:
                # 只打開資料夾
                subprocess.Popen(
                    ['code', folder_path],
                    shell=(platform.system() == 'Windows')
                )
            
            # 等待 VS Code 視窗出現
            folder_name = os.path.basename(os.path.normpath(folder_path))
            
            logger.info(f"尋找包含 '{folder_name}' 的 VS Code 視窗...")
            
            # 使用 PyWinCtl 尋找視窗
            vscode_window = VSCodeController.find_vscode_window(folder_name)
            
            if not vscode_window:
                result["message"] = f"在 15 秒內找不到 VS Code 視窗"
                logger.warning(result["message"])
                return result
            
            result["window_found"] = True
            logger.info(f"找到 VS Code 視窗: {vscode_window.title}")
            
            # 啟用視窗
            if vscode_window.isMinimized:
                vscode_window.restore()
            vscode_window.activate()
            time.sleep(1)
            
            # 修復：使用複製貼上代替直接輸入，避免輸入法問題
            if len(filenames) > 1:
                hotkey_ctrl = 'command' if platform.system() == 'Darwin' else 'ctrl'
                
                # 打開其餘檔案（第一個已經打開）
                for filename in filenames[1:3]:  # 限制最多再開2個檔案
                    time.sleep(0.5)
                    # Ctrl/Cmd + P 打開檔案選擇器
                    pyautogui.hotkey(hotkey_ctrl, 'p')
                    time.sleep(0.3)
                    
                    # 使用剪貼簿來輸入檔案名，避免輸入法問題
                    pyperclip.copy(filename)
                    pyautogui.hotkey(hotkey_ctrl, 'v')
                    time.sleep(0.2)
                    
                    # 按 Enter 打開檔案
                    pyautogui.press('enter')
                    
                    result["files_opened"].append(filename)
                    logger.info(f"已打開檔案: {filename}")
            
            # 記錄第一個檔案
            if filenames:
                result["files_opened"].insert(0, filenames[0])
            
            result["success"] = True
            result["message"] = f"成功打開 VS Code 和 {len(result['files_opened'])} 個檔案"
            logger.info(result["message"])
            
        except FileNotFoundError:
            result["message"] = "找不到 'code' 命令，請確保 VS Code 已安裝並加入 PATH"
            logger.error(result["message"])
        except Exception as e:
            result["message"] = f"VS Code 控制失敗: {str(e)}"
            logger.error(result["message"])
        
        return result

# ============================================
# 改進的螢幕擷取模組 - 使用 PyWinCtl 和模糊匹配
# ============================================

class WindowMatcher:
    """視窗匹配輔助類"""
    
    @staticmethod
    def fuzzy_match(string1: str, string2: str, threshold: float = 0.6) -> bool:
        """使用模糊匹配比較兩個字符串"""
        ratio = SequenceMatcher(None, string1.lower(), string2.lower()).ratio()
        return ratio >= threshold
    
    @staticmethod
    def normalize_title(title: str) -> str:
        """標準化視窗標題，移除瀏覽器後綴等"""
        # 移除常見的瀏覽器後綴
        browser_suffixes = [
            " - Google Chrome",
            " - Mozilla Firefox", 
            " - Microsoft Edge",
            " - Safari",
            " - Opera",
            " - Brave",
            " – Google Chrome",  # 注意不同的破折號
            " – Mozilla Firefox",
            " – Microsoft Edge"
        ]
        
        normalized = title
        for suffix in browser_suffixes:
            if suffix in normalized:
                normalized = normalized.replace(suffix, "")
                break
        
        return normalized.strip()
    
    @staticmethod
    def find_matching_window(target_title: str, all_windows: List[pwc.Window]) -> Optional[pwc.Window]:
        """使用多種策略尋找匹配的視窗"""
        if not target_title:
            return None
        
        target_lower = target_title.lower()
        target_normalized = WindowMatcher.normalize_title(target_title).lower()
        
        # 策略1：精確匹配（忽略大小寫）
        for window in all_windows:
            if window.title:
                if window.title.lower() == target_lower:
                    logger.info(f"精確匹配找到視窗: {window.title}")
                    return window
        
        # 策略2：標準化後精確匹配
        for window in all_windows:
            if window.title:
                normalized = WindowMatcher.normalize_title(window.title).lower()
                if normalized == target_normalized:
                    logger.info(f"標準化匹配找到視窗: {window.title}")
                    return window
        
        # 策略3：包含匹配
        for window in all_windows:
            if window.title:
                window_lower = window.title.lower()
                if target_normalized in window_lower or target_lower in window_lower:
                    logger.info(f"包含匹配找到視窗: {window.title}")
                    return window
        
        # 策略4：模糊匹配
        best_match = None
        best_ratio = 0.0
        
        for window in all_windows:
            if window.title:
                # 嘗試原始標題的模糊匹配
                ratio1 = SequenceMatcher(None, target_lower, window.title.lower()).ratio()
                
                # 嘗試標準化標題的模糊匹配
                normalized = WindowMatcher.normalize_title(window.title).lower()
                ratio2 = SequenceMatcher(None, target_normalized, normalized).ratio()
                
                max_ratio = max(ratio1, ratio2)
                
                if max_ratio > best_ratio and max_ratio >= 0.6:
                    best_ratio = max_ratio
                    best_match = window
        
        if best_match:
            logger.info(f"模糊匹配找到視窗 (相似度 {best_ratio:.2f}): {best_match.title}")
            return best_match
        
        return None

class ScreenCapture:
    """螢幕擷取管理器 - 使用 PyWinCtl"""
    
    @staticmethod
    def capture_all_monitors() -> List[Dict[str, str]]:
        """擷取所有螢幕"""
        screenshots = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        with mss.mss() as sct:
            for i, monitor in enumerate(sct.monitors[1:], 1):  # 跳過第0個（所有螢幕合併）
                filename = f"monitor_{i}_{timestamp}.png"
                filepath = SCREENSHOT_DIR / filename
                
                # 擷取螢幕
                sct_img = sct.grab(monitor)
                
                # 儲存為 PNG
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(filepath))
                
                screenshots.append({
                    "name": f"螢幕 {i}",
                    "filename": filename,
                    "path": str(filepath),
                    "width": monitor["width"],
                    "height": monitor["height"],
                    "timestamp": timestamp
                })
                
                logger.info(f"已擷取螢幕 {i}: {filepath}")
        
        return screenshots
    
    @staticmethod
    def capture_window_pywinctl(window: pwc.Window) -> Optional[Dict[str, str]]:
        """使用 PyWinCtl 擷取特定視窗"""
        try:
            # 確保視窗在前景
            if window.isMinimized:
                window.restore()
            window.activate()
            time.sleep(0.5)
            
            # 獲取視窗位置和大小
            box = window.box
            
            # 擷取視窗區域
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', window.title[:50])
            filename = f"window_{safe_title}_{timestamp}.png"
            filepath = SCREENSHOT_DIR / filename
            
            with mss.mss() as sct:
                monitor = {
                    "top": box.top,
                    "left": box.left,
                    "width": box.width,
                    "height": box.height
                }
                
                # 確保座標在合理範圍內
                monitor["top"] = max(0, monitor["top"])
                monitor["left"] = max(0, monitor["left"])
                monitor["width"] = min(monitor["width"], 3840)
                monitor["height"] = min(monitor["height"], 2160)
                
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(filepath))
            
            logger.info(f"已擷取視窗 '{window.title}': {filepath}")
            
            return {
                "name": window.title,
                "filename": filename,
                "path": str(filepath),
                "width": box.width,
                "height": box.height,
                "timestamp": timestamp
            }
            
        except Exception as e:
            logger.error(f"擷取視窗失敗 '{window.title}': {e}")
            return None
    
    @staticmethod
    def capture_running_programs(window_titles: List[str] = None, project_name: str = None) -> List[Dict[str, str]]:
        """擷取程式視窗（改進版本 - 使用 PyWinCtl 和模糊匹配）"""
        screenshots = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        logger.info(f"開始擷取程式視窗，指定標題: {window_titles}, 專案: {project_name}")
        
        # 獲取所有視窗
        all_windows = pwc.getAllWindows()
        
        # 記錄所有視窗標題以供調試
        logger.info("當前系統所有視窗：")
        for window in all_windows:
            if window.title and window.isVisible:
                logger.info(f"  - {window.title}")
        
        captured_titles = set()
        found_windows = []
        
        # 1. 尋找指定的程式視窗
        if window_titles:
            for target_title in window_titles:
                # 使用改進的視窗匹配
                matching_window = WindowMatcher.find_matching_window(target_title, all_windows)
                
                if matching_window and matching_window.title not in captured_titles:
                    found_windows.append((matching_window, "program"))
                    captured_titles.add(matching_window.title)
                    logger.info(f"找到程式視窗: {matching_window.title}")
                else:
                    logger.warning(f"未找到匹配的視窗: {target_title}")
        
        # 2. 尋找 VS Code 視窗（如果有專案名稱）
        if project_name:
            vscode_window = VSCodeController.find_vscode_window(project_name, timeout=2)
            if vscode_window and vscode_window.title not in captured_titles:
                found_windows.append((vscode_window, "vscode_project"))
                captured_titles.add(vscode_window.title)
                logger.info(f"找到專案 VS Code 視窗: {vscode_window.title}")
        
        # 3. 執行視窗擷取
        for window, capture_type in found_windows:
            screenshot = ScreenCapture.capture_window_pywinctl(window)
            if screenshot:
                screenshot["type"] = capture_type
                screenshots.append(screenshot)
        
        logger.info(f"擷取完成，共 {len(screenshots)} 個視窗")
        
        # 如果沒有找到任何視窗，嘗試更寬鬆的搜尋
        if not screenshots and window_titles:
            logger.info("使用更寬鬆的搜尋策略...")
            for target_title in window_titles:
                # 嘗試使用 PyWinCtl 的內建搜尋功能
                windows = pwc.getWindowsWithTitle(target_title, condition=pwc.Re.CONTAINS, flags=pwc.Re.IGNORECASE)
                for window in windows:
                    if window.title not in captured_titles:
                        screenshot = ScreenCapture.capture_window_pywinctl(window)
                        if screenshot:
                            screenshots.append(screenshot)
                        captured_titles.add(window.title)
                        logger.info(f"寬鬆搜尋找到: {window.title}")
        
        return screenshots

# ============================================
# 程式碼處理模組（保持不變，省略）
# ============================================

class CodeProcessor:
    """程式碼解析和處理器"""
    
    @staticmethod
    def parse_json_response(json_data: Dict) -> ProjectOutput:
        """解析 JSON 格式的 AI 回應"""
        try:
            # 解析檔案列表
            files = []
            for file_data in json_data.get('files', []):
                # 處理程式碼格式問題
                code = file_data.get('code', '')
                
                # 修復換行符號問題
                if isinstance(code, str):
                    # 替換字串形式的 \n 為真正的換行
                    code = code.replace('\\n', '\n')
                    # 替換字串形式的 \t 為真正的 tab
                    code = code.replace('\\t', '\t')
                    # 修復可能的引號轉義問題
                    code = code.replace('\\"', '"')
                    code = code.replace("\\'", "'")
                
                files.append(FileOutput(
                    filename=file_data.get('filename', 'untitled.txt'),
                    filetype=file_data.get('filetype', 'text'),
                    code=code,
                    opens_window=file_data.get('opens_window', False),
                    window_title=file_data.get('window_title'),
                    install_requirements=file_data.get('install_requirements'),
                    dependencies=file_data.get('dependencies'),
                    description=file_data.get('description'),
                    run_command=file_data.get('run_command'),
                    # 新增：網頁應用支援
                    is_web_app=file_data.get('is_web_app', False),
                    can_open_standalone=file_data.get('can_open_standalone', False),
                    server_address=file_data.get('server_address'),
                    web_title=file_data.get('web_title')
                ))
            
            # 創建專案輸出
            return ProjectOutput(
                project_name=json_data.get('project_name', 'untitled_project'),
                description=json_data.get('description', ''),
                files=files,
                main_file=json_data.get('main_file'),
                setup_instructions=json_data.get('setup_instructions'),
                run_instructions=json_data.get('run_instructions')
            )
        
        except Exception as e:
            logger.error(f"解析 JSON 回應失敗: {e}")
            raise
    
    @staticmethod
    def parse_text_response(response_text: str) -> ProjectOutput:
        """解析文本格式的 AI 回應（向後相容）"""
        # 首先嘗試尋找任何形式的程式碼區塊
        code_patterns = [
            r'```(?:python)?\n?(.*?)```',  # 標準 markdown 區塊
            r'```(.*?)```',                 # 任何 markdown 區塊
            r'`([^`]+)`',                   # 單行程式碼
        ]
        
        code = None
        for pattern in code_patterns:
            match = re.search(pattern, response_text, re.DOTALL)
            if match:
                code = match.group(1).strip()
                break
        
        if not code:
            # 如果找不到程式碼區塊，嘗試找 Python 程式碼模式
            # 尋找 import 或 def 開頭的行
            lines = response_text.split('\n')
            code_lines = []
            in_code = False
            for line in lines:
                if re.match(r'^\s*(import |from |def |class |if __name__|#)', line):
                    in_code = True
                if in_code:
                    code_lines.append(line)
                elif code_lines and not line.strip():
                    # 空行可能是程式碼的一部分
                    code_lines.append(line)
                elif code_lines and not re.match(r'^\s', line) and line.strip():
                    # 非縮排的非空行，可能程式碼結束了
                    break
            
            if code_lines:
                code = '\n'.join(code_lines)
        
        if not code:
            raise ValueError(
                "找不到程式碼。請確保 AI 回應包含程式碼區塊（```...```）或有效的程式碼內容。\n"
                f"AI 回應前 500 字元：\n{response_text[:500]}..."
            )
        
        # 解析檔案名稱
        filename_patterns = [
            r'/\*/(.*?)/\*/',                              # 原始格式
            r'filename[:\s]+["\']?([^"\'\n]+)["\']?',     # filename: xxx
            r'檔案名稱[:\s]+["\']?([^"\'\n]+)["\']?',      # 中文
            r'([a-zA-Z_][a-zA-Z0-9_]*\.py)',              # 任何 .py 檔名
        ]
        
        filename = None
        for pattern in filename_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                filename = match.group(1).strip()
                break
        
        if not filename:
            # 提供預設檔名
            logger.warning("找不到檔案名稱，使用預設名稱")
            filename = "generated_code.py"
        
        # 確保檔案名稱有副檔名
        if '.' not in filename:
            filename += '.py'
        
        # 解析安裝指令
        install_commands = []
        install_patterns = [
            r';;;(.*);;;',                      # 原始格式
            r'pip install ([a-zA-Z0-9_-]+)',    # pip install xxx
            r'npm install ([a-zA-Z0-9_-]+)',    # npm install xxx
        ]
        
        for pattern in install_patterns:
            matches = re.findall(pattern, response_text, re.IGNORECASE)
            for match in matches:
                if 'pip install' not in match and 'npm install' not in match:
                    if 'pip' in match or pattern == r'pip install ([a-zA-Z0-9_-]+)':
                        install_commands.append(f"pip install {match}")
                    else:
                        install_commands.append(match)
                else:
                    install_commands.append(match)
        
        # 檢測是否會開啟視窗
        opens_window = any(lib in code.lower() for lib in ['pygame', 'tkinter', 'pyqt', 'wx', 'kivy', 'pyglet'])
        window_title = None
        
        if opens_window:
            # 嘗試從程式碼中提取視窗標題
            title_patterns = [
                r'set_caption\(["\'](.+?)["\']\)',           # pygame
                r'title\s*=\s*["\'](.+?)["\']',             # tkinter
                r'setWindowTitle\(["\'](.+?)["\']\)',       # PyQt
                r'SetTitle\(["\'](.+?)["\']\)',             # wxPython
            ]
            for pattern in title_patterns:
                match = re.search(pattern, code)
                if match:
                    window_title = match.group(1)
                    break
        
        # 創建單檔案專案
        file_output = FileOutput(
            filename=filename,
            filetype="python",
            code=code,
            opens_window=opens_window,
            window_title=window_title,
            install_requirements=install_commands if install_commands else None,
            description="Generated Python file"
        )
        
        return ProjectOutput(
            project_name=filename.replace('.py', '').replace('.js', '').replace('.html', ''),
            description="AI Generated Project",
            files=[file_output],
            main_file=filename
        )
    
    @staticmethod
    def install_packages(install_requirements: List[str]) -> List[str]:
        """安裝套件"""
        logs = []
        
        for requirement in install_requirements:
            if not requirement:
                continue
            
            logger.info(f"執行安裝指令: {requirement}")
            
            # 解析指令
            parts = requirement.split()
            if parts[0] == 'pip':
                full_command = [sys.executable, "-m"] + parts
            else:
                full_command = parts
            
            try:
                result = subprocess.run(
                    full_command,
                    capture_output=True,
                    text=True,
                    check=True,
                    encoding='utf-8'
                )
                
                log = f"✅ 成功執行: {requirement}\n"
                log += result.stdout
                if result.stderr:
                    log += f"\n⚠️ 警告:\n{result.stderr}"
                
                logs.append(log)
                
            except subprocess.CalledProcessError as e:
                error_msg = f"❌ 安裝失敗: {requirement}\n錯誤: {e.stderr}"
                logger.error(error_msg)
                logs.append(error_msg)
        
        return logs
    
    @staticmethod
    def save_project_files(folder_path: str, project: ProjectOutput) -> List[str]:
        """儲存專案檔案"""
        saved_files = []
        project_dir = Path(folder_path) / project.project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        for file in project.files:
            filepath = project_dir / file.filename
            
            # 創建子目錄（如果需要）
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(file.code)
                
                logger.info(f"已儲存檔案: {filepath}")
                saved_files.append(str(filepath))
                
            except IOError as e:
                logger.error(f"儲存檔案失敗 {filepath}: {e}")
                raise
        
        # 儲存專案資訊檔案
        info_file = project_dir / "PROJECT_INFO.json"
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump({
                "project_name": project.project_name,
                "description": project.description,
                "main_file": project.main_file,
                "setup_instructions": project.setup_instructions,
                "run_instructions": project.run_instructions,
                "files": [asdict(file) for file in project.files]
            }, f, indent=2, ensure_ascii=False)
        
        saved_files.append(str(info_file))
        
        return saved_files

# ============================================
# 程式執行管理（保持不變）
# ============================================

class ProgramManager:
    """管理執行中的程式"""
    
    running_programs = {}  # 儲存運行中的程式 {pid: info}
    
    @classmethod
    def add_program(cls, process, filename, folder_path, window_title=None):
        """添加程式到管理列表"""
        if process is None:
            return
        cls.running_programs[process.pid] = {
            'process': process,
            'filename': filename,
            'folder_path': folder_path,
            'window_title': window_title,
            'start_time': datetime.now(),
            'pid': process.pid
        }
        logger.info(f"已添加程式到管理列表: PID {process.pid}, 檔案 {filename}")
    
    @classmethod
    def check_programs(cls):
        """檢查並更新程式狀態"""
        to_remove = []
        status = []
        
        for pid, info in list(cls.running_programs.items()):
            poll_result = info['process'].poll()
            if poll_result is None:
                # 仍在運行
                run_time = (datetime.now() - info['start_time']).seconds
                status.append({
                    'pid': pid,
                    'filename': info['filename'],
                    'window_title': info.get('window_title'),
                    'status': 'running',
                    'run_time': run_time
                })
            else:
                # 已結束
                to_remove.append(pid)
                status.append({
                    'pid': pid,
                    'filename': info['filename'],
                    'window_title': info.get('window_title'),
                    'status': 'finished',
                    'exit_code': poll_result
                })
        
        # 移除已結束的程式
        for pid in to_remove:
            if pid in cls.running_programs:
                del cls.running_programs[pid]
                logger.info(f"程式已結束並從列表移除: PID {pid}")
        
        return status
    
    @classmethod
    def terminate_program(cls, pid):
        """終止指定的程式"""
        if pid in cls.running_programs:
            try:
                cls.running_programs[pid]['process'].terminate()
                time.sleep(0.5)
                if cls.running_programs[pid]['process'].poll() is None:
                    cls.running_programs[pid]['process'].kill()
                del cls.running_programs[pid]
                logger.info(f"已終止程式: PID {pid}")
                return True
            except Exception as e:
                logger.error(f"終止程式失敗: {e}")
                if pid in cls.running_programs:
                    del cls.running_programs[pid] # 從列表中移除
                return False
        return False
    
    @classmethod
    def run_file(cls, filepath: str, folder_path: str, file_info: FileOutput = None):
        """執行檔案"""
        file_ext = Path(filepath).suffix.lower()
        if not file_info:
            logger.warning("run_file 被呼叫時未提供 file_info，將以基本模式執行")
            file_info = FileOutput(filename=Path(filepath).name, filetype=file_ext.strip('.'), code='')

        window_title = file_info.window_title
        
        try:
            process = None
            # 處理網頁應用
            if file_info.is_web_app:
                if file_ext == '.html' and file_info.can_open_standalone:
                    cls.open_standalone_browser(f'file:///{Path(filepath).resolve()}', file_info.web_title or "Web App")
                    return None
                
                if file_ext == '.py':
                    process = cls._run_python(filepath, folder_path, opens_window=file_info.opens_window)
                elif file_ext == '.js':
                    process = cls._run_node(filepath, folder_path)
                
                if not file_info.can_open_standalone and file_info.server_address:
                    time.sleep(2.5) # 給伺服器啟動時間
                    cls.open_standalone_browser(file_info.server_address, file_info.web_title or "Web App")

            # 處理非網頁應用
            elif file_ext == '.py':
                process = cls._run_python(filepath, folder_path, opens_window=file_info.opens_window)
            
            elif file_ext == '.js':
                process = cls._run_node(filepath, folder_path)
                
            elif file_ext == '.html':
                import webbrowser
                webbrowser.open(f'file:///{Path(filepath).resolve()}')
                return None
            else:
                logger.warning(f"不支援直接執行的檔案類型: {file_ext}")
                return None
                
            if process:
                cls.add_program(process, Path(filepath).name, folder_path, window_title)
            return process
            
        except Exception as e:
            logger.error(f"執行檔案失敗 {filepath}: {e}")
            raise

    @classmethod
    def _run_python(cls, filepath: str, folder_path: str, opens_window: bool = False):
        """執行 Python 檔案"""
        logger.info(f"執行 Python 檔案: {filepath}, 是否開啟視窗: {opens_window}")
        if platform.system() == 'Windows':
            if opens_window:
                # 對於 GUI 應用，創建新主控台以確保視窗能正常顯示
                return subprocess.Popen(
                    [sys.executable, str(filepath)],
                    cwd=folder_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                # 對於背景/主控台腳本，隱藏主控台視窗
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                return subprocess.Popen(
                    [sys.executable, str(filepath)],
                    cwd=folder_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    startupinfo=startupinfo
                )
        else:
            # macOS/Linux 的行為保持不變
            return subprocess.Popen(
                [sys.executable, str(filepath)],
                cwd=folder_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
    
    @classmethod
    def _run_node(cls, filepath: str, folder_path: str):
        """執行 Node.js 檔案"""
        return subprocess.Popen(
            ['node', str(filepath)],
            cwd=folder_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )

    @classmethod
    def open_standalone_browser(cls, url: str, title: str = "Web App"):
        """開啟獨立的瀏覽器視窗（不是新分頁）"""
        try:
            logger.info(f"嘗試以獨立視窗模式開啟 URL: {url}")
            browser_opened = False
            if platform.system() == 'Windows':
                # 嘗試找到 Chrome 或 Edge 路徑
                possible_paths = {
                    "chrome": [
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
                    ],
                    "edge": [
                        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                    ]
                }
                
                for browser, paths in possible_paths.items():
                    for path in paths:
                        if os.path.exists(path):
                            subprocess.Popen([
                                path,
                                '--new-window',
                                f'--app={url}',
                                '--window-size=1200,800',
                                f'--user-data-dir={CONFIG_DIR / f"{browser}_profile"}'
                            ])
                            logger.info(f"使用 {browser.capitalize()} 獨立視窗模式開啟")
                            browser_opened = True
                            break
                    if browser_opened:
                        break

            elif platform.system() == 'Darwin':
                chrome_app = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                if os.path.exists(chrome_app):
                    subprocess.Popen([
                        chrome_app, '--new-window', f'--app={url}',
                        '--window-size=1200,800', f'--user-data-dir={CONFIG_DIR / "chrome_profile"}'
                    ])
                    browser_opened = True
                else:
                    subprocess.Popen(['open', '-n', '-a', 'Safari', url])
                    browser_opened = True

            if not browser_opened:
                import webbrowser
                webbrowser.open_new(url)
                logger.info("後備方案：使用預設瀏覽器開啟新視窗/分頁")

        except Exception as e:
            logger.error(f"開啟獨立瀏覽器失敗: {e}")
            import webbrowser
            webbrowser.open_new(url)

# ============================================
# 主要處理流程（修改部分）
# ============================================

class ProcessManager:
    """主要處理流程管理器"""
    
    @staticmethod
    def run_automation_process(
        folder_path: str,
        prompt: str,
        config: AIConfig
    ) -> ProcessResult:
        """執行完整的自動化流程"""
        
        result = ProcessResult(success=False)
        
        try:
            # Step 1: 呼叫 AI 生成程式碼
            logger.info("Step 1: 呼叫 Gemini AI...")
            ai_response, json_data = GeminiAI.generate_content(prompt, config)
            result.ai_response = ai_response
            result.ai_response_json = json_data
            
            # Step 2: 解析 AI 回應
            logger.info("Step 2: 解析 AI 回應...")
            try:
                if json_data:
                    # JSON 模式
                    logger.info("使用 JSON 模式解析")
                    project = CodeProcessor.parse_json_response(json_data)
                else:
                    # 嘗試從純文本中提取 JSON
                    logger.info("嘗試從文本中提取 JSON")
                    try:
                        # 嘗試找到 JSON 結構
                        json_start = ai_response.find('{')
                        json_end = ai_response.rfind('}') + 1
                        if json_start >= 0 and json_end > json_start:
                            json_str = ai_response[json_start:json_end]
                            # 修復常見的 JSON 格式問題
                            json_str = json_str.replace('\\n', '\n')
                            json_str = json_str.replace('\\t', '\t')
                            potential_json = json.loads(json_str)
                            project = CodeProcessor.parse_json_response(potential_json)
                            logger.info("成功從文本中提取並解析 JSON")
                        else:
                            # 文本模式（向後相容）
                            logger.info("使用文本模式解析")
                            project = CodeProcessor.parse_text_response(ai_response)
                    except json.JSONDecodeError:
                        # 回退到文本模式
                        logger.info("JSON 解析失敗，回退到文本模式")
                        project = CodeProcessor.parse_text_response(ai_response)
                
                result.project_data = project
                
            except (ValueError, KeyError) as parse_error:
                logger.error(f"解析 AI 回應失敗: {parse_error}")
                result.error = f"解析失敗: {str(parse_error)}"
                
                # 嘗試提供更詳細的錯誤信息
                error_details = f"""
=== ❌ 解析錯誤 ===
{str(parse_error)}

=== 🔍 可能的原因 ===
1. AI 回應格式不正確
2. JSON 結構有誤
3. 程式碼格式化問題

=== 💡 解決建議 ===
1. 嘗試切換到文本模式
2. 調整 AI 模型（建議使用 Gemini 2.5 Pro）
3. 簡化您的需求描述
4. 檢查 API Key 是否有效

=== 🤖 AI 原始回應 ===
請查看下方「AI 回應」區域以檢視完整內容。
"""
                
                result.output = error_details
                
                # 如果有部分可用數據，嘗試提取
                if "```" in ai_response:
                    result.output += "\n=== 🔍 檢測到程式碼區塊 ===\n您可以手動複製下方 AI 回應中的程式碼。"
                
                return result
            
            # Step 3: 安裝套件
            logger.info("Step 3: 安裝必要套件...")
            all_requirements = []
            for file in project.files:
                if file.install_requirements:
                    all_requirements.extend(file.install_requirements)
            
            if all_requirements:
                result.installation_logs = CodeProcessor.install_packages(all_requirements)
            
            # Step 4: 儲存專案檔案
            logger.info("Step 4: 儲存專案檔案...")
            saved_files = CodeProcessor.save_project_files(folder_path, project)
            result.files_created = saved_files
            
            # Step 5: 啟動 VS Code
            logger.info("Step 5: 啟動 VS Code...")
            project_dir = str(Path(folder_path) / project.project_name)
            filenames_to_open = [f.filename for f in project.files[:3]]  # 最多開啟3個檔案
            vscode_result = VSCodeController.launch_and_open(project_dir, filenames_to_open)
            
            # Step 6: 執行主檔案（如果有）
            logger.info("Step 6: 執行程式...")
            execution_status = "尚未執行"
            execution_detail = ""
            window_titles_to_capture = []  # 收集需要擷取的視窗標題
            
            if project.main_file:
                main_file_path = Path(project_dir) / project.main_file
                
                # 找到對應的檔案資訊
                main_file_info = None
                for file in project.files:
                    if file.filename == project.main_file:
                        main_file_info = file
                        break
                
                if main_file_info:
                    # 執行檔案
                    process = ProgramManager.run_file(
                        str(main_file_path),
                        project_dir,
                        main_file_info  # 傳遞完整的檔案資訊
                    )
                    
                    if process:
                        time.sleep(0.5)
                        poll_result = process.poll()
                        
                        if poll_result is None:
                            execution_status = "✅ 程式已在背景成功啟動"
                            execution_detail = f"程序 ID (PID): {process.pid}"
                            
                            # 處理視窗擷取
                            if main_file_info.opens_window or main_file_info.is_web_app:
                                # 收集所有需要擷取的視窗標題
                                for file in project.files:
                                    if file.opens_window and file.window_title:
                                        window_titles_to_capture.append(file.window_title)
                                        logger.info(f"將擷取視窗: {file.window_title}")
                                    elif file.is_web_app and file.web_title:
                                        window_titles_to_capture.append(file.web_title)
                                        logger.info(f"將擷取網頁視窗: {file.web_title}")
                                
                                # 給程式和瀏覽器更多時間來創建視窗
                                if main_file_info.is_web_app:
                                    time.sleep(4)  # 網頁應用需要更多時間
                                else:
                                    time.sleep(3)  # GUI 應用
                                
                                # 嘗試擷取視窗
                                if window_titles_to_capture:
                                    program_screenshots = ScreenCapture.capture_running_programs(window_titles_to_capture)
                                    for screenshot in program_screenshots:
                                        result.screenshots.append(screenshot['filename'])
                                    
                                    if program_screenshots:
                                        execution_detail += f"\n已擷取 {len(program_screenshots)} 個視窗"
                                    else:
                                        execution_detail += "\n注意：視窗可能需要更多時間才能顯示"
                                        
                            # 特別處理網頁應用
                            if main_file_info.is_web_app:
                                if main_file_info.server_address:
                                    execution_detail += f"\n🌐 網頁地址: {main_file_info.server_address}"
                                if main_file_info.web_title:
                                    execution_detail += f"\n📄 網頁標題: {main_file_info.web_title}"
                                if not main_file_info.can_open_standalone:
                                    execution_detail += "\n✅ 已自動開啟獨立瀏覽器視窗"
                        
                        elif poll_result == 0:
                            stdout, stderr = process.communicate(timeout=1)
                            execution_status = "✅ 程式執行完成"
                            execution_detail = f"輸出:\n{stdout}" if stdout else "程式已結束"
                        else:
                            stdout, stderr = process.communicate(timeout=1)
                            execution_status = "⚠️ 程式執行遇到問題"
                            execution_detail = f"錯誤:\n{stderr}" if stderr else f"退出碼: {poll_result}"
                    
                    elif main_file_info.is_web_app and Path(main_file_path).suffix.lower() == '.html':
                        # 純 HTML 檔案
                        execution_status = "✅ 已開啟 HTML 檔案"
                        execution_detail = f"已在獨立瀏覽器視窗中開啟"
                        if main_file_info.web_title:
                            window_titles_to_capture.append(main_file_info.web_title)
                            time.sleep(2)
                            program_screenshots = ScreenCapture.capture_running_programs(window_titles_to_capture)
                            for screenshot in program_screenshots:
                                result.screenshots.append(screenshot['filename'])
            
            # 整合執行結果
            result.output = f"""
=== 🎉 專案生成成功 ===
📦 專案名稱: {project.project_name}
📝 描述: {project.description}
📁 專案位置: {project_dir}
📄 檔案數量: {len(project.files)}
🎯 主檔案: {project.main_file or '無指定'}

=== 📋 檔案列表 ===
"""
            for file in project.files:
                file_icon = "🐍" if file.filetype == "python" else "📄"
                window_info = f" (視窗: {file.window_title})" if file.opens_window and file.window_title else ""
                result.output += f"{file_icon} {file.filename} - {file.description or file.filetype}{window_info}\n"
            
            result.output += f"""
=== 💻 VS Code 狀態 ===
{'✅ 已開啟' if vscode_result.get('success') else '⚠️ 開啟失敗'}
已開啟檔案: {', '.join(vscode_result.get('files_opened', []))}

=== ⚡ 程式執行狀態 ===
{execution_status}
{execution_detail}
"""
            
            if project.setup_instructions:
                result.output += f"""
=== 🔧 設置指令 ===
{chr(10).join(f"• {inst}" for inst in project.setup_instructions)}
"""
            
            if project.run_instructions:
                result.output += f"""
=== ▶️ 執行指令 ===
{chr(10).join(f"• {inst}" for inst in project.run_instructions)}
"""
            
            if result.installation_logs:
                result.output += f"""
=== 📦 套件安裝日誌 ===
{chr(10).join(result.installation_logs)}
"""
            
            result.output += f"""
=== 💡 操作提示 ===
1. 查看 VS Code 視窗以編輯程式碼
2. 使用「延遲 5 秒後擷取」來擷取運行畫面
3. 查看「執行中的程式」監控程式狀態
4. 如果是圖形程式，應該會看到新視窗出現
"""
            
            result.success = True
            
        except Exception as e:
            result.error = str(e)
            logger.error(f"處理流程失敗: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            if not result.ai_response:
                result.ai_response = "無法獲取 AI 回應"
        
        return result

# ============================================
# Flask 路由（保持原有路由不變）
# ============================================

# 全域變數
window = None

@app.route('/')
def index():
    """主頁面"""
    return render_template('index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """處理配置 API"""
    if request.method == 'GET':
        config = ConfigManager.load()
        return jsonify(asdict(config))
    
    elif request.method == 'POST':
        data = request.get_json()
        config = AIConfig(**data)
        success = ConfigManager.save(config)
        
        if success:
            return jsonify({'success': True, 'message': '配置已儲存'})
        else:
            return jsonify({'success': False, 'error': '儲存失敗'}), 500

@app.route('/select-folder', methods=['GET'])
def select_folder():
    """選擇資料夾"""
    global window
    
    if not window:
        return jsonify({'success': False, 'error': 'Webview 視窗不存在'}), 500
    
    try:
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        path = result[0] if result else None
        
        if path:
            logger.info(f"選擇了資料夾: {path}")
            return jsonify({'success': True, 'path': path})
        else:
            return jsonify({'success': False, 'error': '未選擇資料夾'})
            
    except Exception as e:
        logger.error(f"選擇資料夾失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/run-process', methods=['POST'])
def run_process():
    """執行自動化流程"""
    try:
        data = request.get_json()
        
        folder_path = data.get('folder_path')
        prompt = data.get('prompt')
        config_data = data.get('config', {})
        
        if not all([folder_path, prompt]):
            return jsonify({
                'success': False,
                'error': '缺少必要參數（資料夾路徑或 AI 指令）',
                'ai_response': ''
            }), 400
        
        # 創建配置對象
        config = AIConfig(**config_data)
        
        # 執行流程
        result = ProcessManager.run_automation_process(
            folder_path,
            prompt,
            config
        )
        
        # 準備回應數據
        response_data = {
            'success': result.success,
            'output': result.output,
            'files_created': result.files_created,
            'ai_response': result.ai_response or '無 AI 回應',
            'ai_response_json': result.ai_response_json,
            'installation_logs': result.installation_logs,
            'error': result.error
        }
        
        # 如果有專案數據，添加到回應中
        if result.project_data:
            response_data['project'] = {
                'name': result.project_data.project_name,
                'description': result.project_data.description,
                'files_count': len(result.project_data.files),
                'main_file': result.project_data.main_file,
                'has_gui': any(f.opens_window for f in result.project_data.files)
            }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"執行流程時發生錯誤: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return jsonify({
            'success': False,
            'error': str(e),
            'ai_response': '執行過程中發生未預期的錯誤',
            'output': f'系統錯誤: {str(e)}'
        }), 500

@app.route('/capture-screenshots', methods=['POST'])
def capture_screenshots():
    """擷取螢幕畫面"""
    try:
        data = request.get_json() or {}
        capture_mode = data.get('mode', 'programs')
        window_titles = data.get('window_titles', [])
        project_name = data.get('project_name')  # 新增：專案名稱
        
        screenshots = []
        
        # 根據模式決定擷取內容
        if capture_mode == 'monitors':
            # 只擷取螢幕（不需要）
            logger.info("跳過螢幕擷取模式")
            
        elif capture_mode == 'programs':
            # 只擷取程式視窗
            if window_titles or project_name:
                # 給程式更多時間確保視窗完全顯示
                time.sleep(2)
                program_screenshots = ScreenCapture.capture_running_programs(
                    window_titles, 
                    project_name
                )
                screenshots.extend(program_screenshots)
            else:
                logger.warning("沒有指定視窗標題或專案名稱")
                
        elif capture_mode == 'all':
            # 擷取所有（不建議使用）
            logger.info("不建議使用 'all' 模式")
            if window_titles or project_name:
                time.sleep(2)
                program_screenshots = ScreenCapture.capture_running_programs(
                    window_titles,
                    project_name
                )
                screenshots.extend(program_screenshots)
        
        logger.info(f"擷取完成，共 {len(screenshots)} 張截圖，模式: {capture_mode}")
        
        return jsonify({
            'success': True,
            'screenshots': screenshots,
            'count': len(screenshots)
        })
        
    except Exception as e:
        logger.error(f"擷取螢幕失敗: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/screenshot/<filename>')
def serve_screenshot(filename):
    """提供螢幕截圖"""
    filepath = SCREENSHOT_DIR / filename
    if filepath.exists():
        return send_file(
            filepath, 
            mimetype='image/png',
            as_attachment=False,
            download_name=filename
        )
    else:
        return "Screenshot not found", 404

@app.route('/running-programs', methods=['GET'])
def get_running_programs():
    """獲取運行中的程式列表"""
    try:
        status = ProgramManager.check_programs()
        return jsonify({
            'success': True,
            'programs': status,
            'count': len(status)
        })
    except Exception as e:
        logger.error(f"獲取程式狀態失敗: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/terminate-program/<int:pid>', methods=['POST'])
def terminate_program(pid):
    """終止指定的程式"""
    try:
        success = ProgramManager.terminate_program(pid)
        if success:
            return jsonify({
                'success': True,
                'message': f'程式 PID {pid} 已終止'
            })
        else:
            return jsonify({
                'success': False,
                'error': f'找不到 PID {pid} 的程式'
            }), 404
    except Exception as e:
        logger.error(f"終止程式失敗: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================
# 主程式入口
# ============================================

def run_flask():
    """運行 Flask 伺服器"""
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)

def main():
    """主程式入口"""
    logger.info("=== AI 自動化開發控制器 Pro v3.1 啟動 ===")
    logger.info("=== 使用 PyWinCtl 改進視窗檢測 ===")
    logger.info(f"配置目錄: {CONFIG_DIR}")
    logger.info(f"截圖目錄: {SCREENSHOT_DIR}")
    logger.info(f"日誌目錄: {LOG_DIR}")
    logger.info(f"專案目錄: {PROJECTS_DIR}")
    
    # 啟動 Flask 伺服器線程
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # 等待 Flask 啟動
    time.sleep(1)
    
    # 創建 Webview 視窗
    global window
    window = webview.create_window(
        'AI 自動化開發控制器 Pro v3.1',
        f'http://{HOST}:{PORT}',
        width=1280,
        height=960,
        resizable=True,
        on_top=False
    )
    
    logger.info("正在啟動圖形界面...")
    webview.start()

if __name__ == '__main__':
    main()
