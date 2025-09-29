"""High level automation workflow orchestration."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from core import AIConfig, CodeProcessor, GeminiAI, ProcessResult
from automation import ProgramManager, ScreenCapture, VSCodeController
from core import logger


class ProcessManager:
    """主要處理流程管理器"""

    @staticmethod
    def run_automation_process(
        folder_path: str,
        prompt: str,
        config: AIConfig,
    ) -> ProcessResult:
        """執行完整的自動化流程"""

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
                        json_str = ai_response[json_start:json_end]
                        json_str = json_str.replace('\\n', '\n').replace('\\t', '\t')
                        potential_json = json.loads(json_str)
                        project = CodeProcessor.parse_json_response(potential_json)
                        logger.info("成功從文本中提取並解析 JSON")
                    else:
                        logger.info("使用文本模式解析")
                        project = CodeProcessor.parse_text_response(ai_response)

                result.project_data = project
            except (ValueError, KeyError) as parse_error:
                logger.error("解析 AI 回應失敗: %s", parse_error)
                result.error = f"解析失敗: {parse_error}"
                result.output = (
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

            logger.info("Step 5: 打開 VS Code...")
            filenames_to_open = [file.filename for file in project.files[:3]]
            project_dir = Path(folder_path) / project.project_name
            vscode_result = VSCodeController.launch_and_open(project_dir, filenames_to_open)

            logger.info("Step 6: 執行程式...")
            execution_status = "尚未執行"
            execution_detail = ""
            window_titles_to_capture: List[str] = []

            if project.main_file:
                main_file_path = Path(project_dir) / project.main_file
                main_file_info = next((file for file in project.files if file.filename == project.main_file), None)

                if main_file_info:
                    process = ProgramManager.run_file(
                        str(main_file_path),
                        project_dir,
                        main_file_info,
                    )

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
                                        logger.info("將擷取視窗: %s", file.window_title)
                                    elif file.is_web_app and file.web_title:
                                        window_titles_to_capture.append(file.web_title)
                                        logger.info("將擷取網頁視窗: %s", file.web_title)

                                if main_file_info.is_web_app:
                                    time.sleep(4)
                                else:
                                    time.sleep(3)

                                if window_titles_to_capture:
                                    program_screenshots = ScreenCapture.capture_running_programs(window_titles_to_capture)
                                    for screenshot in program_screenshots:
                                        result.screenshots.append(screenshot['filename'])
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
                            for screenshot in program_screenshots:
                                result.screenshots.append(screenshot['filename'])

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
                "\n=== 💻 VS Code 狀態 ===\n"
                f"{'✅ 已開啟' if vscode_result.get('success') else '⚠️ 開啟失敗'}\n"
                f"已開啟檔案: {', '.join(vscode_result.get('files_opened', []))}\n\n"
                "=== ⚡ 程式執行狀態 ===\n"
                f"{execution_status}\n"
                f"{execution_detail}\n"
            )

            if project.setup_instructions:
                result.output += (
                    "\n=== 🔧 設置指令 ===\n"
                    + "\n".join(f"• {inst}" for inst in project.setup_instructions)
                    + "\n"
                )

            if project.run_instructions:
                result.output += (
                    "\n=== ▶️ 執行指令 ===\n"
                    + "\n".join(f"• {inst}" for inst in project.run_instructions)
                    + "\n"
                )

            if result.installation_logs:
                result.output += (
                    "\n=== 📦 套件安裝日誌 ===\n"
                    + "\n".join(result.installation_logs)
                    + "\n"
                )

            result.output += (
                "\n=== 💡 操作提示 ===\n"
                "1. 查看 VS Code 視窗以編輯程式碼\n"
                "2. 使用「延遲 5 秒後擷取」來擷取運行畫面\n"
                "3. 查看「執行中的程式」監控程式狀態\n"
                "4. 如果是圖形程式，應該會看到新視窗出現"
            )

            result.success = True
            return result
        except Exception as exc:
            result.error = str(exc)
            logger.error("處理流程失敗: %s", exc)
            return result
