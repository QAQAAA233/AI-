"""核心數據結構與共用工具。

此模組集中管理後端會頻繁共用的變量與資料模型，
包含日誌設定、檔案儲存路徑、JSON 解析工具等，
避免關鍵狀態分散在不同檔案。"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================
# 日誌與路徑設定
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger("ai_controller")


CONFIG_DIR = Path.home() / '.ai_controller_v3'
CONFIG_FILE = CONFIG_DIR / 'config.json'
SCREENSHOT_DIR = CONFIG_DIR / 'screenshots'
LOG_DIR = CONFIG_DIR / 'logs'
PROJECTS_DIR = CONFIG_DIR / 'projects'

for directory in (CONFIG_DIR, SCREENSHOT_DIR, LOG_DIR, PROJECTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)


# ============================================
# 數據模型
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
    response_mode: str = "json"
    system_instruction: str = ""
    generation_params: Dict[str, Any] = None
    safety_settings: Dict[str, str] = None
    automation_settings: Dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.generation_params is None:
            self.generation_params = {
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 64,
                "max_output_tokens": 8192,
                "candidate_count": 1,
                "stop_sequences": [],
                "response_mime_type": "application/json"
                if self.response_mode == ResponseMode.JSON.value
                else "text/plain",
            }
        if self.safety_settings is None:
            self.safety_settings = {
                "HARM_CATEGORY_HARASSMENT": "BLOCK_MEDIUM_AND_ABOVE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_MEDIUM_AND_ABOVE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_MEDIUM_AND_ABOVE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_MEDIUM_AND_ABOVE",
            }
        if self.automation_settings is None:
            self.automation_settings = {
                "auto_error_fix": False,
                "auto_optimize": False,
                "auto_test": False,
                "monitor_interval": 5,
            }


@dataclass
class ProcessResult:
    """自動化流程的輸出結果"""

    success: bool
    output: str = ""
    files_created: List[str] = field(default_factory=list)
    project_data: Optional[ProjectOutput] = None
    ai_response: str = ""
    ai_response_json: Optional[Dict[str, Any]] = None
    installation_logs: List[str] = field(default_factory=list)
    error: str = ""
    screenshots: List[str] = field(default_factory=list)


# ============================================
# JSON Schema 與系統指令
# ============================================


def get_json_schema() -> Dict[str, Any]:
    """Gemini API 的 JSON Schema"""

    return {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "專案名稱",
            },
            "description": {
                "type": "string",
                "description": "專案描述",
            },
            "main_file": {
                "type": "string",
                "description": "主要執行檔案",
            },
            "setup_instructions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "設置指令",
            },
            "run_instructions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "執行指令",
            },
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "檔案名稱（含副檔名）",
                        },
                        "filetype": {
                            "type": "string",
                            "enum": [
                                "python",
                                "javascript",
                                "html",
                                "css",
                                "typescript",
                                "java",
                                "cpp",
                                "c",
                                "go",
                                "rust",
                                "ruby",
                                "php",
                                "swift",
                                "kotlin",
                                "sql",
                                "shell",
                                "yaml",
                                "json",
                                "xml",
                                "markdown",
                                "text",
                            ],
                            "description": "檔案類型",
                        },
                        "code": {
                            "type": "string",
                            "description": "完整程式碼內容",
                        },
                        "opens_window": {
                            "type": "boolean",
                            "description": "是否會開啟視窗",
                        },
                        "window_title": {
                            "type": ["string", "null"],
                            "description": "視窗標題（如果有）",
                        },
                        "install_requirements": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "安裝需求",
                        },
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "相依套件",
                        },
                        "description": {
                            "type": "string",
                            "description": "檔案描述",
                        },
                        "run_command": {
                            "type": ["string", "null"],
                            "description": "執行命令",
                        },
                        "is_web_app": {
                            "type": "boolean",
                            "description": "是否為網頁應用",
                        },
                        "can_open_standalone": {
                            "type": "boolean",
                            "description": "主程式是否能自動開啟獨立瀏覽器視窗",
                        },
                        "server_address": {
                            "type": ["string", "null"],
                            "description": "伺服器地址",
                        },
                        "web_title": {
                            "type": ["string", "null"],
                            "description": "網頁標題",
                        },
                    },
                    "required": ["filename", "filetype", "code", "opens_window"],
                },
            },
        },
        "required": ["project_name", "description", "files"],
    }


def get_json_system_instruction() -> str:
    """JSON 模式的系統指令"""

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
# JSON/專案處理工具
# ============================================


def extract_json_object(text: str) -> Optional[str]:
    """從文字中提取第一個完整的 JSON 物件字串."""

    if not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].rstrip()

    stack = 0
    start: Optional[int] = None
    for index, char in enumerate(cleaned):
        if char == '{':
            if start is None:
                start = index
            stack += 1
        elif char == '}' and start is not None:
            stack -= 1
            if stack == 0:
                return cleaned[start : index + 1]

    if cleaned.startswith('{') and cleaned.endswith('}'):
        return cleaned

    return None


class CodeProcessor:
    """程式碼解析和處理器"""

    @staticmethod
    def parse_json_response(json_data: Dict[str, Any]) -> ProjectOutput:
        """解析 JSON 格式的 AI 回應"""

        files: List[FileOutput] = []
        for file_data in json_data.get('files', []):
            code = file_data.get('code', '')
            if isinstance(code, str):
                code = code.replace('\\n', '\n')
                code = code.replace('\\t', '\t')
                code = code.replace('\\"', '"')
                code = code.replace("\\'", "'")

            files.append(
                FileOutput(
                    filename=file_data.get('filename', 'untitled.txt'),
                    filetype=file_data.get('filetype', 'text'),
                    code=code,
                    opens_window=file_data.get('opens_window', False),
                    window_title=file_data.get('window_title'),
                    install_requirements=file_data.get('install_requirements'),
                    dependencies=file_data.get('dependencies'),
                    description=file_data.get('description'),
                    run_command=file_data.get('run_command'),
                    is_web_app=file_data.get('is_web_app', False),
                    can_open_standalone=file_data.get('can_open_standalone', False),
                    server_address=file_data.get('server_address'),
                    web_title=file_data.get('web_title'),
                )
            )

        return ProjectOutput(
            project_name=json_data.get('project_name', 'untitled_project'),
            description=json_data.get('description', ''),
            files=files,
            main_file=json_data.get('main_file'),
            setup_instructions=json_data.get('setup_instructions'),
            run_instructions=json_data.get('run_instructions'),
        )

    @staticmethod
    def parse_text_response(response_text: str) -> ProjectOutput:
        """解析文本格式的 AI 回應（向後相容）"""

        code_patterns = [
            r'```(?:python)?\n?(.*?)```',
            r'```(.*?)```',
            r'`([^`]+)`',
        ]

        code: Optional[str] = None
        for pattern in code_patterns:
            match = re.search(pattern, response_text, re.DOTALL)
            if match:
                code = match.group(1).strip()
                break

        if not code:
            lines = response_text.split('\n')
            code_lines: List[str] = []
            in_code = False
            for line in lines:
                if re.match(r'^\s*(import |from |def |class |if __name__|#)', line):
                    in_code = True
                if in_code:
                    code_lines.append(line)
                elif code_lines and not line.strip():
                    code_lines.append(line)
                elif code_lines and not re.match(r'^\s', line) and line.strip():
                    break

            if code_lines:
                code = '\n'.join(code_lines)

        if not code:
            raise ValueError(
                "找不到程式碼。請確保 AI 回應包含程式碼區塊（```...```）或有效的程式碼內容。\n"
                f"AI 回應前 500 字元：\n{response_text[:500]}..."
            )

        filename_patterns = [
            r'/\*/(.*?)/\*/',
            r'filename[:\s]+["\']?([^"\'\n]+)["\']?',
            r'檔案名稱[:\s]+["\']?([^"\'\n]+)["\']?',
            r'([a-zA-Z_][a-zA-Z0-9_]*\.py)',
        ]

        filename: Optional[str] = None
        for pattern in filename_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                filename = match.group(1).strip()
                break

        if not filename:
            logger.warning("找不到檔案名稱，使用預設名稱")
            filename = "generated_code.py"

        if '.' not in filename:
            filename += '.py'

        install_commands: List[str] = []
        install_patterns = [
            r';;;(.*);;;',
            r'pip install ([a-zA-Z0-9_-]+)',
            r'npm install ([a-zA-Z0-9_-]+)',
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

        opens_window = any(
            lib in code.lower() for lib in ['pygame', 'tkinter', 'pyqt', 'wx', 'kivy', 'pyglet']
        )
        window_title: Optional[str] = None

        if opens_window:
            title_patterns = [
                r'set_caption\(["\'](.+?)["\']\)',
                r'title\s*=\s*["\'](.+?)["\']',
                r'setWindowTitle\(["\'](.+?)["\']\)',
                r'SetTitle\(["\'](.+?)["\']\)',
            ]
            for pattern in title_patterns:
                match = re.search(pattern, code)
                if match:
                    window_title = match.group(1)
                    break

        file_output = FileOutput(
            filename=filename,
            filetype="python",
            code=code,
            opens_window=opens_window,
            window_title=window_title,
            install_requirements=install_commands if install_commands else None,
            description="Generated Python file",
        )

        return ProjectOutput(
            project_name=filename.replace('.py', '').replace('.js', '').replace('.html', ''),
            description="AI Generated Project",
            files=[file_output],
            main_file=filename,
        )

    @staticmethod
    def install_packages(install_requirements: List[str]) -> List[str]:
        logs: List[str] = []

        for requirement in install_requirements:
            if not requirement:
                continue

            logger.info("執行安裝指令: %s", requirement)
            parts = requirement.split()
            full_command = [sys.executable, "-m"] + parts if parts[0] == 'pip' else parts

            try:
                result = subprocess.run(
                    full_command,
                    capture_output=True,
                    text=True,
                    check=True,
                    encoding='utf-8',
                )
                log = f"✅ 成功執行: {requirement}\n" + result.stdout
                if result.stderr:
                    log += f"\n⚠️ 警告:\n{result.stderr}"
                logs.append(log)
            except subprocess.CalledProcessError as exc:
                error_msg = f"❌ 安裝失敗: {requirement}\n錯誤: {exc.stderr}"
                logger.error(error_msg)
                logs.append(error_msg)

        return logs

    @staticmethod
    def save_project_files(folder_path: str, project: ProjectOutput) -> List[str]:
        saved_files: List[str] = []
        project_dir = Path(folder_path) / project.project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        for file in project.files:
            filepath = project_dir / file.filename
            filepath.parent.mkdir(parents=True, exist_ok=True)

            with open(filepath, 'w', encoding='utf-8') as handle:
                handle.write(file.code)
            logger.info("已儲存檔案: %s", filepath)
            saved_files.append(str(filepath))

        info_file = project_dir / "PROJECT_INFO.json"
        with open(info_file, 'w', encoding='utf-8') as handle:
            json.dump(
                {
                    "project_name": project.project_name,
                    "description": project.description,
                    "main_file": project.main_file,
                    "setup_instructions": project.setup_instructions,
                    "run_instructions": project.run_instructions,
                    "files": [asdict(file) for file in project.files],
                },
                handle,
                indent=2,
                ensure_ascii=False,
            )
        saved_files.append(str(info_file))

        return saved_files


__all__ = [
    "AIConfig",
    "CodeProcessor",
    "CONFIG_DIR",
    "CONFIG_FILE",
    "extract_json_object",
    "FileOutput",
    "FileType",
    "LOG_DIR",
    "ProcessResult",
    "PROJECTS_DIR",
    "ResponseMode",
    "SCREENSHOT_DIR",
    "get_json_schema",
    "get_json_system_instruction",
    "logger",
]
