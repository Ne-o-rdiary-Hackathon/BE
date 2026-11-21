from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.dependencies import bearer_scheme, get_current_user
from app.common import BusinessException, ErrorCode
from app.core.config import settings
from app.db.session import get_db


def get_current_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    x_dev_user_id: int | None = Header(default=None, alias="X-Dev-User-Id"),
) -> int:
    """Use a local Swagger identity only when explicitly enabled for development."""
    if (
        settings.app_env == "development"
        and settings.dev_auth_enabled
        and x_dev_user_id is not None
    ):
        user_id = x_dev_user_id
    else:
        return get_current_user(request, credentials, db).user_id

    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1:
        raise BusinessException(ErrorCode.UNAUTHORIZED)
    return user_id
