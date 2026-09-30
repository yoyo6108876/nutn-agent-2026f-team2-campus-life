"""Reproduce Week 3; default fixtures, --live Q1 B1 makes up to two paid calls."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from assignment_checker.retrieval import (
    FrozenInput, QueryRequest, digest, literal_baseline, load_json, prepare,
    render, run_query, validate_answer,
)
from assignment_checker.service import CheckFailure


def evaluate(bundle, raw, gold):
    """Offline authored oracle, NOT the production semantic gate or an LLM judge."""
    try:
        answer = validate_answer(bundle, raw)
        structural_gate = "passed"
        structural_error = None
    except CheckFailure as error:
        answer = None
        structural_gate = "rejected"
        structural_error = error.body()
    facts = raw["facts"] if isinstance(raw, dict) else raw.model_dump()["facts"]
    by_id = {}
    for fact in facts:
        by_id.setdefault(fact["fact_id"], []).append(fact)
    correct, unsupported, abstentions = 0, 0, 0
    details = []
    selected = {chunk["id"]: chunk for chunk in bundle.selected_evidence}
    for fid, expected in gold.items():
        actual = by_id.get(fid, [])
        matched = False
        if len(actual) == 1:
            item = actual[0]
            refs = {ref["chunk_id"] for ref in item["evidence"]}
            valid_refs = bool(refs) and all(
                ref["chunk_id"] in selected and bool(ref["quote"].strip()) and
                ref["quote"] in selected[ref["chunk_id"]]["text"] and
                fid in selected[ref["chunk_id"]]["fact_ids"] for ref in item["evidence"])
            matched = (item["value"] == expected["value"] and valid_refs and
                       set(expected["required_chunk_ids"]) <= refs)
        correct += int(matched)
        for item in actual:
            if item["value"] == "uncertain" and expected["value"] != "uncertain":
                abstentions += 1
            elif not matched:
                unsupported += 1
        details.append({"fact_id": fid, "expected_value": expected["value"],
                        "actual_values": [item["value"] for item in actual], "supported_correct": matched})
    unsupported += sum(len(items) for fid, items in by_id.items() if fid not in gold)
    return {"evaluator": "authored-oracle-v1; closed synthetic benchmark only",
            "citation_gate": structural_gate, "citation_error": structural_error,
            "fact_coverage": f"{correct}/{len(gold)}", "correct_supported_facts": correct,
            "required_facts": len(gold), "unsupported_claims": unsupported,
            "unnecessary_abstentions": abstentions, "details": details,
            "benchmark_pass": answer is not None and correct == len(gold) and unsupported == 0}


def bundle_from_trace(trace):
    return FrozenInput(question=trace["question"], facts=trace["required_facts"],
                       selected_evidence=trace["selected_evidence"], evidence_hash=trace["evidence_hash"])


def failures():
    bundle, _ = prepare("B1")
    original = load_json("generator-fixtures.json")["B1"]
    cases = {}
    fake = deepcopy(original)
    fake["facts"][0]["evidence"][0]["chunk_id"] = "B-old"
    cases["unselected_withdrawn_citation"] = fake
    omitted = deepcopy(original)
    omitted["facts"].pop()
    cases["omitted_fact"] = omitted
    wrong = deepcopy(original)
    wrong["facts"][0]["value"] = "00:00–24:00"
    cases["valid_quote_wrong_conclusion"] = wrong
    gold = load_json("oracle.json")["B1"]["facts"]
    return {"provenance": "deliberately injected fixtures, not observed live LLM failures",
            "evidence_hash": bundle.evidence_hash,
            "observations": [{"case": name, "injected_output": output,
                              "evaluation": evaluate(bundle, output, gold)} for name, output in cases.items()]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", nargs="*", choices=["Q1", "B1"], default=[])
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/week3-evidence"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    oracle = load_json("oracle.json")
    records, all_pass = [], True
    for qid in ("Q1", "Q2", "Q3", "B1"):
        request = QueryRequest(query_id=qid, mode="live" if qid in args.live else "fixture")
        record = {"query_id": qid, "request": request.model_dump(), "generators": []}
        try:
            response = run_query(request)
        except CheckFailure as error:
            record.update(error=error.body(), benchmark_pass=False)
            records.append(record)
            all_pass = False
            print(f"{qid}: {error.code}")
            continue
        record["response"] = response
        (args.output_dir / f"{qid}-top-k-trace.json").write_text(
            json.dumps(response["trace"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        matched = response["status"] == oracle[qid]["expected_status"]
        if response["status"] == "answered":
            bundle = bundle_from_trace(response["trace"])
            for kind, output in (("literal_rule_baseline", literal_baseline(bundle).model_dump()),
                                 (response["provider_kind"], response["generator_output"])):
                score = evaluate(bundle, output, oracle[qid]["facts"])
                record["generators"].append({"kind": kind, "evidence_hash": bundle.evidence_hash,
                                              "raw_output": output, "evaluation": score})
            # Baseline failures are measurements, not a failure of the test harness.
            matched = matched and record["generators"][1]["evaluation"]["benchmark_pass"]
        else:
            matched = matched and response["provider_attempts"] == 0 and not response["answer"]
        record["benchmark_pass"] = matched
        all_pass = all_pass and matched
        records.append(record)
        print(f"{qid}: {response['status']}; mode={request.mode}; expected={matched}")
    failure_records = failures()
    expected_gates = ["rejected", "rejected", "passed"]
    observed_gates = [item["evaluation"]["citation_gate"] for item in failure_records["observations"]]
    failure_records["matches_expected_limitations"] = (observed_gates == expected_gates and
        failure_records["observations"][2]["evaluation"]["unsupported_claims"] == 1)
    all_pass = all_pass and failure_records["matches_expected_limitations"]
    comparison = {"schema_version": "week3-comparison-v1", "captured_at": datetime.now(timezone.utc).isoformat(),
                  "command": "python -m scripts.run_week3_evidence " + " ".join(sys.argv[1:]),
                  "data_source": "synthetic authored fixture; no real student records",
                  "teacher_original_case": "not_supplied; B1 is a clearly labeled synthetic substitute",
                  "oracle_hash": digest(oracle), "all_expected_checks_passed": all_pass, "cases": records}
    for name, value in (("generator-comparison.json", comparison), ("failure-observations.json", failure_records)):
        (args.output_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
