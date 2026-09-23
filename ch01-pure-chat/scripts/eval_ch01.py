import asyncio
import json
from pathlib import Path

from app.core.config import get_settings
from app.core.model import create_chat_model
from app.schemas.chat import ChatRequest
from app.services.chat import prepare_chat_messages, stream_chat
from app.services.extraction import extract_after_sales


CASES_PATH = Path("evals/ch01_cases.json")
RESULTS_PATH = Path("evals/ch01_results.json")


async def evaluate_case(case, model, settings):
    if case["kind"] == "chat":
        request = ChatRequest(messages=case["messages"])
        messages = prepare_chat_messages(request, settings.history_max_tokens)
        output = "".join([chunk async for chunk in stream_chat(messages, model)])
        passed = (
            any(text in output for text in case["must_contain_any"])
            and all(text not in output for text in case["must_not_contain"])
        )
        return {"id": case["id"], "passed": passed, "actual": output}

    result = await extract_after_sales(
        case["description"],
        model,
        settings.chat_structured_output_method,
    )
    actual = result.model_dump()
    return {
        "id": case["id"],
        "passed": actual == case["expected"],
        "actual": actual,
        "expected": case["expected"],
    }


async def main() -> int:
    settings = get_settings()
    model = create_chat_model(settings)
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        try:
            results.append(await evaluate_case(case, model, settings))
        except Exception as exc:
            results.append(
                {"id": case["id"], "passed": False, "error": type(exc).__name__}
            )

    RESULTS_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    passed = sum(result["passed"] for result in results)
    print(f"chapter-1 eval: {passed}/{len(results)} passed")
    for result in results:
        print(f"{'PASS' if result['passed'] else 'FAIL'} {result['id']}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
