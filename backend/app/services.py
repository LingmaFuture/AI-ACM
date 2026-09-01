import re
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from .judge import JudgeUnavailable, judge_executor
from .models import PrivateJudgeBundle, Problem, ProblemVersion, User
from .schemas import ProblemDraftV1


def unique_slug(db: Session, hint: str) -> str:
    base = re.sub(r"[^a-z0-9-]+", "-", hint.lower()).strip("-") or "ai-problem"
    base = re.sub(r"-+", "-", base)[:110]
    candidate = base
    suffix = 2
    while db.scalar(select(Problem.id).where(Problem.slug == candidate)):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def create_problem(db: Session, author_id: str, draft: ProblemDraftV1) -> Problem:
    problem = Problem(
        slug=unique_slug(db, draft.slug_hint),
        author_id=author_id,
        status="published",
        language="zh-CN",
    )
    db.add(problem)
    db.flush()
    create_problem_version(db, problem, draft)
    return problem


def create_problem_version(
    db: Session, problem: Problem, draft: ProblemDraftV1
) -> ProblemVersion:
    latest = db.scalar(
        select(ProblemVersion.version_number)
        .where(ProblemVersion.problem_id == problem.id)
        .order_by(ProblemVersion.version_number.desc())
        .limit(1)
    )
    version = ProblemVersion(
        problem_id=problem.id,
        version_number=(latest or 0) + 1,
        title=draft.title,
        description=draft.description,
        difficulty=draft.difficulty,
        tags=draft.tags,
        function_spec=draft.function_spec.model_dump(),
        starter_code=draft.starter_code,
        public_cases=[case.model_dump() for case in draft.public_cases],
        constraints=draft.constraints,
        checker=draft.checker.model_dump(),
        resource_limits=draft.resource_limits.model_dump(),
    )
    db.add(version)
    db.flush()
    db.add(
        PrivateJudgeBundle(
            version_id=version.id,
            reference_solution=draft.reference_solution,
            hidden_cases=[case.model_dump() for case in draft.hidden_cases],
            mutants=draft.mutants,
        )
    )
    problem.current_version_id = version.id
    db.flush()
    return version


def find_similar_titles(db: Session, title: str) -> list[dict]:
    rows = db.execute(
        select(Problem, ProblemVersion)
        .join(ProblemVersion, Problem.current_version_id == ProblemVersion.id)
        .where(Problem.status == "published")
    ).all()
    matches = []
    for problem, version in rows:
        score = SequenceMatcher(None, title.lower(), version.title.lower()).ratio()
        if score >= 0.68:
            matches.append({"slug": problem.slug, "title": version.title, "score": round(score, 2)})
    return sorted(matches, key=lambda item: item["score"], reverse=True)[:5]


def validate_problem_draft(db: Session, raw_payload: dict) -> dict:
    report: dict = {"passed": False, "checks": [], "similar": []}
    try:
        draft = ProblemDraftV1.model_validate(raw_payload)
        report["checks"].append({"name": "结构化字段", "passed": True, "message": "Schema 合法"})
    except Exception as exc:
        report["checks"].append(
            {"name": "结构化字段", "passed": False, "message": str(exc)[:1000]}
        )
        return report

    all_cases = [case.model_dump() for case in draft.public_cases + draft.hidden_cases]
    base_payload = {
        "function_spec": draft.function_spec.model_dump(),
        "tests": all_cases,
        "checker": draft.checker.model_dump(),
        "resource_limits": draft.resource_limits.model_dump(),
        "reveal_actual": False,
    }
    try:
        reference_result = judge_executor.run({**base_payload, "code": draft.reference_solution})
        reference_passed = reference_result.get("status") == "accepted"
        report["checks"].append(
            {
                "name": "参考答案",
                "passed": reference_passed,
                "message": (
                    "通过全部测试"
                    if reference_passed
                    else reference_result.get("message", reference_result.get("status", "失败"))
                ),
            }
        )

        blank_code = (
            f"class {draft.function_spec.class_name}:\n"
            f"    def {draft.function_spec.method_name}(self, "
            + ", ".join(arg.name for arg in draft.function_spec.args)
            + "):\n        return None\n"
        )
        blank_result = judge_executor.run({**base_payload, "code": blank_code})
        blank_rejected = blank_result.get("status") != "accepted"
        report["checks"].append(
            {
                "name": "空实现拦截",
                "passed": blank_rejected,
                "message": "空实现已被拒绝" if blank_rejected else "测试错误地接受了空实现",
            }
        )

        rejected = 0
        mutant_details = []
        for index, mutant in enumerate(draft.mutants):
            result = judge_executor.run({**base_payload, "code": mutant})
            caught = result.get("status") != "accepted"
            rejected += int(caught)
            mutant_details.append(f"错误实现 {index + 1}{'已拦截' if caught else '未拦截'}")
        mutants_passed = rejected == len(draft.mutants) and len(draft.mutants) >= 2
        report["checks"].append(
            {
                "name": "典型错误实现",
                "passed": mutants_passed,
                "message": "；".join(mutant_details),
            }
        )
    except JudgeUnavailable as exc:
        report["checks"].append(
            {"name": "隔离判题环境", "passed": False, "message": str(exc)[:1000]}
        )

    report["similar"] = find_similar_titles(db, draft.title)
    report["passed"] = all(item["passed"] for item in report["checks"])
    return report


def public_problem_dict(
    db: Session,
    problem: Problem,
    version: ProblemVersion,
    viewer_id: str | None = None,
    include_description: bool = False,
) -> dict:
    from .models import Submission

    author = db.get(User, problem.author_id)
    accepted = db.scalar(
        select(Submission.id)
        .where(Submission.problem_id == problem.id, Submission.status == "accepted")
        .limit(1)
    )
    solved = False
    if viewer_id:
        solved = bool(
            db.scalar(
                select(Submission.id)
                .where(
                    Submission.problem_id == problem.id,
                    Submission.user_id == viewer_id,
                    Submission.status == "accepted",
                    Submission.kind == "submit",
                )
                .limit(1)
            )
        )
    result = {
        "id": problem.id,
        "slug": problem.slug,
        "status": problem.status,
        "language": problem.language,
        "version": version.version_number,
        "title": version.title,
        "difficulty": version.difficulty,
        "tags": version.tags,
        "author": author.display_name if author else "匿名",
        "solved": solved,
        "can_edit": bool(viewer_id and viewer_id == problem.author_id),
        "has_accepts": bool(accepted),
        "published_at": version.published_at.isoformat(),
    }
    if include_description:
        result.update(
            {
                "description": version.description,
                "function_spec": version.function_spec,
                "starter_code": version.starter_code,
                "public_cases": version.public_cases,
                "constraints": version.constraints,
                "checker": {
                    key: value
                    for key, value in version.checker.items()
                    if key in {"kind", "atol", "rtol", "threshold"}
                },
                "resource_limits": version.resource_limits,
            }
        )
    return result
