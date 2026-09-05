import json
from datetime import UTC, datetime

from celery import Celery

from .config import settings
from .database import SessionLocal
from .extraction import extract_text
from .generator import DraftGenerationError, generate_draft
from .judge import JudgeUnavailable, judge_executor
from .models import (
    GenerationJob,
    PrivateJudgeBundle,
    ProblemDraft,
    ProblemVersion,
    SourceUpload,
    Submission,
)
from .schemas import ProblemDraftV1
from .services import validate_problem_draft
from .storage import private_storage

celery_app = Celery("aiacm", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)


def _generated_reference_error(draft) -> str | None:
    draft_cases = draft.public_cases + draft.hidden_cases

    def run_reference(reveal_actual: bool) -> tuple[list[dict], dict]:
        tests = [case.model_dump() for case in draft_cases]
        result = judge_executor.run(
            {
                "code": draft.reference_solution,
                "function_spec": draft.function_spec.model_dump(),
                "tests": tests,
                "checker": draft.checker.model_dump(),
                "resource_limits": draft.resource_limits.model_dump(),
                "reveal_actual": reveal_actual,
            }
        )
        return tests, result

    tests, result = run_reference(reveal_actual=True)
    if result.get("status") != "accepted":
        outcomes = result.get("cases") or []
        can_calibrate = len(outcomes) == len(tests) and all(
            "actual" in outcome and outcome.get("actual") is not None for outcome in outcomes
        )
        if can_calibrate:
            for case, outcome in zip(draft_cases, outcomes, strict=True):
                case.expected = outcome["actual"]
            try:
                ProblemDraftV1.model_validate(draft.model_dump(mode="json"))
            except Exception:
                can_calibrate = False
            if can_calibrate:
                tests, result = run_reference(reveal_actual=False)

    if result.get("status") == "accepted":
        base_payload = {
            "function_spec": draft.function_spec.model_dump(),
            "tests": tests,
            "checker": draft.checker.model_dump(),
            "resource_limits": draft.resource_limits.model_dump(),
            "reveal_actual": False,
        }
        uncaught = []
        for index, mutant in enumerate(draft.mutants, start=1):
            mutant_result = judge_executor.run({**base_payload, "code": mutant})
            if mutant_result.get("status") == "accepted":
                uncaught.append(index)
        if not uncaught:
            return None
        numbers = "、".join(str(index) for index in uncaught)
        return (
            f"错误实现 {numbers} 未被任何测试拦截；请让这些错误实现包含真实缺陷，并增加能触发缺陷的测试用例"
        )

    details = []
    for index, case in enumerate(result.get("cases") or []):
        if case.get("passed"):
            continue
        detail = f"{case.get('name', f'用例 {index + 1}')}: {case.get('message', '未通过')}"
        if "actual" in case and index < len(tests):
            actual = json.dumps(case.get("actual"), ensure_ascii=False)[:300]
            expected = json.dumps(tests[index].get("expected"), ensure_ascii=False)[:300]
            detail += f"，实际={actual}，期望={expected}"
        details.append(detail)
        if len(details) == 3:
            break
    summary = "；".join(details) or str(result.get("message") or result.get("status"))
    return (
        f"参考答案未通过隔离执行（{result.get('passed', 0)}/{result.get('total', len(tests))}）："
        f"{summary}"
    )[:1500]


@celery_app.task(name="generate_draft")
def generate_draft_task(job_id: str) -> None:
    db = SessionLocal()
    job = db.get(GenerationJob, job_id)
    try:
        if not job or not job.upload_id:
            return
        job.status = "running"
        upload = db.get(SourceUpload, job.upload_id)
        if not upload:
            raise ValueError("上传记录不存在")
        upload.status = "extracting"
        db.commit()
        content = private_storage.get(upload.object_key)
        text = extract_text(upload.original_name, content)
        upload.extracted_text = text
        upload.status = "generating"
        db.commit()
        validation_report = None
        try:
            payload = generate_draft(
                text,
                upload.original_name,
                reference_validator=_generated_reference_error,
            )
        except DraftGenerationError as exc:
            if exc.draft is None or not exc.validation_error:
                raise
            payload = exc.draft
            validation_report = {
                "passed": False,
                "checks": [
                    {
                        "name": "生成预检（待修订）",
                        "passed": False,
                        "message": (
                            "自动修复后仍未通过校验，已保留草稿供修改。"
                            f"{exc.validation_error}。修改后请重新运行质量门禁。"
                        ),
                    }
                ],
                "similar": [],
            }
        draft = ProblemDraft(
            owner_id=job.owner_id,
            source_upload_id=upload.id,
            payload=payload.model_dump(mode="json"),
            status="needs_revision" if validation_report else "draft",
            validation_report=validation_report,
        )
        db.add(draft)
        db.flush()
        upload.status = "ready"
        job.status = "completed"
        job.draft_id = draft.id
        job.result = {"draft_id": draft.id}
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"[:2000]
            if job.upload_id:
                upload = db.get(SourceUpload, job.upload_id)
                if upload:
                    upload.status = "failed"
            db.commit()
    finally:
        db.close()


@celery_app.task(name="validate_draft")
def validate_draft_task(job_id: str) -> None:
    db = SessionLocal()
    job = db.get(GenerationJob, job_id)
    try:
        if not job or not job.draft_id:
            return
        job.status = "running"
        draft = db.get(ProblemDraft, job.draft_id)
        if not draft:
            raise ValueError("草稿不存在")
        draft.status = "validating"
        db.commit()
        report = validate_problem_draft(db, draft.payload)
        draft.validation_report = report
        draft.status = "ready" if report["passed"] else "needs_revision"
        job.status = "completed"
        job.result = report
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"[:2000]
            db.commit()
    finally:
        db.close()


@celery_app.task(name="judge_submission")
def judge_submission_task(submission_id: str) -> None:
    db = SessionLocal()
    submission = db.get(Submission, submission_id)
    try:
        if not submission:
            return
        submission.status = "running"
        db.commit()
        version = db.get(ProblemVersion, submission.version_id)
        bundle = db.query(PrivateJudgeBundle).filter_by(version_id=submission.version_id).one()
        if not version:
            raise ValueError("题目版本不存在")
        tests = list(version.public_cases)
        reveal = submission.kind == "run"
        if submission.kind == "submit":
            tests += list(bundle.hidden_cases)
        result = judge_executor.run(
            {
                "code": submission.code,
                "function_spec": version.function_spec,
                "tests": tests,
                "checker": version.checker,
                "resource_limits": version.resource_limits,
                "reveal_actual": reveal,
            }
        )
        if submission.kind == "submit":
            for index, case in enumerate(result.get("cases", []), start=1):
                case["name"] = f"测试 {index}"
                case.pop("actual", None)
        status = result.get("status", "internal_error")
        if status in {"policy_error"}:
            status = "runtime_error"
        submission.status = status
        submission.passed_cases = int(result.get("passed", 0))
        submission.total_cases = int(result.get("total", len(tests)))
        submission.runtime_ms = result.get("runtime_ms")
        submission.result = result
        submission.finished_at = datetime.now(UTC)
        db.commit()
    except JudgeUnavailable as exc:
        submission.status = "internal_error"
        submission.result = {"message": str(exc)}
        submission.finished_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        submission = db.get(Submission, submission_id)
        if submission:
            submission.status = "internal_error"
            submission.result = {"message": f"{type(exc).__name__}: {exc}"[:1000]}
            submission.finished_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()


def dispatch(task, *args) -> None:
    if settings.sync_tasks:
        task(*args)
    else:
        task.delay(*args)
