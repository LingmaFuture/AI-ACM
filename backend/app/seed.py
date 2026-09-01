from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Problem, User
from .schemas import ProblemDraftV1
from .security import hash_password
from .seed_data import SEED_DRAFTS
from .services import create_problem


def seed_database(db: Session) -> None:
    system = db.scalar(select(User).where(User.email == "system@aiacm.local"))
    if not system:
        system = User(
            email="system@aiacm.local",
            password_hash=hash_password("unusable-system-password"),
            display_name="AI-ACM 题库组",
            role="admin",
            email_verified=True,
        )
        db.add(system)
        db.flush()
    if not db.scalar(select(Problem.id).limit(1)):
        for raw in SEED_DRAFTS:
            create_problem(db, system.id, ProblemDraftV1.model_validate(raw))
    db.commit()

