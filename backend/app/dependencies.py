from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import SESSION_COOKIE, read_session


async def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = read_session(token) if token else None
    if not user_id:
        return None
    user = db.get(User, user_id)
    return user if user and user.is_active else None


async def current_user(user: User | None = Depends(optional_user)) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    if not user.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请先验证邮箱")
    return user


async def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


async def contributor_user(user: User = Depends(current_user)) -> User:
    if user.contribution_suspended:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该账号的投稿权限已暂停")
    return user
