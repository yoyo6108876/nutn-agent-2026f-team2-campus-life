import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from assignment_checker.api import create_app
from assignment_checker.service import CheckFailure

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "assignment"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeProvider:
    def __init__(self, output=None, error=None):
        self.output = output if output is not None else load("normal.provider.json")
        self.error = error
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return copy.deepcopy(self.output)


def invoke(request=None, provider=None):
    provider = provider if provider is not None else FakeProvider()
    with TestClient(create_app(provider)) as client:
        return client.post("/assistant/check-submission", json=request if request is not None else
                           load("normal.request.json")), provider


def test_normal_http_200_both_notices_share_missing_requirement():
    response, provider = invoke()
    assert response.status_code == 200
    assert response.json() == load("normal.expected.json")
    assert provider.calls == 1


def test_invalid_http_422_never_calls_provider():
    response, provider = invoke(load("invalid.request.json"))
    assert response.status_code == 422
    assert response.json()["error"]["stage"] == "request_validation"
    assert provider.calls == 0


def test_schema_valid_hallucinated_reference_http_502():
    response, provider = invoke(provider=FakeProvider(load("ungrounded.provider.json")))
    assert response.status_code == 502
    assert response.json()["error"]["stage"] == "grounding"
    assert "S99" in response.json()["error"]["message"]
    assert "student_notice" not in response.json()
    assert provider.calls == 1


@pytest.mark.parametrize("mutation", [
    "empty", "blank", "duplicate_section", "duplicate_requirement", "unknown_teacher",
    "bool_version", "extra_field", "long_text", "empty_requirements", "wrong_type",
])
def test_bad_requests_do_not_reach_provider(mutation):
    data = load("normal.request.json")
    if mutation == "empty":
        data["teacher_example"]["sections"] = []
    elif mutation == "blank":
        data["student_submission"]["sections"][0]["text"] = "  \n "
    elif mutation == "duplicate_section":
        data["student_submission"]["sections"] *= 2
    elif mutation == "duplicate_requirement":
        data["confirmed_requirements"] *= 2
    elif mutation == "unknown_teacher":
        data["confirmed_requirements"][0]["teacher_section_id"] = "T99"
    elif mutation == "bool_version":
        data["submission_version"] = True
    elif mutation == "extra_field":
        data["OPENAI_API_KEY"] = "example-secret-must-not-be-echoed"
    elif mutation == "long_text":
        data["student_submission"]["sections"][0]["text"] = "x" * 12001
    elif mutation == "empty_requirements":
        data["confirmed_requirements"] = []
    elif mutation == "wrong_type":
        data["submission_version"] = "1"
    response, provider = invoke(data)
    assert response.status_code == 422
    assert provider.calls == 0
    assert "example-secret" not in response.text


@pytest.mark.parametrize("mutation", ["submission", "version", "assignment", "quote",
                                      "teacher_quote", "teacher_section", "missing_check",
                                      "extra_check", "duplicate", "no_evidence"])
def test_grounding_rejects_bad_evidence_and_identity(mutation):
    data = load("normal.provider.json")
    if mutation in ("submission", "assignment"):
        data[f"{mutation}_id"] = "wrong"
    elif mutation == "version":
        data["submission_version"] = 2
    elif mutation == "quote":
        data["checks"][0]["student_evidence"][0]["quote"] = "not in source"
    elif mutation == "teacher_quote":
        data["checks"][0]["teacher_evidence"]["quote"] = "not in source"
    elif mutation == "teacher_section":
        data["checks"][0]["teacher_evidence"] = copy.deepcopy(data["checks"][1]["teacher_evidence"])
    elif mutation == "missing_check":
        data["checks"].pop()
    elif mutation == "extra_check":
        extra = copy.deepcopy(data["checks"][0]); extra["requirement_id"] = "R99"
        data["checks"].append(extra)
    elif mutation == "duplicate":
        data["checks"][1]["requirement_id"] = "R1"
    elif mutation == "no_evidence":
        data["checks"][0]["student_evidence"] = []
    response, _ = invoke(provider=FakeProvider(data))
    assert response.status_code == 502
    assert response.json()["error"]["stage"] == "grounding"


def test_schema_failure_is_separate_from_grounding():
    raw = load("normal.provider.json")
    raw["checks"][0]["status"] = "probably_done"
    response, _ = invoke(provider=FakeProvider(raw))
    assert response.status_code == 502
    assert response.json()["error"]["stage"] == "response_schema"


def test_uncertain_goes_to_confirmation_for_both_audiences():
    raw = load("normal.provider.json")
    raw["checks"].reverse()
    raw["checks"][0]["status"] = "uncertain"
    response, _ = invoke(provider=FakeProvider(raw))
    assert response.status_code == 200
    result = response.json()
    assert [item["requirement_id"] for item in result["checks"]] == ["R1", "R2"]
    assert result["student_notice"] == result["teacher_notice"] == {
        "needs_revision": [], "needs_confirmation": ["R2"],
    }


def test_known_failure_gate_cannot_establish_semantic_truth():
    # A deliberate synthetic false positive, not an observed live-model failure.
    request = load("known-failure.request.json")
    raw = load("normal.provider.json")
    raw["checks"][1].update({
        "status": "met",
        "student_evidence": [{"section_id": "S2", "quote": request["student_submission"]["sections"][1]["text"]}],
        "reason": "提到附錄，所以視為已完成。（故意注入的錯誤判定）",
    })
    response, _ = invoke(request, FakeProvider(raw))
    assert response.status_code == 200
    assert response.json()["checks"][1]["status"] == "met"
    # Manual desired label is uncertain; evidence existence alone cannot enforce it.
    assert response.json()["checks"][1]["status"] != "uncertain"


@pytest.mark.parametrize("status,code", [(502, "PROVIDER_AUTH_FAILED"), (503, "MISSING_API_KEY"),
                                        (504, "PROVIDER_TIMEOUT")])
def test_provider_failure_never_becomes_missing_assignment(status, code):
    response, _ = invoke(provider=FakeProvider(error=CheckFailure(code, "provider", "safe", status)))
    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "stage": "provider", "message": "safe"}}


def test_malformed_json_and_health_never_call_provider():
    provider = FakeProvider()
    with TestClient(create_app(provider)) as client:
        assert client.get("/health").json()["live_api_checked"] is False
        response = client.post("/assistant/check-submission", content="{broken", headers={"content-type": "application/json"})
        assert response.status_code == 422
    assert provider.calls == 0
