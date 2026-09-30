"""Run locally: python -m uvicorn assignment_checker.api:app --host 127.0.0.1."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .models import CheckRequest, CheckResponse, ModelReport
from .provider import OpenAIProvider
from .service import CheckFailure, ground_report
from .retrieval import QueryRequest, load_json, run_query


def create_app(provider=None, retrieval_provider=None):
    app = FastAPI(title="作業缺漏提醒助手", version="0.2.0",
                  description="Week 2 作業比對與 Week 3 檢索證據示範；本機教學版本。")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error):
        # No invalid field values or upstream exception bodies in the response.
        return JSONResponse(status_code=422, content={"error": {
            "code": "INVALID_REQUEST", "stage": "request_validation",
            "message": "輸入未符合規格，請檢查必填欄位、型別、段落及要求的引用。",
        }})

    @app.exception_handler(CheckFailure)
    async def check_failure(request: Request, error: CheckFailure):
        return JSONResponse(status_code=error.status_code, content=error.body())

    @app.get("/health")
    def health():
        return {"status": "ok", "provider": "openai", "live_api_checked": False}

    @app.post("/assistant/check-submission", response_model=CheckResponse)
    def check_submission(payload: CheckRequest):
        active_provider = provider if provider is not None else OpenAIProvider()
        raw = active_provider.generate(payload)
        try:
            report = ModelReport.model_validate(raw)
        except ValidationError:
            raise CheckFailure("INVALID_RESPONSE", "response_schema", "模型輸出不符合回覆結構。") from None
        return ground_report(payload, report)

    @app.get("/assistant/week3/queries")
    def week3_queries():
        return {"data_source": "synthetic_only", "teacher_original_case": "pricing_contract_known_but_source_text_missing",
                "queries": [{"query_id": key, "question": value["question"], "top_k": value["top_k"]}
                            for key, value in load_json("dataset.json")["queries"].items()]}

    @app.post("/assistant/week3/query")
    def week3_query(payload: QueryRequest):
        return run_query(payload, retrieval_provider)

    return app


app = create_app()
