"""AI 自動化開發控制器 Pro 入口模組。"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Any, Dict, List

import webview
from flask import Flask, jsonify, render_template, request, send_file

from automation import ProcessManager, ProgramManager, ScreenCapture
from core import AIConfig, SCREENSHOT_DIR, logger
from services import ConfigManager


app = Flask(__name__)
HOST = '127.0.0.1'
PORT = 5001


window = None  # type: ignore[assignment]


@app.route('/')
def index() -> str:
    """主頁面"""

    return render_template('index.html')


@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """處理配置 API"""

    if request.method == 'GET':
        config = ConfigManager.load()
        return jsonify(asdict(config))

    data = request.get_json() or {}
    config = AIConfig(**data)
    success = ConfigManager.save(config)
    if success:
        return jsonify({'success': True, 'message': '配置已儲存'})
    return jsonify({'success': False, 'error': '儲存失敗'}), 500


@app.route('/select-folder', methods=['GET'])
def select_folder():
    """選擇資料夾"""

    global window

    if not window:
        return jsonify({'success': False, 'error': 'Webview 視窗不存在'}), 500

    try:
        result = window.create_file_dialog(webview.FOLDER_DIALOG)  # type: ignore[attr-defined]
        path = result[0] if result else None
        if path:
            logger.info("選擇了資料夾: %s", path)
            return jsonify({'success': True, 'path': path})
        return jsonify({'success': False, 'error': '未選擇資料夾'})
    except Exception as exc:  # pragma: no cover - 依賴桌面環境
        logger.error("選擇資料夾失敗: %s", exc)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/run-process', methods=['POST'])
def run_process():
    """執行自動化流程"""

    try:
        data: Dict[str, Any] = request.get_json() or {}
        folder_path = data.get('folder_path')
        prompt = data.get('prompt')
        config_data = data.get('config', {})

        if not folder_path or not prompt:
            return jsonify({
                'success': False,
                'error': '缺少必要參數（資料夾路徑或 AI 指令）',
                'ai_response': '',
            }), 400

        config = AIConfig(**config_data)
        result = ProcessManager.run_automation_process(folder_path, prompt, config)

        response_data: Dict[str, Any] = {
            'success': result.success,
            'output': result.output,
            'files_created': result.files_created,
            'ai_response': result.ai_response or '無 AI 回應',
            'ai_response_json': result.ai_response_json,
            'installation_logs': result.installation_logs,
            'error': result.error,
            'screenshots': result.screenshots,
        }

        if result.project_data:
            response_data['project'] = {
                'name': result.project_data.project_name,
                'description': result.project_data.description,
                'files_count': len(result.project_data.files),
                'main_file': result.project_data.main_file,
                'has_gui': any(file.opens_window for file in result.project_data.files),
            }

        return jsonify(response_data)
    except Exception as exc:  # pragma: no cover - 依賴外部服務
        logger.error("執行流程時發生錯誤: %s", exc)
        import traceback

        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(exc),
            'ai_response': '執行過程中發生未預期的錯誤',
            'output': f'系統錯誤: {exc}',
        }), 500


@app.route('/capture-screenshots', methods=['POST'])
def capture_screenshots():
    """擷取螢幕畫面"""

    try:
        data: Dict[str, Any] = request.get_json() or {}
        capture_mode = data.get('mode', 'programs')
        window_titles = data.get('window_titles', [])
        project_name = data.get('project_name')

        screenshots: List[Dict[str, Any]] = []

        if capture_mode == 'programs':
            if window_titles or project_name:
                time.sleep(2)
                screenshots = ScreenCapture.capture_running_programs(window_titles, project_name)
            else:
                logger.warning("沒有指定視窗標題或專案名稱")
        elif capture_mode == 'all':
            logger.info("不建議使用 'all' 模式")
            if window_titles or project_name:
                time.sleep(2)
                screenshots = ScreenCapture.capture_running_programs(window_titles, project_name)

        logger.info("擷取完成，共 %s 張截圖，模式: %s", len(screenshots), capture_mode)
        return jsonify({'success': True, 'screenshots': screenshots, 'count': len(screenshots)})
    except Exception as exc:  # pragma: no cover - 依賴桌面環境
        logger.error("擷取螢幕失敗: %s", exc)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/screenshot/<filename>')
def serve_screenshot(filename: str):
    """提供螢幕截圖"""

    filepath = SCREENSHOT_DIR / filename
    if filepath.exists():
        return send_file(filepath, mimetype='image/png', as_attachment=False, download_name=filename)
    return "Screenshot not found", 404


@app.route('/running-programs', methods=['GET'])
def get_running_programs():
    """獲取運行中的程式列表"""

    try:
        status = ProgramManager.check_programs()
        return jsonify({'success': True, 'programs': status, 'count': len(status)})
    except Exception as exc:  # pragma: no cover
        logger.error("獲取程式狀態失敗: %s", exc)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/terminate-program/<int:pid>', methods=['POST'])
def terminate_program(pid: int):
    """終止指定的程式"""

    try:
        success = ProgramManager.terminate_program(pid)
        if success:
            return jsonify({'success': True, 'message': f'程式 PID {pid} 已終止'})
        return jsonify({'success': False, 'error': f'找不到 PID {pid} 的程式'}), 404
    except Exception as exc:  # pragma: no cover
        logger.error("終止程式失敗: %s", exc)
        return jsonify({'success': False, 'error': str(exc)}), 500


def run_flask() -> None:
    """運行 Flask 伺服器"""

    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


def main() -> None:
    """主程式入口"""

    logger.info("=== AI 自動化開發控制器 Pro 啟動 ===")
    logger.info("配置目錄: %s", SCREENSHOT_DIR.parent)

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    time.sleep(1)

    global window
    window = webview.create_window(
        'AI 自動化開發控制器 Pro',
        f'http://{HOST}:{PORT}',
        width=1280,
        height=960,
        resizable=True,
        on_top=False,
    )

    logger.info("正在啟動圖形界面...")
    webview.start()


if __name__ == '__main__':
    main()
