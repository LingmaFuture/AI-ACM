import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_db
from .dependencies import admin_user, contributor_user, current_user, optional_user
from .extraction import validate_upload
from .mailer import send_verification_email
from .models import (
    GenerationJob,
    ModerationAction,
    PrivateJudgeBundle,
    Problem,
    ProblemDraft,
    ProblemReport,
    ProblemVersion,
    SourceUpload,
    Submission,
    User,
)
from .rate_limit import limiter, request_key
from .schemas import (
    DraftUpdate,
    LoginRequest,
    ModerationRequest,
    ProblemDraftV1,
    RegisterRequest,
    ReportRequest,
    SubmissionRequest,
)
from .security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    create_session,
    create_verification_token,
    hash_password,
    read_verification_token,
    verify_password,
)
from .services import create_problem, create_problem_version, public_problem_dict
from .storage import private_storage
from .tasks import dispatch, generate_draft_task, judge_submission_task, validate_draft_task

router = APIRouter(prefix=settings.api_prefix)


def user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "email_verified": user.email_verified,
        "contribution_suspended": user.contribution_suspended,
        "created_at": user.created_at.isoformat(),
    }


def ensure_owner(record_owner: str, user: User) -> None:
    if record_owner != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="没有权限访问此内容")


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ai-acm-api"}


@router.post("/auth/register", status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    limiter.check(request_key(request, None, "register"), 5, 3600)
    email = payload.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="该邮箱已注册")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_verification_token(user.id)
    verification_url = f"{settings.frontend_url}/verify?token={token}"
    try:
        send_verification_email(user.email, verification_url)
    except Exception as exc:
        print(f"[AI-ACM] email delivery failed: {exc}; link={verification_url}")
    result = {"message": "注册成功，请检查邮箱完成验证", "user": user_dict(user)}
    if settings.environment == "development":
        result["verification_token"] = token
    return result


@router.get("/auth/verify")
async def verify_email(token: str, db: Session = Depends(get_db)) -> dict:
    user_id = read_verification_token(token)
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise HTTPException(status_code=400, detail="验证链接无效或已过期")
    user.email_verified = True
    db.commit()
    return {"message": "邮箱验证成功"}


@router.post("/auth/login")
async def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被停用")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="请先验证邮箱")
    response.set_cookie(
        SESSION_COOKIE,
        create_session(user.id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"user": user_dict(user)}


@router.post("/auth/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"message": "已退出登录"}


@router.get("/auth/me")
async def me(user: User | None = Depends(optional_user)) -> dict:
    return {"user": user_dict(user) if user else None}


@router.get("/problems")
async def list_problems(
    q: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    solved: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    viewer: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = (
        select(Problem, ProblemVersion)
        .join(ProblemVersion, Problem.current_version_id == ProblemVersion.id)
        .where(Problem.status == "published")
        .order_by(Problem.created_at.desc())
    )
    if q:
        statement = statement.where(ProblemVersion.title.ilike(f"%{q[:80]}%"))
    if difficulty:
        statement = statement.where(ProblemVersion.difficulty == difficulty)
    rows = db.execute(statement).all()
    items = [public_problem_dict(db, problem, version, viewer.id if viewer else None) for problem, version in rows]
    if tag:
        items = [item for item in items if tag.lower() in {str(value).lower() for value in item["tags"]}]
    if solved is not None:
        items = [item for item in items if item["solved"] is solved]
    total = len(items)
    return {"items": items[offset : offset + limit], "total": total}


@router.get("/problems/{slug}")
async def get_problem(
    slug: str,
    viewer: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.execute(
        select(Problem, ProblemVersion)
        .join(ProblemVersion, Problem.current_version_id == ProblemVersion.id)
        .where(Problem.slug == slug, Problem.status == "published")
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="题目不存在")
    return public_problem_dict(db, row[0], row[1], viewer.id if viewer else None, True)


def create_submission(
    problem_id: str,
    kind: str,
    payload: SubmissionRequest,
    request: Request,
    user: User,
    db: Session,
) -> dict:
    limiter.check(request_key(request, user.id, "judge"), 30, 60)
    problem = db.get(Problem, problem_id)
    if not problem or problem.status != "published" or not problem.current_version_id:
        raise HTTPException(status_code=404, detail="题目不存在")
    submission = Submission(
        user_id=user.id,
        problem_id=problem.id,
        version_id=problem.current_version_id,
        kind=kind,
        code=payload.code,
        status="queued",
    )
    db.add(submission)
    db.commit()
    submission_id = submission.id
    dispatch(judge_submission_task, submission_id)
    return {"id": submission_id, "status": "queued", "events_url": f"/api/v1/submissions/{submission_id}/events"}


@router.post("/problems/{problem_id}/run", status_code=202)
async def run_problem(
    problem_id: str,
    payload: SubmissionRequest,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    return create_submission(problem_id, "run", payload, request, user, db)


@router.post("/problems/{problem_id}/submit", status_code=202)
async def submit_problem(
    problem_id: str,
    payload: SubmissionRequest,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    return create_submission(problem_id, "submit", payload, request, user, db)


def submission_dict(submission: Submission) -> dict:
    return {
        "id": submission.id,
        "problem_id": submission.problem_id,
        "version_id": submission.version_id,
        "kind": submission.kind,
        "status": submission.status,
        "passed_cases": submission.passed_cases,
        "total_cases": submission.total_cases,
        "runtime_ms": submission.runtime_ms,
        "result": submission.result,
        "created_at": submission.created_at.isoformat(),
        "finished_at": submission.finished_at.isoformat() if submission.finished_at else None,
    }


@router.get("/submissions/{submission_id}")
async def get_submission(
    submission_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    submission = db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")
    ensure_owner(submission.user_id, user)
    return submission_dict(submission)


@router.get("/submissions/{submission_id}/events")
async def submission_events(
    submission_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    submission = db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")
    ensure_owner(submission.user_id, user)

    async def stream():
        last_status = None
        for _ in range(150):
            stream_db = SessionLocal()
            try:
                current = stream_db.get(Submission, submission_id)
                if not current:
                    yield 'event: error\ndata: {"message":"提交不存在"}\n\n'
                    return
                if current.status != last_status or current.finished_at:
                    data = json.dumps(submission_dict(current), ensure_ascii=False)
                    yield f"event: status\ndata: {data}\n\n"
                    last_status = current.status
                if current.finished_at:
                    return
            finally:
                stream_db.close()
            await asyncio.sleep(0.4)
        yield 'event: error\ndata: {"message":"等待判题结果超时"}\n\n'

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/problems/{problem_id}/submissions")
async def problem_submissions(
    problem_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(Submission)
        .where(Submission.problem_id == problem_id, Submission.user_id == user.id)
        .order_by(Submission.created_at.desc())
        .limit(20)
    ).all()
    return {"items": [submission_dict(item) for item in rows]}


@router.post("/uploads", status_code=201)
async def upload_source(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(contributor_user),
    db: Session = Depends(get_db),
) -> dict:
    limiter.check(request_key(request, user.id, "upload"), 10, 3600)
    content = await file.read(settings.upload_max_bytes + 1)
    validate_upload(file.filename or "upload", content)
    suffix = Path(file.filename or "upload").suffix.lower()
    record = SourceUpload(
        owner_id=user.id,
        original_name=(file.filename or "upload")[:255],
        object_key="pending",
        content_type=(file.content_type or "application/octet-stream")[:120],
        size_bytes=len(content),
    )
    db.add(record)
    db.flush()
    record.object_key = f"{user.id}/{record.id}{suffix}"
    private_storage.put(record.object_key, content, record.content_type)
    db.commit()
    return {
        "id": record.id,
        "original_name": record.original_name,
        "size_bytes": record.size_bytes,
        "status": record.status,
        "private": True,
    }


@router.post("/uploads/{upload_id}/generate", status_code=202)
async def generate_from_upload(
    upload_id: str,
    request: Request,
    user: User = Depends(contributor_user),
    db: Session = Depends(get_db),
) -> dict:
    limiter.check(request_key(request, user.id, "generate"), 8, 3600)
    upload = db.get(SourceUpload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="上传记录不存在")
    ensure_owner(upload.owner_id, user)
    if upload.status not in {"uploaded", "failed"}:
        raise HTTPException(status_code=409, detail="该资料已经在处理")
    job = GenerationJob(owner_id=user.id, upload_id=upload.id, kind="generate", status="queued")
    db.add(job)
    upload.status = "queued"
    db.commit()
    job_id = job.id
    dispatch(generate_draft_task, job_id)
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    job = db.get(GenerationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    ensure_owner(job.owner_id, user)
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "result": job.result,
        "error": job.error,
        "draft_id": job.draft_id,
        "updated_at": job.updated_at.isoformat(),
    }


def draft_dict(draft: ProblemDraft) -> dict:
    return {
        "id": draft.id,
        "status": draft.status,
        "source_upload_id": draft.source_upload_id,
        "payload": draft.payload,
        "rights_attested": draft.rights_attested,
        "validation_report": draft.validation_report,
        "published_problem_id": draft.published_problem_id,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
    }


@router.get("/drafts")
async def list_drafts(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    statement = select(ProblemDraft).order_by(ProblemDraft.updated_at.desc())
    if user.role != "admin":
        statement = statement.where(ProblemDraft.owner_id == user.id)
    rows = db.scalars(statement.limit(50)).all()
    return {"items": [draft_dict(item) for item in rows]}


@router.get("/drafts/{draft_id}")
async def get_draft(
    draft_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    draft = db.get(ProblemDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    ensure_owner(draft.owner_id, user)
    return draft_dict(draft)


@router.patch("/drafts/{draft_id}")
async def update_draft(
    draft_id: str,
    payload: DraftUpdate,
    user: User = Depends(contributor_user),
    db: Session = Depends(get_db),
) -> dict:
    draft = db.get(ProblemDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    ensure_owner(draft.owner_id, user)
    if draft.status == "published":
        raise HTTPException(status_code=409, detail="已发布版本不可覆盖")
    draft.payload = payload.payload.model_dump(mode="json")
    draft.rights_attested = payload.rights_attested
    draft.validation_report = None
    draft.status = "draft"
    db.commit()
    return draft_dict(draft)


@router.post("/drafts/{draft_id}/validate", status_code=202)
async def validate_draft_endpoint(
    draft_id: str,
    request: Request,
    user: User = Depends(contributor_user),
    db: Session = Depends(get_db),
) -> dict:
    limiter.check(request_key(request, user.id, "validate"), 12, 3600)
    draft = db.get(ProblemDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    ensure_owner(draft.owner_id, user)
    if draft.status in {"validating", "published"}:
        raise HTTPException(status_code=409, detail="草稿当前状态不可校验")
    job = GenerationJob(
        owner_id=user.id, draft_id=draft.id, kind="validate", status="queued"
    )
    db.add(job)
    draft.status = "validating"
    db.commit()
    job_id = job.id
    dispatch(validate_draft_task, job_id)
    return {"job_id": job_id, "status": "queued"}


@router.post("/drafts/{draft_id}/publish", status_code=201)
async def publish_draft(
    draft_id: str,
    user: User = Depends(contributor_user),
    db: Session = Depends(get_db),
) -> dict:
    draft = db.get(ProblemDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    ensure_owner(draft.owner_id, user)
    if draft.status == "published":
        raise HTTPException(status_code=409, detail="草稿已经发布")
    if not draft.rights_attested:
        raise HTTPException(status_code=400, detail="发布前必须确认内容授权")
    if not draft.validation_report or not draft.validation_report.get("passed"):
        raise HTTPException(status_code=400, detail="草稿尚未通过自动质量门禁")
    payload = ProblemDraftV1.model_validate(draft.payload)
    if draft.published_problem_id:
        problem = db.get(Problem, draft.published_problem_id)
        if not problem:
            raise HTTPException(status_code=404, detail="待修订的题目不存在")
        ensure_owner(problem.author_id, user)
        create_problem_version(db, problem, payload)
    else:
        problem = create_problem(db, draft.owner_id, payload)
    draft.status = "published"
    draft.published_problem_id = problem.id
    db.commit()
    return {"id": problem.id, "slug": problem.slug, "status": problem.status}


@router.post("/problems/{problem_id}/revisions", status_code=201)
async def create_revision_draft(
    problem_id: str,
    user: User = Depends(contributor_user),
    db: Session = Depends(get_db),
) -> dict:
    problem = db.get(Problem, problem_id)
    if not problem or not problem.current_version_id:
        raise HTTPException(status_code=404, detail="题目不存在")
    ensure_owner(problem.author_id, user)
    version = db.get(ProblemVersion, problem.current_version_id)
    bundle = db.scalar(
        select(PrivateJudgeBundle).where(PrivateJudgeBundle.version_id == problem.current_version_id)
    )
    if not version or not bundle:
        raise HTTPException(status_code=500, detail="当前判题版本不完整")
    payload = ProblemDraftV1.model_validate(
        {
            "schema_version": "ProblemDraftV1",
            "title": version.title,
            "slug_hint": problem.slug,
            "description": version.description,
            "difficulty": version.difficulty,
            "tags": version.tags,
            "constraints": version.constraints,
            "function_spec": version.function_spec,
            "starter_code": version.starter_code,
            "public_cases": version.public_cases,
            "hidden_cases": bundle.hidden_cases,
            "checker": version.checker,
            "resource_limits": version.resource_limits,
            "reference_solution": bundle.reference_solution,
            "mutants": bundle.mutants,
        }
    )
    draft = ProblemDraft(
        owner_id=user.id,
        status="draft",
        payload=payload.model_dump(mode="json"),
        published_problem_id=problem.id,
    )
    db.add(draft)
    db.commit()
    return draft_dict(draft)


@router.post("/problems/{problem_id}/reports", status_code=201)
async def report_problem(
    problem_id: str,
    payload: ReportRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not db.get(Problem, problem_id):
        raise HTTPException(status_code=404, detail="题目不存在")
    report = ProblemReport(
        problem_id=problem_id,
        reporter_id=user.id,
        reason=payload.reason,
        details=payload.details,
    )
    db.add(report)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="你已经举报过该题") from exc
    return {"id": report.id, "status": report.status}


@router.post("/admin/problems/{problem_id}/delist")
async def delist_problem(
    problem_id: str,
    payload: ModerationRequest,
    user: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    problem = db.get(Problem, problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="题目不存在")
    problem.status = "delisted"
    db.add(
        ModerationAction(
            problem_id=problem.id, moderator_id=user.id, action="delist", reason=payload.reason
        )
    )
    db.commit()
    return {"id": problem.id, "status": problem.status}


@router.post("/admin/problems/{problem_id}/restore")
async def restore_problem(
    problem_id: str,
    payload: ModerationRequest,
    user: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    problem = db.get(Problem, problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="题目不存在")
    problem.status = "published"
    db.add(
        ModerationAction(
            problem_id=problem.id, moderator_id=user.id, action="restore", reason=payload.reason
        )
    )
    db.commit()
    return {"id": problem.id, "status": problem.status}


@router.post("/admin/users/{user_id}/contributions/suspend")
async def suspend_contributions(
    user_id: str,
    payload: ModerationRequest,
    moderator: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    target.contribution_suspended = True
    db.add(
        ModerationAction(
            target_user_id=target.id,
            moderator_id=moderator.id,
            action="suspend_contributions",
            reason=payload.reason,
        )
    )
    db.commit()
    return {"user_id": target.id, "contribution_suspended": True}


@router.post("/admin/users/{user_id}/contributions/restore")
async def restore_contributions(
    user_id: str,
    payload: ModerationRequest,
    moderator: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    target.contribution_suspended = False
    db.add(
        ModerationAction(
            target_user_id=target.id,
            moderator_id=moderator.id,
            action="restore_contributions",
            reason=payload.reason,
        )
    )
    db.commit()
    return {"user_id": target.id, "contribution_suspended": False}


@router.get("/profile")
async def profile(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    submissions = db.scalar(select(func.count(Submission.id)).where(Submission.user_id == user.id)) or 0
    accepted_problem_ids = db.scalars(
        select(distinct(Submission.problem_id)).where(
            Submission.user_id == user.id,
            Submission.kind == "submit",
            Submission.status == "accepted",
        )
    ).all()
    tags: dict[str, int] = {}
    if accepted_problem_ids:
        rows = db.execute(
            select(ProblemVersion.tags)
            .join(Problem, Problem.current_version_id == ProblemVersion.id)
            .where(Problem.id.in_(accepted_problem_ids))
        ).all()
        for (problem_tags,) in rows:
            for tag in problem_tags:
                tags[str(tag)] = tags.get(str(tag), 0) + 1
    days = db.scalars(
        select(Submission.created_at)
        .where(Submission.user_id == user.id)
        .order_by(Submission.created_at.desc())
    ).all()
    unique_days = sorted({value.date() for value in days}, reverse=True)
    streak = 0
    cursor = datetime.now(UTC).date()
    for day in unique_days:
        if day == cursor:
            streak += 1
            cursor = cursor.fromordinal(cursor.toordinal() - 1)
        elif day < cursor:
            break
    return {
        "user": user_dict(user),
        "stats": {
            "solved": len(accepted_problem_ids),
            "submissions": submissions,
            "streak": streak,
            "tags": tags,
        },
    }


@router.get("/leaderboard")
async def leaderboard(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(
            User.id,
            User.display_name,
            func.count(distinct(Submission.problem_id)).label("solved"),
            func.min(Submission.created_at).label("first_accept"),
        )
        .join(Submission, Submission.user_id == User.id)
        .where(Submission.kind == "submit", Submission.status == "accepted", User.is_active.is_(True))
        .group_by(User.id, User.display_name)
        .order_by(func.count(distinct(Submission.problem_id)).desc(), func.min(Submission.created_at))
        .limit(100)
    ).all()
    return {
        "items": [
            {"rank": index, "user_id": row.id, "display_name": row.display_name, "solved": row.solved}
            for index, row in enumerate(rows, start=1)
        ]
    }
