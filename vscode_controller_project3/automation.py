"""Automation helpers for controlling VS Code, screen capture, and running programs."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
import re
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import mss
import mss.tools
import pyautogui
import pyperclip
import pywinctl as pwc
from difflib import SequenceMatcher

from core import CONFIG_DIR, SCREENSHOT_DIR, FileOutput, logger


class VSCodeController:
    """VS Code 自動化控制器"""

    @staticmethod
    def find_vscode_window(folder_name: str, timeout: int = 15) -> Optional[pwc.Window]:
        """使用 PyWinCtl 尋找 VS Code 視窗"""

        start_time = time.time()
        while time.time() - start_time < timeout:
            all_windows = pwc.getAllWindows()
            for window in all_windows:
                if window.title:
                    title_lower = window.title.lower()
                    if 'visual studio code' in title_lower and folder_name.lower() in title_lower:
                        return window
            time.sleep(0.5)

        vscode_windows = pwc.getWindowsWithTitle("Visual Studio Code", condition=pwc.Re.CONTAINS)
        if vscode_windows:
            return vscode_windows[0]
        return None

    @staticmethod
    def launch_and_open(folder_path: str, filenames: List[str]) -> Dict[str, Any]:
        """啟動 VS Code 並打開指定檔案"""

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
                subprocess.Popen(
                    ['code', folder_path, str(first_file)],
                    shell=(platform.system() == 'Windows'),
                )
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
        except Exception as exc:
            result["message"] = f"VS Code 控制失敗: {exc}"
            logger.error(result["message"])

        return result


class WindowMatcher:
    """視窗匹配輔助類"""

    @staticmethod
    def fuzzy_match(string1: str, string2: str, threshold: float = 0.6) -> bool:
        ratio = SequenceMatcher(None, string1.lower(), string2.lower()).ratio()
        return ratio >= threshold

    @staticmethod
    def normalize_title(title: str) -> str:
        browser_suffixes = [
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
        for suffix in browser_suffixes:
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
            if window.title:
                window_lower = window.title.lower()
                if target_normalized in window_lower or target_lower in window_lower:
                    logger.info("包含匹配找到視窗: %s", window.title)
                    return window

        best_match: Optional[pwc.Window] = None
        best_ratio = 0.0
        for window in all_windows:
            if window.title:
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

        return None


class ScreenCapture:
    """螢幕擷取管理器 - 使用 PyWinCtl"""

    @staticmethod
    def capture_all_monitors() -> List[Dict[str, Any]]:
        screenshots: List[Dict[str, Any]] = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with mss.mss() as sct:
            for index, monitor in enumerate(sct.monitors[1:], 1):
                filename = f"monitor_{index}_{timestamp}.png"
                filepath = SCREENSHOT_DIR / filename
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(filepath))
                screenshots.append(
                    {
                        "name": f"螢幕 {index}",
                        "filename": filename,
                        "path": str(filepath),
                        "width": monitor["width"],
                        "height": monitor["height"],
                        "timestamp": timestamp,
                    }
                )
                logger.info("已擷取螢幕 %s: %s", index, filepath)
        return screenshots

    @staticmethod
    def capture_window_pywinctl(window: pwc.Window) -> Optional[Dict[str, Any]]:
        try:
            if window.isMinimized:
                window.restore()
            window.activate()
            time.sleep(0.5)

            box = window.box
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', window.title[:50])
            filename = f"window_{safe_title}_{timestamp}.png"
            filepath = SCREENSHOT_DIR / filename

            with mss.mss() as sct:
                monitor = {
                    "top": max(0, box.top),
                    "left": max(0, box.left),
                    "width": min(box.width, 3840),
                    "height": min(box.height, 2160),
                }
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(filepath))

            logger.info("已擷取視窗 '%s': %s", window.title, filepath)
            return {
                "name": window.title,
                "filename": filename,
                "path": str(filepath),
                "width": box.width,
                "height": box.height,
                "timestamp": timestamp,
            }
        except Exception as exc:
            logger.error("擷取視窗失敗 '%s': %s", window.title if window else '未知', exc)
            return None

    @staticmethod
    def capture_running_programs(
        window_titles: Optional[List[str]] = None,
        project_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        screenshots: List[Dict[str, Any]] = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info("開始擷取程式視窗，指定標題: %s, 專案: %s", window_titles, project_name)

        all_windows = pwc.getAllWindows()
        logger.info("當前系統所有視窗：")
        for window in all_windows:
            if window.title and window.isVisible:
                logger.info("  - %s", window.title)

        captured_titles = set()
        found_windows: List[tuple[pwc.Window, str]] = []

        if window_titles:
            for target_title in window_titles:
                matching_window = WindowMatcher.find_matching_window(target_title, all_windows)
                if matching_window and matching_window.title not in captured_titles:
                    found_windows.append((matching_window, "program"))
                    captured_titles.add(matching_window.title)
                    logger.info("找到程式視窗: %s", matching_window.title)
                else:
                    logger.warning("未找到匹配的視窗: %s", target_title)

        if project_name:
            vscode_window = VSCodeController.find_vscode_window(project_name, timeout=2)
            if vscode_window and vscode_window.title not in captured_titles:
                found_windows.append((vscode_window, "vscode_project"))
                captured_titles.add(vscode_window.title)
                logger.info("找到專案 VS Code 視窗: %s", vscode_window.title)

        for window, capture_type in found_windows:
            screenshot = ScreenCapture.capture_window_pywinctl(window)
            if screenshot:
                screenshot["type"] = capture_type
                screenshots.append(screenshot)

        logger.info("擷取完成，共 %s 個視窗", len(screenshots))

        if not screenshots and window_titles:
            logger.info("使用更寬鬆的搜尋策略...")
            for target_title in window_titles:
                windows = pwc.getWindowsWithTitle(
                    target_title,
                    condition=pwc.Re.CONTAINS,
                    flags=pwc.Re.IGNORECASE,
                )
                for window in windows:
                    if window.title not in captured_titles:
                        screenshot = ScreenCapture.capture_window_pywinctl(window)
                        if screenshot:
                            screenshots.append(screenshot)
                        captured_titles.add(window.title)
                        logger.info("寬鬆搜尋找到: %s", window.title)

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
                status.append(
                    {
                        'pid': pid,
                        'filename': info['filename'],
                        'window_title': info.get('window_title'),
                        'status': 'running',
                        'run_time': run_time,
                    }
                )
            else:
                to_remove.append(pid)
                status.append(
                    {
                        'pid': pid,
                        'filename': info['filename'],
                        'window_title': info.get('window_title'),
                        'status': 'finished',
                        'exit_code': poll_result,
                    }
                )

        for pid in to_remove:
            if pid in cls.running_programs:
                del cls.running_programs[pid]
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
                del cls.running_programs[pid]
                logger.info("已終止程式: PID %s", pid)
                return True
            except Exception as exc:
                logger.error("終止程式失敗: %s", exc)
                if pid in cls.running_programs:
                    del cls.running_programs[pid]
                return False
        return False

    @classmethod
    def run_file(cls, filepath: str, folder_path: str, file_info: Optional[FileOutput] = None) -> Optional[subprocess.Popen]:
        file_ext = Path(filepath).suffix.lower()
        if not file_info:
            logger.warning("run_file 被呼叫時未提供 file_info，將以基本模式執行")
            file_info = FileOutput(filename=Path(filepath).name, filetype=file_ext.strip('.'), code='')

        window_title = file_info.window_title
        process: Optional[subprocess.Popen] = None

        try:
            if file_info.is_web_app:
                if file_ext == '.html' and file_info.can_open_standalone:
                    cls.open_standalone_browser(f'file:///{Path(filepath).resolve()}', file_info.web_title or "Web App")
                    return None

                if file_ext == '.py':
                    process = cls._run_python(filepath, folder_path, opens_window=file_info.opens_window)
                elif file_ext == '.js':
                    process = cls._run_node(filepath, folder_path)

                if not file_info.can_open_standalone and file_info.server_address:
                    time.sleep(2.5)
                    cls.open_standalone_browser(file_info.server_address, file_info.web_title or "Web App")

            elif file_ext == '.py':
                process = cls._run_python(filepath, folder_path, opens_window=file_info.opens_window)
            elif file_ext == '.js':
                process = cls._run_node(filepath, folder_path)
            elif file_ext == '.html':
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
    def _run_python(cls, filepath: str, folder_path: str, opens_window: bool = False) -> subprocess.Popen:
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
    def _run_node(cls, filepath: str, folder_path: str) -> subprocess.Popen:
        return subprocess.Popen(
            ['node', str(filepath)],
            cwd=folder_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
        )

    @classmethod
    def open_standalone_browser(cls, url: str, title: str = "Web App") -> None:
        try:
            logger.info("嘗試以獨立視窗模式開啟 URL: %s", url)
            browser_opened = False
            if platform.system() == 'Windows':
                possible_paths = {
                    "chrome": [
                        r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                        r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                        r"C:\\Users\\%USERNAME%\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe",
                    ],
                    "edge": [
                        r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
                        r"C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
                    ],
                }

                for browser, paths in possible_paths.items():
                    for raw_path in paths:
                        expanded_path = os.path.expandvars(raw_path)
                        if os.path.exists(expanded_path):
                            chrome_profile = CONFIG_DIR / "chrome_profile"
                            chrome_profile.mkdir(parents=True, exist_ok=True)
                            subprocess.Popen(
                                [
                                    expanded_path,
                                    '--new-window',
                                    f'--app={url}',
                                    '--window-size=1200,800',
                                    f'--user-data-dir={chrome_profile}',
                                    f'--class={title}',
                                ]
                            )
                            browser_opened = True
                            break
                    if browser_opened:
                        break

            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', '-n', '-a', 'Google Chrome', '--args', '--new-window', f'--app={url}'])
                browser_opened = True
            else:
                subprocess.Popen(['xdg-open', url])
                browser_opened = True

            if not browser_opened:
                webbrowser.open_new(url)
                logger.info("後備方案：使用預設瀏覽器開啟新視窗/分頁")
        except Exception as exc:
            logger.error("開啟獨立瀏覽器失敗: %s", exc)
            webbrowser.open_new(url)
