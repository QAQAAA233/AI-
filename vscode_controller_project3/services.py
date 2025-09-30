"""後端服務模組：集中管理設定檔與 Gemini AI 呼叫。"""

from __future__ import annotations

import json
import base64
from dataclasses import asdict
from typing import Dict, List, Optional, Tuple

import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold

from core import AIConfig, CONFIG_FILE, extract_json_object, get_json_system_instruction, logger


try:  # Optional Google Cloud Auth support
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError

    HAS_GOOGLE_AUTH = True
except ImportError:  # pragma: no cover - optional dependency
    google = None  # type: ignore
    DefaultCredentialsError = Exception  # type: ignore
    HAS_GOOGLE_AUTH = False


class ConfigManager:
    """配置文件管理器"""

    @staticmethod
    def load() -> AIConfig:
        if not CONFIG_FILE.exists():
            logger.info("配置文件不存在，使用預設配置")
            return AIConfig()

        try:
            data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            return AIConfig(**data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("讀取配置文件失敗: %s", exc)
            return AIConfig()

    @staticmethod
    def save(config: AIConfig) -> bool:
        try:
            CONFIG_FILE.write_text(
                json.dumps(asdict(config), indent=4, ensure_ascii=False),
                encoding='utf-8',
            )
            logger.info("配置文件已儲存")
            return True
        except OSError as exc:
            logger.error("儲存配置文件失敗: %s", exc)
            return False


class GeminiAI:
    """Gemini AI API 管理器"""

    @staticmethod
    def configure(config: AIConfig) -> None:
        if config.connection_method == 'api_key':
            if not config.gemini_api_key:
                raise ValueError("API Key 模式需要提供有效的 API Key")
            genai.configure(api_key=config.gemini_api_key)
            logger.info("已使用 API Key 連接 Gemini")

        elif config.connection_method == 'gcloud_auth':
            if not HAS_GOOGLE_AUTH:
                raise ImportError("缺少 google-auth 套件，請執行: pip install google-auth")
            try:
                credentials, project_id = google.auth.default()  # type: ignore[attr-defined]
                genai.configure(credentials=credentials)
                logger.info("已使用 Google Cloud Auth 連接 (專案: %s)", project_id)
            except DefaultCredentialsError as exc:
                raise ConnectionError("找不到 Google Cloud 憑證，請執行: gcloud auth application-default login") from exc
        else:
            raise ValueError(f"不支援的連接模式: {config.connection_method}")

    @staticmethod
    def generate_content(prompt: str, config: AIConfig) -> Tuple[str, Optional[Dict[str, object]]]:
        GeminiAI.configure(config)

        gen_params = dict(config.generation_params or {})
        if config.response_mode == "json":
            gen_params["response_mime_type"] = "application/json"
            system_instruction = get_json_system_instruction()
        else:
            gen_params["response_mime_type"] = "text/plain"
            system_instruction = config.system_instruction or get_json_system_instruction()

        gen_config = GenerationConfig(**{key: value for key, value in gen_params.items() if value is not None})

        safety_settings = {
            HarmCategory[category]: HarmBlockThreshold[threshold]
            for category, threshold in (config.safety_settings or {}).items()
        }

        model_name = f"models/{config.model_name}"
        logger.info("使用模型: %s, 模式: %s", model_name, config.response_mode)

        model_kwargs = {
            "model_name": model_name,
            "safety_settings": safety_settings,
            "generation_config": gen_config,
        }

        if system_instruction:
            model_kwargs["system_instruction"] = system_instruction

        model = genai.GenerativeModel(**model_kwargs)
        response = model.generate_content(prompt, generation_config=gen_config)

        collected_texts: List[str] = []
        json_candidates: List[str] = []

        def collect_text(text: Optional[str]) -> None:
            if not text:
                return
            normalized = text.strip()
            if not normalized:
                return
            collected_texts.append(normalized)
            json_fragment = extract_json_object(normalized)
            if json_fragment:
                json_candidates.append(json_fragment)

        if getattr(response, "candidates", None):
            for candidate in response.candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None)
                if not parts:
                    continue
                for part in parts:
                    part_text = getattr(part, "text", None)
                    collect_text(part_text)

                    part_dict = part.to_dict() if hasattr(part, "to_dict") else {}
                    inline_data = part_dict.get("inline_data") if isinstance(part_dict, dict) else None
                    if inline_data and inline_data.get("mime_type") == "application/json":
                        data = inline_data.get("data")
                        if data:
                            try:
                                decoded = base64.b64decode(data).decode("utf-8")
                                json_candidates.append(decoded)
                                collect_text(decoded)
                            except (ValueError, UnicodeDecodeError) as decode_err:
                                logger.warning("JSON inline_data 解碼失敗: %s", decode_err)

        response_text = getattr(response, "text", "") or ""
        if not response_text and collected_texts:
            response_text = "\n".join(collected_texts)

        json_data: Optional[Dict[str, object]] = None
        if config.response_mode == "json":
            candidate_pool: List[str] = []
            if response_text:
                extracted = extract_json_object(response_text)
                if extracted:
                    candidate_pool.append(extracted)
            candidate_pool.extend(json_candidates)

            deduped: List[str] = []
            seen = set()
            for candidate in candidate_pool:
                key = candidate.strip()
                if key and key not in seen:
                    seen.add(key)
                    deduped.append(candidate)

            for candidate_text in deduped:
                try:
                    json_data = json.loads(candidate_text)
                    logger.info("成功解析 JSON 回應")
                    break
                except json.JSONDecodeError as exc:
                    logger.debug("忽略無法解析的 JSON 候選: %s", exc)

            if json_data is None:
                logger.warning("JSON 解析失敗，改以純文本處理")

        return response_text, json_data


__all__ = ["ConfigManager", "GeminiAI", "HAS_GOOGLE_AUTH"]
