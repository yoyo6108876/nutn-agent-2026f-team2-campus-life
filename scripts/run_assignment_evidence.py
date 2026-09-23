"""Record synthetic API examples; --live explicitly makes one paid provider call."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

from assignment_checker.api import create_app
from assignment_checker.provider import OpenAIProvider

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "assignment"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class RecordingProvider:
    def __init__(self, delegate=None, fixture=None):
        self.delegate = delegate
        self.fixture = fixture
        self.calls = 0
        self.raw_output = None

    def generate(self, request):
        self.calls += 1
        output = self.delegate.generate(request) if self.delegate is not None else self.fixture
        self.raw_output = output.model_dump() if hasattr(output, "model_dump") else output
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="對固定合成資料進行一次真實 LLM 呼叫")
    parser.add_argument("--case", choices=["normal", "invalid", "ungrounded", "known-failure"], default="normal")
    parser.add_argument("--output", type=Path, required=True, help="輸出證據 JSON；建議放在 git 忽略的 tmp/")
    args = parser.parse_args()
    if args.live and args.case in ("invalid", "ungrounded"):
        parser.error("非法輸入與假引用情境使用固定替身；--live 僅適用 normal 或 known-failure")
    source = f"{args.case}.request.json" if args.case in ("invalid", "known-failure") else "normal.request.json"
    request = load(source)
    delegate = OpenAIProvider() if args.live else None
    fixture = load("ungrounded.provider.json" if args.case == "ungrounded" else "normal.provider.json")
    if args.case == "known-failure" and not args.live:
        fixture["checks"][1].update({
            "status": "met", "student_evidence": [{"section_id": "S2", "quote": request["student_submission"]["sections"][1]["text"]}],
            "reason": "提到附錄，因此視為完成。（故意注入的錯誤判定）",
        })
    provider = RecordingProvider(delegate, fixture)
    with TestClient(create_app(provider)) as client:
        response = client.post("/assistant/check-submission", json=request)
    result = response.json()
    expected_status = {"normal": 200, "invalid": 422, "ungrounded": 502, "known-failure": 200}[args.case]
    labels = {check["requirement_id"]: check["status"] for check in result.get("checks", [])}
    expected_labels = {"R1": "met", "R2": "uncertain" if args.case == "known-failure" else "missing"}
    matched = response.status_code == expected_status
    if args.case in ("normal", "known-failure"):
        matched = matched and labels == expected_labels
    evidence = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "case": args.case,
        "data_source": "synthetic teaching fixture; no real student work",
        "provider_kind": "live_openai" if args.live else "fixture_test_double",
        "command": "python -m scripts.run_assignment_evidence " + " ".join(sys.argv[1:]),
        "transport": "FastAPI TestClient (in-process HTTP); live provider uses HTTPS when enabled",
        "request": request,
        "provider_attempts": provider.calls,
        "provider_output": provider.raw_output,
        "provider_metadata": delegate.metadata if delegate is not None else None,
        "http_status": response.status_code,
        "response": result,
        "expected_http_status": expected_status,
        "expected_labels": expected_labels if args.case in ("normal", "known-failure") else None,
        "matches_expected": matched,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.case}: HTTP {response.status_code}; provider={evidence['provider_kind']}; matches_expected={matched}")
    print(f"Evidence: {args.output}")
    # Deliberately injected known-failure mismatch is still returned as failure.
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
