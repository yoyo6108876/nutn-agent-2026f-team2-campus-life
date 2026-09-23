"""Separate output shape validation from evidence and identity checks."""

from .models import CheckRequest, CheckResponse, ModelReport, Notice


class CheckFailure(Exception):
    def __init__(self, code, stage, message, status_code=502):
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.message = message
        self.status_code = status_code

    def body(self):
        return {"error": {"code": self.code, "stage": self.stage, "message": self.message}}


def require(condition, message):
    if not condition:
        raise CheckFailure("UNGROUNDED_RESPONSE", "grounding", message)


def ground_report(request: CheckRequest, report: ModelReport) -> CheckResponse:
    for field in ("assignment_id", "submission_id", "submission_version"):
        require(getattr(report, field) == getattr(request, field), f"Submission {field} does not match")
    expected = {item.id: item for item in request.confirmed_requirements}
    actual = [item.requirement_id for item in report.checks]
    require(len(actual) == len(set(actual)), "Duplicate requirement in response")
    require(set(actual) == set(expected), "Response must cover exactly the confirmed requirements")
    teacher = {item.id: item.text for item in request.teacher_example.sections}
    student = {item.id: item.text for item in request.student_submission.sections}
    for check in report.checks:
        evidence = check.teacher_evidence
        requirement = expected[check.requirement_id]
        require(evidence.section_id == requirement.teacher_section_id,
                "Teacher evidence must point to the requirement's teacher section")
        require(evidence.quote in teacher[evidence.section_id], "Teacher quote is not present in its source")
        if check.status in ("met", "partial"):
            require(bool(check.student_evidence), "Met or partial checks require student evidence")
        for evidence in check.student_evidence:
            require(evidence.section_id in student,
                    f"Student evidence section {evidence.section_id} does not exist")
            require(evidence.quote in student[evidence.section_id], "Student quote is not present in its source")
    # Canonical order follows the teacher's requirements, regardless of model order.
    by_id = {item.requirement_id: item for item in report.checks}
    ordered = [by_id[item.id] for item in request.confirmed_requirements]
    notice = Notice(
        needs_revision=[item.requirement_id for item in ordered if item.status in ("partial", "missing")],
        needs_confirmation=[item.requirement_id for item in ordered if item.status == "uncertain"],
    )
    return CheckResponse(
        assignment_id=request.assignment_id,
        submission_id=request.submission_id,
        submission_version=request.submission_version,
        checks=ordered,
        student_notice=notice,
        teacher_notice=notice.model_copy(deep=True),
    )
