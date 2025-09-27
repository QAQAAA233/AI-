"""
AI 自動化開發控制器 Pro - 改進版後端
功能：整合 Gemini AI 與 VS Code 自動化控制，支援螢幕擷取和錯誤分析
作者：AI Controller Development Team
版本：2.0.0
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
from dataclasses import dataclass, asdict

# Web framework imports
from flask import Flask, render_template, jsonify, request, send_file
import webview

# AI and automation imports
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold
import pygetwindow as gw
import pyautogui
import pyperclip

# Screen capture imports
import mss
import mss.tools
from PIL import Image
import io
import base64

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
CONFIG_DIR = Path.home() / '.ai_controller_v2'
CONFIG_FILE = CONFIG_DIR / 'config.json'
SCREENSHOT_DIR = CONFIG_DIR / 'screenshots'
LOG_DIR = CONFIG_DIR / 'logs'

# 確保必要目錄存在
for directory in [CONFIG_DIR, SCREENSHOT_DIR, LOG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ============================================
# 數據模型
# ============================================

@dataclass
class AIConfig:
    """AI 配置數據模型"""
    connection_method: str = "api_key"
    gemini_api_key: str = ""
    model_name: str = "gemini-2.5-pro"
    system_instruction: str = """You are a helpful coding assistant.

When generating code, you MUST follow this format:
1. If packages need to be installed, include: ;;;pip install package_name;;;
2. Put the complete Python code in a code block: ```python ... ```
3. Specify the filename: /*/filename.py/*/
4. IMPORTANT: If creating a GUI window (pygame/tkinter), set the window title to match the filename (without .py extension)

Example response format:
;;;pip install pygame;;;

```python
import pygame
pygame.init()
pygame.display.set_caption("cool_animation")  # Window title matches filename
# ... rest of the code
```

/*/cool_animation.py/*/"""
    generation_params: Dict[str, Any] = None
    safety_settings: Dict[str, str] = None
    automation_settings: Dict[str, Any] = None

    def __post_init__(self):
        if self.generation_params is None:
            self.generation_params = {
                "temperature": 1.0,
                "top_p": 0.95,
                "top_k": 64,
                "max_output_tokens": 8192,
                "candidate_count": 1,
                "stop_sequences": [],
                "response_mime_type": "text/plain"
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
    filename: str = ""
    ai_response: str = ""
    installation_log: str = ""
    error: str = ""
    screenshots: List[str] = None

# ============================================
# 配置管理模塊
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
# Gemini AI 模塊
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
    def generate_content(prompt: str, config: AIConfig) -> str:
        """呼叫 Gemini API 生成內容"""
        try:
            # 配置連接
            GeminiAI.configure(config)
            
            # 準備生成配置
            gen_config = GenerationConfig(**{
                k: v for k, v in config.generation_params.items() if v
            })
            
            # 準備安全設置
            safety_settings = {
                HarmCategory[category]: HarmBlockThreshold[threshold]
                for category, threshold in config.safety_settings.items()
            }
            
            # 準備系統指令
            system_instruction = {
                "parts": [{"text": config.system_instruction}]
            } if config.system_instruction else None
            
            # 創建模型實例
            model_name = f"models/{config.model_name}"
            logger.info(f"使用模型: {model_name}")
            
            model = genai.GenerativeModel(
                model_name=model_name,
                safety_settings=safety_settings,
                system_instruction=system_instruction
            )
            
            # 生成內容
            response = model.generate_content(prompt, generation_config=gen_config)
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini API 呼叫失敗: {e}")
            raise

# ============================================
# VS Code 自動化控制模塊
# ============================================

class VSCodeController:
    """VS Code 自動化控制器"""
    
    @staticmethod
    def launch_and_open(folder_path: str, filename: str) -> Dict[str, Any]:
        """啟動 VS Code 並打開指定文件"""
        result = {
            "success": False,
            "window_found": False,
            "file_opened": False,
            "message": ""
        }
        
        try:
            # 啟動 VS Code
            logger.info(f"正在啟動 VS Code，資料夾: {folder_path}")
            subprocess.Popen(
                ['code', folder_path],
                shell=(platform.system() == 'Windows')
            )
            
            # 等待視窗出現
            folder_name = os.path.basename(os.path.normpath(folder_path))
            vscode_window = None
            timeout = 20
            start_time = time.time()
            
            logger.info(f"尋找包含 '{folder_name}' 的 VS Code 視窗...")
            
            while time.time() - start_time < timeout:
                possible_windows = gw.getWindowsWithTitle(folder_name)
                for window in possible_windows:
                    if 'visual studio code' in window.title.lower():
                        vscode_window = window
                        break
                if vscode_window:
                    break
                time.sleep(0.5)
            
            if not vscode_window:
                # 如果找不到特定資料夾的視窗，嘗試找任何 VS Code 視窗
                possible_windows = gw.getWindowsWithTitle("Visual Studio Code")
                if possible_windows:
                    vscode_window = possible_windows[0]
                    logger.warning("使用找到的第一個 VS Code 視窗")
                else:
                    result["message"] = f"在 {timeout} 秒內找不到 VS Code 視窗"
                    logger.warning(result["message"])
                    return result
            
            result["window_found"] = True
            logger.info(f"找到 VS Code 視窗: {vscode_window.title}")
            
            # 啟用視窗
            if vscode_window.isMinimized:
                vscode_window.restore()
            vscode_window.activate()
            time.sleep(1)
            
            # 使用鍵盤快捷鍵打開文件
            hotkey_ctrl = 'command' if platform.system() == 'Darwin' else 'ctrl'
            
            # Ctrl/Cmd + P 打開文件選擇器
            pyautogui.hotkey(hotkey_ctrl, 'p')
            time.sleep(0.5)
            
            # 輸入文件名
            pyperclip.copy(filename)
            pyautogui.hotkey(hotkey_ctrl, 'v')
            time.sleep(0.2)
            
            # 按 Enter 打開文件
            pyautogui.press('enter')
            time.sleep(1)
            
            result["file_opened"] = True
            
            # 也打開 Terminal 供檢查（但不執行命令）
            pyautogui.hotkey(hotkey_ctrl, '`')
            time.sleep(0.5)
            
            result["success"] = True
            result["message"] = f"成功打開 VS Code 和檔案: {filename}"
            logger.info(result["message"])
            
        except FileNotFoundError:
            result["message"] = "找不到 'code' 命令，請確保 VS Code 已安裝並加入 PATH"
            logger.error(result["message"])
        except Exception as e:
            result["message"] = f"VS Code 控制失敗: {str(e)}"
            logger.error(result["message"])
        
        return result

# ============================================
# 螢幕擷取模塊
# ============================================

class ScreenCapture:
    """螢幕擷取管理器"""
    
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
    def capture_window(window_title: str) -> Optional[Dict[str, str]]:
        """擷取特定視窗"""
        try:
            # 尋找視窗
            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                logger.warning(f"找不到標題包含 '{window_title}' 的視窗")
                return None
            
            window = windows[0]
            
            # 確保視窗在前景
            if window.isMinimized:
                window.restore()
            window.activate()
            time.sleep(0.5)
            
            # 擷取視窗區域
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = window_title.replace(' ', '_').replace('/', '_')
            filename = f"window_{safe_title}_{timestamp}.png"
            filepath = SCREENSHOT_DIR / filename
            
            with mss.mss() as sct:
                monitor = {
                    "top": window.top,
                    "left": window.left,
                    "width": window.width,
                    "height": window.height
                }
                
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(filepath))
            
            logger.info(f"已擷取視窗 '{window_title}': {filepath}")
            
            return {
                "name": window_title,
                "filename": filename,
                "path": str(filepath),
                "width": window.width,
                "height": window.height,
                "timestamp": timestamp
            }
            
        except Exception as e:
            logger.error(f"擷取視窗失敗: {e}")
            return None
    
    @staticmethod
    def capture_running_programs() -> List[Dict[str, str]]:
        """擷取特定的程式視窗（VS Code、控制器、AI 生成的程式）"""
        screenshots = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 獲取最近生成的檔案名稱（從 ProgramManager 獲取）
        recent_filenames = []
        for info in ProgramManager.running_programs.values():
            # 去除 .py 副檔名作為視窗標題的一部分
            filename_without_ext = info['filename'].replace('.py', '')
            recent_filenames.append(filename_without_ext)
        
        logger.info(f"尋找相關視窗，最近的檔案名稱: {recent_filenames}")
        
        all_windows = gw.getAllWindows()
        captured_titles = set()
        
        for window in all_windows:
            # 跳過最小化的視窗和已擷取的視窗
            if not window.title or window.title in captured_titles:
                continue
            
            window_title_lower = window.title.lower()
            should_capture = False
            capture_reason = ""
            
            # 1. 檢查是否為 VS Code 視窗（只擷取一次）
            if 'visual studio code' in window_title_lower and 'VS Code' not in captured_titles:
                should_capture = True
                capture_reason = "VS Code"
                captured_titles.add('VS Code')  # 標記已擷取
            
            # 2. 檢查是否為控制器視窗
            elif 'ai 自動化開發控制器' in window_title_lower or 'ai controller' in window_title_lower:
                should_capture = True
                capture_reason = "控制器"
            
            # 3. 檢查是否包含最近生成的檔案名稱
            else:
                for filename in recent_filenames:
                    if filename.lower() in window_title_lower:
                        should_capture = True
                        capture_reason = f"程式視窗 ({filename})"
                        break
            
            # 4. 檢查常見的 Python GUI 框架視窗（但必須合理大小）
            if not should_capture and window.width > 300 and window.height > 200:
                # 只擷取明確是程式產生的視窗
                gui_keywords = ['pygame', 'tkinter', 'tk', 'pyqt', 'animation', 'demo']
                for keyword in gui_keywords:
                    if keyword in window_title_lower:
                        # 額外檢查：確保不是系統視窗
                        if not any(sys_word in window_title_lower for sys_word in 
                                 ['chrome', 'firefox', 'edge', 'explorer', 'settings', 'config']):
                            should_capture = True
                            capture_reason = f"GUI 程式 ({keyword})"
                            break
            
            if should_capture:
                try:
                    logger.info(f"準備擷取視窗: {window.title} (原因: {capture_reason})")
                    
                    # 確保視窗可見並置頂
                    if window.isMinimized:
                        window.restore()
                    window.activate()
                    time.sleep(0.3)
                    
                    # 擷取視窗
                    safe_title = window.title[:30].replace(' ', '_').replace('/', '_').replace('\\', '_')
                    filename = f"{capture_reason.replace(' ', '_')}_{safe_title}_{timestamp}.png"
                    filepath = SCREENSHOT_DIR / filename
                    
                    with mss.mss() as sct:
                        monitor = {
                            "top": max(0, window.top),
                            "left": max(0, window.left),
                            "width": min(window.width, 3840),  # 限制最大寬度
                            "height": min(window.height, 2160)  # 限制最大高度
                        }
                        
                        sct_img = sct.grab(monitor)
                        mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(filepath))
                    
                    screenshots.append({
                        "name": f"{capture_reason}: {window.title[:50]}",
                        "filename": filename,
                        "path": str(filepath),
                        "width": window.width,
                        "height": window.height,
                        "timestamp": timestamp
                    })
                    
                    captured_titles.add(window.title)
                    logger.info(f"成功擷取視窗: {window.title}")
                    
                except Exception as e:
                    logger.warning(f"擷取視窗 '{window.title}' 失敗: {e}")
        
        logger.info(f"總共擷取了 {len(screenshots)} 個相關視窗")
        return screenshots

# ============================================
# 程式碼處理模塊
# ============================================

class CodeProcessor:
    """程式碼解析和處理器"""
    
    @staticmethod
    def parse_ai_response(response_text: str) -> Tuple[str, str, Optional[str]]:
        """解析 AI 回應中的程式碼和指令"""
        # 解析程式碼區塊
        code_match = re.search(r'```python(.*?)```', response_text, re.DOTALL)
        if not code_match:
            # 嘗試其他可能的格式
            code_match = re.search(r'```(.*?)```', response_text, re.DOTALL)
            if not code_match:
                raise ValueError(
                    "找不到程式碼區塊。請確保 AI 回應包含 ```python ... ``` 格式的程式碼。\n"
                    f"AI 回應前 500 字元：\n{response_text[:500]}..."
                )
        
        code = code_match.group(1).strip()
        if not code:
            raise ValueError("程式碼區塊為空")
        
        # 解析檔案名稱
        filename_match = re.search(r'/\*/(.*?)/\*/', response_text)
        if not filename_match:
            # 嘗試其他可能的格式
            filename_match = re.search(r'檔案名稱[：:]\s*(\S+\.py)', response_text, re.IGNORECASE)
            if not filename_match:
                # 如果還是找不到，提供預設名稱
                logger.warning("找不到檔案名稱，使用預設名稱")
                filename = "generated_code.py"
            else:
                filename = filename_match.group(1).strip()
        else:
            filename = filename_match.group(1).strip()
        
        # 驗證檔案名稱安全性
        if ".." in filename or "/" in filename or "\\" in filename:
            raise ValueError(f"不安全的檔案名稱: {filename}")
        
        # 確保檔案名稱有 .py 副檔名
        if not filename.endswith('.py'):
            filename += '.py'
        
        # 解析安裝指令（可選）
        install_match = re.search(r';;;(.*);;;', response_text)
        install_command = install_match.group(1).strip() if install_match else None
        
        logger.info(f"解析成功 - 檔案名: {filename}, 安裝指令: {install_command}")
        
        return filename, code, install_command
    
    @staticmethod
    def install_packages(install_command: str) -> str:
        """安裝套件"""
        if not install_command:
            return ""
        
        logger.info(f"執行安裝指令: {install_command}")
        
        full_command = [sys.executable, "-m"] + install_command.split()
        
        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8'
            )
            
            log = f"✅ 成功執行: {install_command}\n"
            log += result.stdout
            if result.stderr:
                log += f"\n⚠️ 警告:\n{result.stderr}"
            
            return log
            
        except subprocess.CalledProcessError as e:
            error_msg = f"❌ 安裝失敗: {install_command}\n錯誤: {e.stderr}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    @staticmethod
    def save_code_file(folder_path: str, filename: str, code: str) -> str:
        """儲存程式碼檔案"""
        filepath = Path(folder_path) / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(code)
            
            logger.info(f"已儲存檔案: {filepath}")
            return str(filepath)
            
        except IOError as e:
            logger.error(f"儲存檔案失敗: {e}")
            raise

# ============================================
# 程式執行管理
# ============================================

class ProgramManager:
    """管理執行中的程式"""
    
    running_programs = {}  # 儲存運行中的程式 {pid: info}
    
    @classmethod
    def add_program(cls, process, filename, folder_path):
        """添加程式到管理列表"""
        cls.running_programs[process.pid] = {
            'process': process,
            'filename': filename,
            'folder_path': folder_path,
            'start_time': datetime.now(),
            'pid': process.pid
        }
        logger.info(f"已添加程式到管理列表: PID {process.pid}, 檔案 {filename}")
    
    @classmethod
    def check_programs(cls):
        """檢查並更新程式狀態"""
        to_remove = []
        status = []
        
        for pid, info in cls.running_programs.items():
            poll_result = info['process'].poll()
            if poll_result is None:
                # 仍在運行
                run_time = (datetime.now() - info['start_time']).seconds
                status.append({
                    'pid': pid,
                    'filename': info['filename'],
                    'status': 'running',
                    'run_time': run_time
                })
            else:
                # 已結束
                to_remove.append(pid)
                status.append({
                    'pid': pid,
                    'filename': info['filename'],
                    'status': 'finished',
                    'exit_code': poll_result
                })
        
        # 移除已結束的程式
        for pid in to_remove:
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
                return False
        return False

# ============================================
# 主要處理流程
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
            ai_response = GeminiAI.generate_content(prompt, config)
            result.ai_response = ai_response  # 無論如何都保存 AI 回應
            
            # Step 2: 解析 AI 回應
            logger.info("Step 2: 解析 AI 回應...")
            try:
                filename, code, install_cmd = CodeProcessor.parse_ai_response(ai_response)
                result.filename = filename
            except ValueError as parse_error:
                # 解析失敗時，返回錯誤但包含 AI 原始回應
                logger.error(f"解析 AI 回應失敗: {parse_error}")
                result.error = f"解析失敗: {str(parse_error)}\n\n請檢查 AI 回應格式是否正確。"
                result.output = f"""
=== ❌ 解析錯誤 ===
{str(parse_error)}

=== 📝 提示 ===
AI 回應必須包含：
1. Python 程式碼區塊：```python ... ```
2. 檔案名稱：/*/filename.py/*/
3. (可選) 安裝指令：;;;pip install package;;;

=== 🤖 AI 原始回應 ===
請查看下方「AI 回應」區域以檢視完整內容。
您可以複製 AI 回應中的程式碼，手動建立檔案。
"""
                # 即使解析失敗也返回，讓用戶能看到 AI 回應
                return result
            
            # Step 3: 安裝套件（如果需要）
            if install_cmd:
                logger.info("Step 3: 安裝套件...")
                try:
                    result.installation_log = CodeProcessor.install_packages(install_cmd)
                except Exception as install_error:
                    logger.warning(f"套件安裝失敗: {install_error}")
                    result.installation_log = f"⚠️ 套件安裝失敗: {install_error}"
            
            # Step 4: 儲存程式碼檔案
            logger.info("Step 4: 儲存程式碼檔案...")
            file_path = CodeProcessor.save_code_file(folder_path, filename, code)
            
            # Step 5: 啟動 VS Code 並執行程式
            logger.info("Step 5: 啟動 VS Code 並執行程式...")
            vscode_result = VSCodeController.launch_and_open(folder_path, filename)
            
            # Step 6: 使用 Popen 非阻塞式執行程式（核心執行方式）
            logger.info(f"Step 6: 使用 Popen 非阻塞式執行程式: {file_path}")
            try:
                # 使用 subprocess.Popen 在背景執行程式
                process = subprocess.Popen(
                    [sys.executable, str(file_path)],
                    cwd=folder_path,  # 確保在正確的目錄執行
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == 'Windows' else 0
                )
                
                # 將程式加入管理列表
                ProgramManager.add_program(process, filename, folder_path)
                
                # 等待一小段時間檢查程式是否正常啟動
                time.sleep(0.5)
                poll_result = process.poll()
                
                if poll_result is None:
                    # 程式仍在運行（正常情況）
                    logger.info(f"程式已成功在背景啟動，PID: {process.pid}")
                    execution_status = "✅ 程式已在背景成功啟動"
                    execution_detail = f"程序 ID (PID): {process.pid}"
                elif poll_result == 0:
                    # 程式已正常結束（可能是快速執行的腳本）
                    stdout, stderr = process.communicate(timeout=1)
                    execution_status = "✅ 程式執行完成"
                    execution_detail = f"輸出:\n{stdout}" if stdout else "程式已結束"
                else:
                    # 程式執行出錯
                    stdout, stderr = process.communicate(timeout=1)
                    execution_status = "⚠️ 程式執行遇到問題"
                    execution_detail = f"錯誤:\n{stderr}" if stderr else f"退出碼: {poll_result}"
                    
            except Exception as e:
                logger.error(f"Popen 執行失敗: {e}")
                execution_status = "❌ 程式啟動失敗"
                execution_detail = str(e)
            
            # 整合執行結果
            result.output = f"""
=== 執行摘要 ===
📁 專案資料夾: {folder_path}
📄 檔案名稱: {filename}
🖥️ VS Code 狀態: {'✅ 已開啟' if vscode_result.get('success') else '⚠️ 開啟失敗'}

=== 程式執行狀態 ===
{execution_status}
{execution_detail}

=== 操作提示 ===
💡 程式已在背景執行，您可以：
1. 查看 VS Code 視窗以編輯程式碼
2. 使用「延遲 5 秒後擷取」來擷取運行畫面
3. 使用「擷取 VS Code Terminal」查看輸出
4. 如果是圖形程式，應該會看到新視窗出現

⚠️ 注意：
- 圖形介面程式（pygame/tkinter）會開啟新視窗
- Web 應用會在瀏覽器中開啟
- 長時間運行的程式會持續在背景執行
"""
            
            if result.installation_log:
                result.output = f"=== 套件安裝日誌 ===\n{result.installation_log}\n\n" + result.output
            
            result.success = True
            
        except Exception as e:
            result.error = str(e)
            logger.error(f"處理流程失敗: {e}")
            # 確保 AI 回應總是被保留
            if not result.ai_response:
                result.ai_response = "無法獲取 AI 回應"
        
        return result

# ============================================
# Flask 路由
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
        
        # 返回結果（確保總是包含 AI 回應）
        return jsonify({
            'success': result.success,
            'output': result.output,
            'filename': result.filename,
            'ai_response': result.ai_response or '無 AI 回應',
            'installation_log': result.installation_log,
            'error': result.error
        })
        
    except Exception as e:
        logger.error(f"執行流程時發生錯誤: {e}")
        # 即使發生異常也嘗試返回有用的信息
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
        capture_mode = data.get('mode', 'all')  # all, monitors, programs
        
        screenshots = []
        
        if capture_mode in ['all', 'monitors']:
            # 擷取所有螢幕
            monitor_screenshots = ScreenCapture.capture_all_monitors()
            screenshots.extend(monitor_screenshots)
        
        # 給程式時間顯示視窗
        if capture_mode in ['all', 'programs']:
            # 等待程式視窗完全載入
            time.sleep(1)
            
            # 擷取程式產生的視窗（包括 VS Code、控制器、AI 生成的程式）
            program_screenshots = ScreenCapture.capture_running_programs()
            screenshots.extend(program_screenshots)
        
        logger.info(f"擷取完成，共 {len(screenshots)} 張截圖")
        
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

@app.route('/monitor-terminal', methods=['POST'])
def monitor_terminal():
    """監控 VS Code Terminal 輸出（通過截圖）"""
    try:
        # 嘗試擷取 VS Code 視窗
        vscode_screenshot = None
        for window_title_part in ['Visual Studio Code', 'VS Code', 'Code']:
            windows = gw.getWindowsWithTitle(window_title_part)
            if windows:
                window = windows[0]
                # 聚焦到 Terminal 區域
                window.activate()
                time.sleep(0.5)
                
                # 擷取整個 VS Code 視窗
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"vscode_terminal_{timestamp}.png"
                filepath = SCREENSHOT_DIR / filename
                
                with mss.mss() as sct:
                    monitor = {
                        "top": max(0, window.top),
                        "left": max(0, window.left),
                        "width": window.width,
                        "height": window.height
                    }
                    
                    sct_img = sct.grab(monitor)
                    mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(filepath))
                
                return jsonify({
                    'success': True,
                    'screenshot': {
                        'filename': filename,
                        'timestamp': timestamp
                    },
                    'message': 'VS Code Terminal 截圖成功'
                })
        
        return jsonify({
            'success': False,
            'error': '找不到 VS Code 視窗'
        }), 404
        
    except Exception as e:
        logger.error(f"監控 Terminal 失敗: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
    """運行 Flask 服務器"""
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)

def main():
    """主程式入口"""
    logger.info("=== AI 自動化開發控制器 Pro 啟動 ===")
    logger.info(f"配置目錄: {CONFIG_DIR}")
    logger.info(f"截圖目錄: {SCREENSHOT_DIR}")
    logger.info(f"日誌目錄: {LOG_DIR}")
    
    # 啟動 Flask 服務器線程
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # 等待 Flask 啟動
    time.sleep(1)
    
    # 創建 Webview 視窗
    global window
    window = webview.create_window(
        'AI 自動化開發控制器 Pro',
        f'http://{HOST}:{PORT}',
        width=1200,
        height=900,
        resizable=True,
        on_top=False
    )
    
    logger.info("正在啟動圖形界面...")
    webview.start()

if __name__ == '__main__':
    main()