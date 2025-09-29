"""自動化流程相關的所有控制器。"""

from __future__ import annotations

import io
import json
import os
import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys

import mss
import pyautogui
import pyperclip
import pywinctl as pwc
from PIL import Image
from difflib import SequenceMatcher

from core import AIConfig, CodeProcessor, CONFIG_DIR, ProcessResult, SCREENSHOT_DIR, logger
from services import GeminiAI


class VSCodeController:
    """VS Code 自動化控制器"""

    @staticmethod
    def find_vscode_window(folder_name: str, timeout: int = 15) -> Optional[pwc.Window]:
        start_time = time.time()
        while time.time() - start_time < timeout:
            for window in pwc.getAllWindows():
                if window.title and 'visual studio code' in window.title.lower():
                    if folder_name.lower() in window.title.lower():
                        return window
            time.sleep(0.5)

        vscode_windows = pwc.getWindowsWithTitle("Visual Studio Code", condition=pwc.Re.CONTAINS)
        return vscode_windows[0] if vscode_windows else None

    @staticmethod
    def launch_and_open(folder_path: str, filenames: List[str]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "success": False,
            "window_found": False,
            "files_opened": [],
            "message": "",
        }

        try:
            logger.info("正在啟動 VS Code，資料夾: %s", folder_path)
            if filenames:
                first_file = Path(folder_path) / filenames[0]
                subprocess.Popen(['code', folder_path, str(first_file)], shell=(platform.system() == 'Windows'))
            else:
                subprocess.Popen(['code', folder_path], shell=(platform.system() == 'Windows'))

            folder_name = os.path.basename(os.path.normpath(folder_path))
            logger.info("尋找包含 '%s' 的 VS Code 視窗...", folder_name)
            vscode_window = VSCodeController.find_vscode_window(folder_name)
            if not vscode_window:
                result["message"] = "在 15 秒內找不到 VS Code 視窗"
                logger.warning(result["message"])
                return result

            result["window_found"] = True
            logger.info("找到 VS Code 視窗: %s", vscode_window.title)

            if vscode_window.isMinimized:
                vscode_window.restore()
            vscode_window.activate()
            time.sleep(1)

            if len(filenames) > 1:
                hotkey_ctrl = 'command' if platform.system() == 'Darwin' else 'ctrl'
                for filename in filenames[1:3]:
                    time.sleep(0.5)
                    pyautogui.hotkey(hotkey_ctrl, 'p')
                    time.sleep(0.3)
                    pyperclip.copy(filename)
                    pyautogui.hotkey(hotkey_ctrl, 'v')
                    time.sleep(0.2)
                    pyautogui.press('enter')
                    result["files_opened"].append(filename)
                    logger.info("已打開檔案: %s", filename)

            if filenames:
                result["files_opened"].insert(0, filenames[0])

            result["success"] = True
            result["message"] = f"成功打開 VS Code 和 {len(result['files_opened'])} 個檔案"
            logger.info(result["message"])
        except FileNotFoundError:
            result["message"] = "找不到 'code' 命令，請確保 VS Code 已安裝並加入 PATH"
            logger.error(result["message"])
        except Exception as exc:  # pragma: no cover - 依賴桌面環境
            result["message"] = f"VS Code 控制失敗: {exc}"
            logger.error(result["message"])

        return result


class WindowMatcher:
    """視窗匹配輔助類"""

    @staticmethod
    def normalize_title(title: str) -> str:
        suffixes = [
            " - Google Chrome",
            " - Mozilla Firefox",
            " - Microsoft Edge",
            " - Safari",
            " - Opera",
            " - Brave",
            " – Google Chrome",
            " – Mozilla Firefox",
            " – Microsoft Edge",
        ]
        normalized = title
        for suffix in suffixes:
            if suffix in normalized:
                normalized = normalized.replace(suffix, "")
                break
        return normalized.strip()

    @staticmethod
    def find_matching_window(target_title: str, all_windows: List[pwc.Window]) -> Optional[pwc.Window]:
        if not target_title:
            return None

        target_lower = target_title.lower()
        target_normalized = WindowMatcher.normalize_title(target_title).lower()

        for window in all_windows:
            if window.title and window.title.lower() == target_lower:
                logger.info("精確匹配找到視窗: %s", window.title)
                return window

        for window in all_windows:
            if window.title:
                normalized = WindowMatcher.normalize_title(window.title).lower()
                if normalized == target_normalized:
                    logger.info("標準化匹配找到視窗: %s", window.title)
                    return window

        for window in all_windows:
            if window.title and target_normalized in window.title.lower():
                logger.info("包含匹配找到視窗: %s", window.title)
                return window

        best_match: Optional[pwc.Window] = None
        best_ratio = 0.0
        for window in all_windows:
            if not window.title:
                continue
            ratio1 = SequenceMatcher(None, target_lower, window.title.lower()).ratio()
            normalized = WindowMatcher.normalize_title(window.title).lower()
            ratio2 = SequenceMatcher(None, target_normalized, normalized).ratio()
            max_ratio = max(ratio1, ratio2)
            if max_ratio > best_ratio and max_ratio >= 0.6:
                best_ratio = max_ratio
                best_match = window

        if best_match:
            logger.info("模糊匹配找到視窗 (相似度 %.2f): %s", best_ratio, best_match.title)
        return best_match


class ScreenCapture:
    """螢幕擷取管理器"""

    @staticmethod
    def capture_window_pywinctl(window: pwc.Window) -> Optional[Dict[str, Any]]:
        try:
            if window.isMinimized:
                window.restore()
            window.activate()
            time.sleep(0.5)

            box = window.box
            with mss.mss() as sct:
                region = {
                    "top": box.top,
                    "left": box.left,
                    "width": box.width,
                    "height": box.height,
                }
                sct_img = sct.grab(region)
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")

            filename = f"window_{int(time.time())}.png"
            filepath = SCREENSHOT_DIR / filename
            filepath.write_bytes(buffered.getvalue())

            logger.info("已擷取視窗: %s", window.title)
            return {
                "filename": filename,
                "title": window.title,
                "path": str(filepath),
            }
        except Exception as exc:  # pragma: no cover - 依賴桌面環境
            logger.error("視窗擷取失敗: %s", exc)
            return None

    @staticmethod
    def capture_running_programs(window_titles: List[str], project_name: Optional[str] = None) -> List[Dict[str, Any]]:
        screenshots: List[Dict[str, Any]] = []
        captured_titles = set()
        windows = pwc.getAllWindows()

        for target_title in window_titles:
            window = WindowMatcher.find_matching_window(target_title, windows)
            if window and window.title not in captured_titles:
                screenshot = ScreenCapture.capture_window_pywinctl(window)
                if screenshot:
                    screenshots.append(screenshot)
                captured_titles.add(window.title)

        if project_name:
            vscode_window = VSCodeController.find_vscode_window(project_name)
            if vscode_window and vscode_window.title not in captured_titles:
                screenshot = ScreenCapture.capture_window_pywinctl(vscode_window)
                if screenshot:
                    screenshots.append(screenshot)
                captured_titles.add(vscode_window.title)

        return screenshots


class ProgramManager:
    """管理執行中的程式"""

    running_programs: Dict[int, Dict[str, Any]] = {}

    @classmethod
    def add_program(cls, process: subprocess.Popen, filename: str, folder_path: str, window_title: Optional[str] = None) -> None:
        if process is None:
            return
        cls.running_programs[process.pid] = {
            'process': process,
            'filename': filename,
            'folder_path': folder_path,
            'window_title': window_title,
            'start_time': datetime.now(),
            'pid': process.pid,
        }
        logger.info("已添加程式到管理列表: PID %s, 檔案 %s", process.pid, filename)

    @classmethod
    def check_programs(cls) -> List[Dict[str, Any]]:
        to_remove: List[int] = []
        status: List[Dict[str, Any]] = []

        for pid, info in list(cls.running_programs.items()):
            poll_result = info['process'].poll()
            if poll_result is None:
                run_time = (datetime.now() - info['start_time']).seconds
                status.append({
                    'pid': pid,
                    'filename': info['filename'],
                    'window_title': info.get('window_title'),
                    'status': 'running',
                    'run_time': run_time,
                })
            else:
                to_remove.append(pid)
                status.append({
                    'pid': pid,
                    'filename': info['filename'],
                    'window_title': info.get('window_title'),
                    'status': 'finished',
                    'exit_code': poll_result,
                })

        for pid in to_remove:
            cls.running_programs.pop(pid, None)
            logger.info("程式已結束並從列表移除: PID %s", pid)

        return status

    @classmethod
    def terminate_program(cls, pid: int) -> bool:
        if pid in cls.running_programs:
            try:
                cls.running_programs[pid]['process'].terminate()
                time.sleep(0.5)
                if cls.running_programs[pid]['process'].poll() is None:
                    cls.running_programs[pid]['process'].kill()
                cls.running_programs.pop(pid, None)
                logger.info("已終止程式: PID %s", pid)
                return True
            except Exception as exc:  # pragma: no cover - 依賴系統環境
                logger.error("終止程式失敗: %s", exc)
                cls.running_programs.pop(pid, None)
        return False

    @classmethod
    def run_file(cls, filepath: str, folder_path: str, file_info=None):
        file_ext = Path(filepath).suffix.lower()
        window_title = getattr(file_info, 'window_title', None) if file_info else None

        try:
            process = None
            if file_info and getattr(file_info, 'is_web_app', False):
                if file_ext == '.html' and getattr(file_info, 'can_open_standalone', False):
                    cls.open_standalone_browser(f'file:///{Path(filepath).resolve()}', getattr(file_info, 'web_title', "Web App"))
                    return None
                if file_ext == '.py':
                    process = cls._run_python(filepath, folder_path, getattr(file_info, 'opens_window', False))
                elif file_ext == '.js':
                    process = cls._run_node(filepath, folder_path)
                if not getattr(file_info, 'can_open_standalone', False) and getattr(file_info, 'server_address', None):
                    time.sleep(2.5)
                    cls.open_standalone_browser(file_info.server_address, getattr(file_info, 'web_title', "Web App"))
            elif file_ext == '.py':
                process = cls._run_python(filepath, folder_path, getattr(file_info, 'opens_window', False))
            elif file_ext == '.js':
                process = cls._run_node(filepath, folder_path)
            elif file_ext == '.html':
                import webbrowser

                webbrowser.open(f'file:///{Path(filepath).resolve()}')
                return None
            else:
                logger.warning("不支援直接執行的檔案類型: %s", file_ext)
                return None

            if process:
                cls.add_program(process, Path(filepath).name, folder_path, window_title)
            return process
        except Exception as exc:
            logger.error("執行檔案失敗 %s: %s", filepath, exc)
            raise

    @classmethod
    def _run_python(cls, filepath: str, folder_path: str, opens_window: bool = False):
        logger.info("執行 Python 檔案: %s, 是否開啟視窗: %s", filepath, opens_window)
        if platform.system() == 'Windows':
            if opens_window:
                return subprocess.Popen(
                    [sys.executable, str(filepath)],
                    cwd=folder_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
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
                startupinfo=startupinfo,
            )

        return subprocess.Popen(
            [sys.executable, str(filepath)],
            cwd=folder_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
        )

    @classmethod
    def _run_node(cls, filepath: str, folder_path: str):
        return subprocess.Popen(
            ['node', str(filepath)],
            cwd=folder_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
        )

    @classmethod
    def open_standalone_browser(cls, url: str, title: str = "Web App"):
        try:
            logger.info("嘗試以獨立視窗模式開啟 URL: %s", url)
            browser_opened = False
            if platform.system() == 'Windows':
                possible_paths = {
                    "chrome": [
                        r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                        r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                        os.path.expanduser(r"~\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"),
                    ],
                    "edge": [
                        r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
                        r"C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
                    ],
                }

                for browser, paths in possible_paths.items():
                    for path in paths:
                        if os.path.exists(path):
                            subprocess.Popen([
                                path,
                                '--new-window',
                                f'--app={url}',
                                '--window-size=1200,800',
                                f'--user-data-dir={CONFIG_DIR / f"{browser}_profile"}',
                            ])
                            logger.info("使用 %s 獨立視窗模式開啟", browser.capitalize())
                            browser_opened = True
                            break
                    if browser_opened:
                        break

            elif platform.system() == 'Darwin':
                chrome_app = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                if os.path.exists(chrome_app):
                    subprocess.Popen([
                        chrome_app,
                        '--new-window',
                        f'--app={url}',
                        '--window-size=1200,800',
                        f'--user-data-dir={CONFIG_DIR / "chrome_profile"}',
                    ])
                    browser_opened = True
                else:
                    subprocess.Popen(['open', '-n', '-a', 'Safari', url])
                    browser_opened = True

            if not browser_opened:
                import webbrowser

                webbrowser.open_new(url)
                logger.info("後備方案：使用預設瀏覽器開啟新視窗/分頁")
        except Exception as exc:  # pragma: no cover
            logger.error("開啟獨立瀏覽器失敗: %s", exc)
            import webbrowser

            webbrowser.open_new(url)


class ProcessManager:
    """主要處理流程管理器"""

    @staticmethod
    def run_automation_process(folder_path: str, prompt: str, config: AIConfig) -> ProcessResult:
        result = ProcessResult(success=False)
        try:
            logger.info("Step 1: 呼叫 Gemini AI...")
            ai_response, json_data = GeminiAI.generate_content(prompt, config)
            result.ai_response = ai_response
            result.ai_response_json = json_data

            logger.info("Step 2: 解析 AI 回應...")
            try:
                if json_data:
                    logger.info("使用 JSON 模式解析")
                    project = CodeProcessor.parse_json_response(json_data)
                else:
                    logger.info("嘗試從文本中提取 JSON")
                    json_start = ai_response.find('{')
                    json_end = ai_response.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = ai_response[json_start:json_end].replace('\\n', '\n').replace('\\t', '\t')
                        project = CodeProcessor.parse_json_response(json.loads(json_str))
                        logger.info("成功從文本中提取並解析 JSON")
                    else:
                        logger.info("使用文本模式解析")
                        project = CodeProcessor.parse_text_response(ai_response)

                result.project_data = project
            except (ValueError, KeyError, json.JSONDecodeError) as parse_error:
                logger.error("解析 AI 回應失敗: %s", parse_error)
                result.error = f"解析失敗: {parse_error}"
                error_details = (
                    "=== ❌ 解析錯誤 ===\n"
                    f"{parse_error}\n\n"
                    "=== 🔍 可能的原因 ===\n"
                    "1. AI 回應格式不正確\n"
                    "2. JSON 結構有誤\n"
                    "3. 程式碼格式化問題\n\n"
                    "=== 💡 解決建議 ===\n"
                    "1. 嘗試切換到文本模式\n"
                    "2. 調整 AI 模型（建議使用 Gemini 2.5 Pro）\n"
                    "3. 簡化您的需求描述\n"
                    "4. 檢查 API Key 是否有效\n\n"
                    "=== 🤖 AI 原始回應 ===\n"
                    "請查看下方「AI 回應」區域以檢視完整內容。"
                )
                result.output = error_details
                if "```" in ai_response:
                    result.output += "\n=== 🔍 檢測到程式碼區塊 ===\n您可以手動複製下方 AI 回應中的程式碼。"
                return result

            logger.info("Step 3: 安裝必要套件...")
            all_requirements: List[str] = []
            for file in project.files:
                if file.install_requirements:
                    all_requirements.extend(file.install_requirements)
            if all_requirements:
                result.installation_logs = CodeProcessor.install_packages(all_requirements)

            logger.info("Step 4: 儲存專案檔案...")
            saved_files = CodeProcessor.save_project_files(folder_path, project)
            result.files_created = saved_files

            logger.info("Step 5: 啟動 VS Code...")
            project_dir = str(Path(folder_path) / project.project_name)
            filenames_to_open = [f.filename for f in project.files[:3]]
            vscode_result = VSCodeController.launch_and_open(project_dir, filenames_to_open)

            logger.info("Step 6: 執行程式...")
            execution_status = "尚未執行"
            execution_detail = ""
            window_titles_to_capture: List[str] = []

            if project.main_file:
                main_file_path = Path(project_dir) / project.main_file
                main_file_info = next((file for file in project.files if file.filename == project.main_file), None)

                if main_file_info:
                    process = ProgramManager.run_file(str(main_file_path), project_dir, main_file_info)
                    if process:
                        time.sleep(0.5)
                        poll_result = process.poll()
                        if poll_result is None:
                            execution_status = "✅ 程式已在背景成功啟動"
                            execution_detail = f"程序 ID (PID): {process.pid}"

                            if main_file_info.opens_window or main_file_info.is_web_app:
                                for file in project.files:
                                    if file.opens_window and file.window_title:
                                        window_titles_to_capture.append(file.window_title)
                                    elif file.is_web_app and file.web_title:
                                        window_titles_to_capture.append(file.web_title)

                                time.sleep(4 if main_file_info.is_web_app else 3)
                                if window_titles_to_capture:
                                    program_screenshots = ScreenCapture.capture_running_programs(window_titles_to_capture)
                                    result.screenshots.extend(s['filename'] for s in program_screenshots)
                                    if program_screenshots:
                                        execution_detail += f"\n已擷取 {len(program_screenshots)} 個視窗"
                                    else:
                                        execution_detail += "\n注意：視窗可能需要更多時間才能顯示"

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
                    elif main_file_info.is_web_app and main_file_path.suffix.lower() == '.html':
                        execution_status = "✅ 已開啟 HTML 檔案"
                        execution_detail = "已在獨立瀏覽器視窗中開啟"
                        if main_file_info.web_title:
                            window_titles_to_capture.append(main_file_info.web_title)
                            time.sleep(2)
                            program_screenshots = ScreenCapture.capture_running_programs(window_titles_to_capture)
                            result.screenshots.extend(s['filename'] for s in program_screenshots)

            result.output = (
                "=== 🎉 專案生成成功 ===\n"
                f"📦 專案名稱: {project.project_name}\n"
                f"📝 描述: {project.description}\n"
                f"📁 專案位置: {project_dir}\n"
                f"📄 檔案數量: {len(project.files)}\n"
                f"🎯 主檔案: {project.main_file or '無指定'}\n\n"
                "=== 📋 檔案列表 ===\n"
            )

            for file in project.files:
                file_icon = "🐍" if file.filetype == "python" else "📄"
                window_info = f" (視窗: {file.window_title})" if file.opens_window and file.window_title else ""
                result.output += f"{file_icon} {file.filename} - {file.description or file.filetype}{window_info}\n"

            result.output += (
                "=== 💻 VS Code 狀態 ===\n"
                f"{'✅ 已開啟' if vscode_result.get('success') else '⚠️ 開啟失敗'}\n"
                f"已開啟檔案: {', '.join(vscode_result.get('files_opened', []))}\n\n"
                "=== ⚡ 程式執行狀態 ===\n"
                f"{execution_status}\n"
                f"{execution_detail}\n"
            )

            if project.setup_instructions:
                result.output += "=== 🔧 設置指令 ===\n" + "\n".join(f"• {inst}" for inst in project.setup_instructions) + "\n"
            if project.run_instructions:
                result.output += "=== ▶️ 執行指令 ===\n" + "\n".join(f"• {inst}" for inst in project.run_instructions) + "\n"
            if result.installation_logs:
                result.output += "=== 📦 套件安裝日誌 ===\n" + "\n".join(result.installation_logs) + "\n"

            result.output += (
                "=== 💡 操作提示 ===\n"
                "1. 查看 VS Code 視窗以編輯程式碼\n"
                "2. 使用「延遲 5 秒後擷取」來擷取運行畫面\n"
                "3. 查看「執行中的程式」監控程式狀態\n"
                "4. 如果是圖形程式，應該會看到新視窗出現"
            )

            result.success = True
        except Exception as exc:  # pragma: no cover - 整體流程依賴桌面環境
            result.error = str(exc)
            logger.error("處理流程失敗: %s", exc)
            import traceback

            logger.error(traceback.format_exc())
            if not result.ai_response:
                result.ai_response = "無法獲取 AI 回應"

        return result


__all__ = [
    "ProcessManager",
    "ProgramManager",
    "ScreenCapture",
    "VSCodeController",
]
