"""Run the chapter-two labeled cases against the configured model and database."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.core.config import get_settings
from app.db.base import create_database_engine, create_session_factory
from app.db.models import Message
from app.db.repository import Repository
from app.main import _build_chat_orchestrator
from app.services.chat import DoneEvent, TokenEvent, ToolEvent


CHAPTER_DIR = Path(__file__).resolve().parents[1]
CASES_PATH = CHAPTER_DIR / "evals" / "ch02_cases.json"
RESULTS_PATH = CHAPTER_DIR / "evals" / "ch02_results.json"


def answer_grounds_tool(case: dict, answer: str, payloads: list[dict]) -> bool:
    if case["expected_tool"] is None:
        return True
    if len(payloads) != 1 or payloads[0].get("tool") != case["expected_tool"]:
        return False
    data = payloads[0].get("data")
    if not isinstance(data, dict):
        return not case.get("grounded_fields") and not case.get("grounded_terms")
    for field in case.get("grounded_fields", []):
        value = data.get(field)
        if value is None or str(value) not in answer:
            return False
    for term in case.get("grounded_terms", []):
        if term not in str(data.get("answer", "")) or term not in answer:
            return False
    return True


async def evaluate_case(case, orchestrator, session_factory, run_id):
    tools = []
    tokens = []
    done_id = None
    error_type = None
    try:
        async for event in orchestrator.stream_turn(
            user_id=f"eval-{run_id}-{case['id']}",
            message=case["message"],
            conversation_id=None,
        ):
            if isinstance(event, ToolEvent):
                tools.append(event.name)
            elif isinstance(event, TokenEvent):
                tokens.append(event.content)
            elif isinstance(event, DoneEvent):
                done_id = event.conversation_id
                if tuple(tools) != event.tools:
                    error_type = "EventMismatch"
    except Exception as exc:
        error_type = type(exc).__name__

    tool_payloads = []
    if done_id is not None:
        async with session_factory() as session:
            statement = (
                select(Message.content)
                .where(Message.conversation_id == done_id, Message.role == "tool")
                .order_by(Message.id)
            )
            for content in (await session.scalars(statement)).all():
                try:
                    tool_payloads.append(json.loads(content or ""))
                except (ValueError, TypeError):
                    tool_payloads.append({})

    expected_tool = case["expected_tool"]
    expected_tools = [] if expected_tool is None else [expected_tool]
    actual_ok = tool_payloads[0].get("ok") if len(tool_payloads) == 1 else None
    actual_found = (
        tool_payloads[0].get("data", {}).get("found")
        if len(tool_payloads) == 1 and isinstance(tool_payloads[0].get("data"), dict)
        else None
    )
    answer = "".join(tokens)
    # Terms are alternative signs that the answer addressed the labeled intent.
    answer_term_ok = any(term in answer for term in case["answer_terms"])
    grounded_ok = answer_grounds_tool(case, answer, tool_payloads)
    passed = (
        error_type is None
        and done_id is not None
        and tools == expected_tools
        and len(tool_payloads) == len(expected_tools)
        and bool(answer)
        and answer_term_ok
        and grounded_ok
        and (
            "expected_tool_ok" not in case
            or actual_ok is case["expected_tool_ok"]
        )
        and (
            "expected_faq_found" not in case
            or actual_found is case["expected_faq_found"]
        )
    )
    return {
        "id": case["id"],
        "passed": passed,
        "expected_tool": expected_tool,
        "actual_tools": tools,
        "tool_payloads": tool_payloads,
        "expected_tool_ok": case.get("expected_tool_ok"),
        "actual_tool_ok": actual_ok,
        "expected_faq_found": case.get("expected_faq_found"),
        "actual_faq_found": actual_found,
        "answer_term_ok": answer_term_ok,
        "grounded_ok": grounded_ok,
        "token_count": len(tokens),
        "answer_length": len(answer),
        "answer": answer,
        "conversation_id": done_id,
        "error_type": error_type,
    }


async def main():
    settings = get_settings()
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    engine = create_database_engine(settings)
    repository = None
    try:
        session_factory = create_session_factory(engine)
        repository = Repository(session_factory)
        orchestrator = _build_chat_orchestrator(settings, repository)
        run_id = uuid4().hex[:12]
        results = []
        for case in cases:
            try:
                result = await evaluate_case(
                    case, orchestrator, session_factory, run_id
                )
            except Exception as exc:
                result = {
                    "id": case["id"],
                    "passed": False,
                    "error_type": type(exc).__name__,
                }
            results.append(result)
            print(
                f"{'PASS' if result['passed'] else 'FAIL'} {case['id']} "
                f"tools={result.get('actual_tools', [])} "
                f"ok={result.get('actual_tool_ok')} "
                f"found={result.get('actual_faq_found')} "
                f"answer_term={result.get('answer_term_ok')} "
                f"grounded={result.get('grounded_ok')} "
                f"error={result.get('error_type')}"
            )

        summary = {
            "run_id": run_id,
            "passed": sum(result["passed"] for result in results),
            "total": len(results),
            "results": results,
        }
        RESULTS_PATH.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"chapter-2 eval: {summary['passed']}/{summary['total']} passed")
        return 0 if summary["passed"] == summary["total"] else 1
    finally:
        try:
            if repository is not None:
                await repository.close()
        finally:
            await engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"chapter-2 eval setup failed: {type(exc).__name__}")
        raise SystemExit(2) from None
