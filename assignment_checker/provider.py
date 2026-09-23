"""OpenAI Responses adapter. Credentials stay local and errors are sanitized."""

import os
from pathlib import Path
from time import perf_counter

from dotenv import dotenv_values
from openai import (
    APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError,
    OpenAI, RateLimitError,
)
from pydantic import ValidationError

from .models import CheckRequest, ModelReport
from .service import CheckFailure

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gpt-4.1-mini-2025-04-14"
PROMPT_VERSION = "assignment-check-v1.1"
PROMPT = Path(__file__).with_name("prompt.txt").read_text(encoding="utf-8")


def local_settings():
    # Never overwrite the file or log its contents. Shell values take precedence.
    values = dotenv_values(ROOT / ".env", interpolate=False)
    key = os.environ.get("OPENAI_API_KEY") or values.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL") or values.get("OPENAI_MODEL") or DEFAULT_MODEL
    if not key or not key.strip():
        raise CheckFailure("MISSING_API_KEY", "configuration",
                           "請在專案 .env 設定 OPENAI_API_KEY。", 503)
    return key.strip(), model


class OpenAIProvider:
    def __init__(self, client=None, model=None):
        self.client = client
        self.model = model
        self.metadata = {}

    def generate(self, request: CheckRequest) -> ModelReport:
        if self.client is None:
            key, default_model = local_settings()
            # One request, no hidden retries and no environment base-URL override.
            with OpenAI(api_key=key, base_url="https://api.openai.com/v1",
                        max_retries=0, timeout=45) as client:
                return self._generate(client, self.model or default_model, request)
        return self._generate(self.client, self.model or DEFAULT_MODEL, request)

    def _generate(self, client, model, request):
        start = perf_counter()
        try:
            response = client.responses.parse(
                model=model,
                input=[{"role": "system", "content": PROMPT},
                       {"role": "user", "content": request.model_dump_json()}],
                text_format=ModelReport,
                temperature=0,
                max_output_tokens=3000,
                store=False,
            )
        except AuthenticationError:
            raise CheckFailure("PROVIDER_AUTH_FAILED", "provider", "API 金鑰驗證失敗，請確認金鑰。") from None
        except RateLimitError as error:
            quota = error.code == "insufficient_quota"
            raise CheckFailure("PROVIDER_QUOTA" if quota else "PROVIDER_RATE_LIMIT", "provider",
                               "API 可用額度不足，請檢查專案帳務。" if quota else
                               "API 達到速率限制，請稍後再試。") from None
        except APITimeoutError:
            raise CheckFailure("PROVIDER_TIMEOUT", "provider", "API 超過 45 秒未完成回應。", 504) from None
        except APIConnectionError:
            raise CheckFailure("PROVIDER_UNREACHABLE", "provider", "無法連線至 API。") from None
        except APIStatusError:
            raise CheckFailure("PROVIDER_ERROR", "provider", "API 拒絕請求，請檢查模型權限與設定。") from None
        except (ValidationError, ValueError):
            raise CheckFailure("INVALID_RESPONSE", "response_schema", "模型輸出不符合回覆結構。") from None
        self.metadata = {
            "model": response.model,
            "prompt_version": PROMPT_VERSION,
            "latency_seconds": round(perf_counter() - start, 3),
            "usage": response.usage.model_dump() if response.usage else None,
        }
        if response.status != "completed":
            raise CheckFailure("INCOMPLETE_RESPONSE", "provider", "模型輸出未完成，未產生檢查報告。")
        if response.output_parsed is None:
            raise CheckFailure("NO_STRUCTURED_RESPONSE", "provider", "模型拒絕或未提供可用的結構化回覆。")
        return response.output_parsed
