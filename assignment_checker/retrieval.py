"""Small, inspectable lexical retriever and citation gate for Week 3 fixtures.

Fact/role tags are curated index metadata, never inferred from model output.
Gold labels live outside this module and are used only by the offline evaluator.
"""

from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from .models import Identifier, StrictModel, Text
from .provider import OpenAIProvider
from .service import CheckFailure

DATA = Path(__file__).resolve().parents[1] / "examples" / "week3"


def load_json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


class QueryRequest(StrictModel):
    query_id: Literal["Q1", "Q2", "Q3", "B1"]
    mode: Literal["fixture", "live"] = "fixture"
    top_k: Annotated[int, Field(ge=1, le=10)] | None = None


class Citation(StrictModel):
    chunk_id: Identifier
    quote: Text


class FactAnswer(StrictModel):
    fact_id: Identifier
    value: Text
    evidence: Annotated[list[Citation], Field(min_length=1, max_length=10)]


class GeneratedAnswer(StrictModel):
    facts: Annotated[list[FactAnswer], Field(min_length=1, max_length=10)]


class FrozenInput(StrictModel):
    question: str
    facts: list[dict]
    selected_evidence: list[dict]
    evidence_hash: str


class RetrievalProvider(OpenAIProvider):
    response_type = GeneratedAnswer
    prompt_version = "retrieval-generator-v1"
    prompt = Path(__file__).with_name("retrieval_prompt.txt").read_text(encoding="utf-8")


def tokens(text):
    lowered = text.lower()
    result = set(re.findall(r"[a-z0-9]+", lowered))
    for run in re.findall(r"[\u4e00-\u9fff]+", lowered):
        result.update(run[i:i + 2] for i in range(len(run) - 1))
        if len(run) == 1:
            result.add(run)
    return result


def prepare(query_id, top_k=None, dataset=None, today=None):
    dataset = dataset if dataset is not None else load_json("dataset.json")
    query = dataset["queries"][query_id]
    today = today or date.today()
    top_k = top_k if top_k is not None else query["top_k"]
    words = tokens(query["question"])
    sources = {source["id"]: source for source in dataset["sources"]}
    candidates, excluded = [], []
    for chunk in dataset["chunks"]:
        if chunk["corpus"] != query["corpus"]:
            continue
        source = sources[chunk["source_id"]]
        reason = None
        if source["withdrawn"]:
            reason = "withdrawn"
        elif not source["permission"]:
            reason = "permission_denied"
        elif source["pii"] != "synthetic_no_pii":
            reason = "pii_not_approved"
        elif not date.fromisoformat(source["updated_at"]) <= today <= date.fromisoformat(source["valid_until"]):
            reason = "outside_validity_window"
        if reason:
            excluded.append({"chunk_id": chunk["id"], "reason": reason})
            continue
        overlap = sorted(words & tokens(chunk["text"]))
        score = len(overlap) / len(words) if words else 0.0
        # Stable ties, and a positive score threshold; metadata is not a search term.
        if score > 0:
            candidates.append({**chunk, "score": score, "matched_terms": overlap,
                               "source_version": source["version"]})
    candidates.sort(key=lambda chunk: (-chunk["score"], chunk["id"]))
    selected = candidates[:top_k]
    selected_ids = {chunk["id"] for chunk in selected}
    missing = []
    for fact in query["facts"]:
        for role in fact["required_roles"]:
            if not any(fact["id"] in chunk["fact_ids"] and chunk["role"] == role for chunk in selected):
                missing.append({"fact_id": fact["id"], "role": role})
    status = "no_answer" if not selected else "coverage_failure" if missing else "ready"
    evidence = [{key: chunk[key] for key in ("id", "source_id", "source_version", "role", "fact_ids", "text")}
                for chunk in selected]
    bundle = FrozenInput(question=query["question"], facts=query["facts"],
                         selected_evidence=evidence, evidence_hash=digest(evidence))
    trace = {
        "query_id": query_id, "question": query["question"], "corpus": query["corpus"],
        "dataset_version": dataset["version"], "dataset_hash": digest(dataset),
        "policy_date": today.isoformat(), "retriever_version": "unicode-bigram-overlap-v1",
        "top_k": top_k, "min_score_exclusive": 0, "gate": status,
        "missing_coverage": missing, "excluded": excluded,
        "required_facts": query["facts"],
        "ranked_candidates": [{"rank": i + 1, "chunk_id": chunk["id"],
                               "source_id": chunk["source_id"], "score": round(chunk["score"], 6),
                               "matched_terms": chunk["matched_terms"], "selected": chunk["id"] in selected_ids}
                              for i, chunk in enumerate(candidates)],
        "selected_evidence": evidence, "evidence_hash": bundle.evidence_hash,
    }
    return bundle, trace


def validate_answer(bundle, raw):
    """Validate provenance and coverage. This does NOT prove semantic entailment."""
    try:
        answer = GeneratedAnswer.model_validate(raw)
    except ValidationError:
        raise CheckFailure("INVALID_RESPONSE", "response_schema", "模型回覆格式不符。") from None
    facts = {fact["id"]: fact for fact in bundle.facts}
    ids = [fact.fact_id for fact in answer.facts]
    errors = []
    if len(ids) != len(set(ids)) or set(ids) != set(facts):
        errors.append("fact_set_mismatch")
    chunks = {chunk["id"]: chunk for chunk in bundle.selected_evidence}
    if digest(bundle.selected_evidence) != bundle.evidence_hash:
        errors.append("evidence_changed")
    for fact in answer.facts:
        spec = facts.get(fact.fact_id)
        if spec is None:
            continue
        if fact.value not in spec["allowed_values"]:
            errors.append("value_out_of_contract")
        cited_roles = set()
        cited_ids = []
        for citation in fact.evidence:
            chunk = chunks.get(citation.chunk_id)
            cited_ids.append(citation.chunk_id)
            if chunk is None:
                errors.append("citation_not_selected")
                continue
            if citation.quote not in chunk["text"]:
                errors.append("quote_not_in_source")
            if fact.fact_id not in chunk["fact_ids"]:
                errors.append("citation_wrong_fact")
            else:
                cited_roles.add(chunk["role"])
        if len(cited_ids) != len(set(cited_ids)):
            errors.append("duplicate_citation")
        if not set(spec["required_roles"]) <= cited_roles:
            errors.append("citation_role_coverage_failure")
    if errors:
        raise CheckFailure("UNGROUNDED_RESPONSE", "grounding", ", ".join(sorted(set(errors))))
    ordered = {fact.fact_id: fact for fact in answer.facts}
    return GeneratedAnswer(facts=[ordered[spec["id"]] for spec in bundle.facts])


def render(bundle, answer):
    """Only the system attaches source versions and verbatim citations."""
    chunks = {chunk["id"]: chunk for chunk in bundle.selected_evidence}
    labels = {spec["id"]: spec["label"] for spec in bundle.facts}
    return [{"fact_id": fact.fact_id, "label": labels[fact.fact_id], "value": fact.value,
             "citations": [{"chunk_id": citation.chunk_id,
                            "source_id": chunks[citation.chunk_id]["source_id"],
                            "source_version": chunks[citation.chunk_id]["source_version"],
                            "quote": citation.quote} for citation in fact.evidence]}
            for fact in answer.facts]


def literal_baseline(bundle):
    """Exact wording baseline: require every authored keyword, else uncertain."""
    facts = []
    for spec in bundle.facts:
        relevant = [chunk for chunk in bundle.selected_evidence if spec["id"] in chunk["fact_ids"]]
        searchable = "\n".join(chunk["text"] for chunk in relevant if chunk["role"] != "teacher")
        value = "uncertain"
        for rule in spec["literal_rules"]:
            if all(term in searchable for term in rule["terms"]):
                value = rule["value"]
                break
        facts.append({"fact_id": spec["id"], "value": value,
                      "evidence": [{"chunk_id": chunk["id"], "quote": chunk["text"]} for chunk in relevant]})
    return GeneratedAnswer.model_validate({"facts": facts})


def generator_input(bundle):
    # Both generators see the same evidence. LLM gets no baseline rules or oracle.
    return bundle.model_copy(update={"facts": [
        {key: value for key, value in fact.items() if key != "literal_rules"} for fact in bundle.facts
    ]}, deep=True)


def run_query(request, provider=None):
    bundle, trace = prepare(request.query_id, request.top_k)
    result = {"mode": request.mode, "status": trace["gate"], "trace": trace,
              "provider_attempts": 0, "provider_metadata": None,
              "answer": [], "student_notice": None, "teacher_notice": None}
    if trace["gate"] != "ready":
        result["message"] = "找不到可用證據。" if trace["gate"] == "no_answer" else "檢索證據不完整，不能判定作業缺漏。"
        return result
    if request.mode == "fixture":
        # Q3 is the same question as Q1 with a smaller default retrieval budget.
        fixture_id = "Q1" if request.query_id == "Q3" else request.query_id
        raw = load_json("generator-fixtures.json")[fixture_id]
        result["provider_kind"] = "authored_fixture_not_model_output"
    else:
        active = provider if provider is not None else RetrievalProvider()
        result["provider_attempts"] = 1
        raw = active.generate(generator_input(bundle))
        result["provider_metadata"] = active.metadata
        result["provider_kind"] = "live_openai"
    answer = validate_answer(bundle, raw)
    result.update(status="answered", answer=render(bundle, answer),
                  generator_output=answer.model_dump(), citation_gate="passed",
                  semantic_verification="not_proven_by_citation_gate")
    if trace["corpus"] == "assignment-demo":
        notice = {"needs_revision": [fact.fact_id for fact in answer.facts if fact.value in ("missing", "partial")],
                  "needs_confirmation": [fact.fact_id for fact in answer.facts if fact.value == "uncertain"]}
        result["student_notice"] = notice
        result["teacher_notice"] = dict(notice)
    return result
