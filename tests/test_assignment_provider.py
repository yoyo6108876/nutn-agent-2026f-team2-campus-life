import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
from openai import OpenAI
import pytest

from assignment_checker.models import CheckRequest, ModelReport
from assignment_checker.provider import DEFAULT_MODEL, OpenAIProvider
from assignment_checker.service import CheckFailure

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "assignment"


def request():
    return CheckRequest.model_validate_json((FIXTURES / "normal.request.json").read_text())


def test_responses_adapter_uses_one_call_and_does_not_store():
    report = ModelReport.model_validate_json((FIXTURES / "normal.provider.json").read_text())
    parse = Mock(return_value=SimpleNamespace(model=DEFAULT_MODEL, usage=None,
                                             status="completed", output_parsed=report))
    provider = OpenAIProvider(client=SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    assert provider.generate(request()) == report
    parse.assert_called_once()
    options = parse.call_args.kwargs
    assert options["store"] is False
    assert options["temperature"] == 0
    assert options["max_output_tokens"] == 3000
    assert "tools" not in options
    assert json.loads(options["input"][1]["content"])["submission_id"] == "SUB-DEMO-01"


@pytest.mark.parametrize("status,code,expected", [
    (401, "invalid_api_key", "PROVIDER_AUTH_FAILED"),
    (429, "insufficient_quota", "PROVIDER_QUOTA"),
    (429, "rate_limit_exceeded", "PROVIDER_RATE_LIMIT"),
    (403, "model_not_found", "PROVIDER_ERROR"),
])
def test_real_sdk_errors_are_sanitized_without_retry(status, code, expected):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={"error": {"message": "must-not-leak-secret",
                                                     "type": code, "code": code}})
    with OpenAI(api_key="test-only-not-a-real-key", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(CheckFailure) as error:
            OpenAIProvider(client=client).generate(request())
    assert error.value.code == expected
    assert "must-not-leak-secret" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("status,parsed,code", [
    ("incomplete", None, "INCOMPLETE_RESPONSE"),
    ("completed", None, "NO_STRUCTURED_RESPONSE"),
])
def test_refusal_and_incomplete_are_not_success(status, parsed, code):
    parse = Mock(return_value=SimpleNamespace(model=DEFAULT_MODEL, usage=None,
                                             status=status, output_parsed=parsed))
    with pytest.raises(CheckFailure) as error:
        OpenAIProvider(client=SimpleNamespace(responses=SimpleNamespace(parse=parse))).generate(request())
    assert error.value.code == code


def test_missing_key_is_handled_without_network(monkeypatch):
    from assignment_checker import provider
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(provider, "dotenv_values", lambda *args, **kwargs: {})
    with pytest.raises(CheckFailure) as error:
        provider.OpenAIProvider().generate(request())
    assert error.value.status_code == 503
    assert error.value.code == "MISSING_API_KEY"
