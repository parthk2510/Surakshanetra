import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.auth import get_current_user, require_admin, _get_client_ip
from backend.database.models import get_db, User, Role, UserSession, AuditLog
from backend.database.rbac import require_permission, RBACManager

user_mgmt_bp = APIRouter(prefix="/api/users", tags=["user-management"])


class AssignRoleRequest(BaseModel):
    user_id: int
    role: str


class RevokeSessionRequest(BaseModel):
    session_token: str


class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "analyst"


class ResetPasswordRequest(BaseModel):
    new_password: str


def _validate_password(password: str) -> str:
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return "Password must contain at least one special character"
    return ""


@user_mgmt_bp.get("")
@user_mgmt_bp.get("/list")
async def list_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).filter(User.is_active == True).all()
    return {
        "success": True,
        "users": [u.to_dict() for u in users],
    }


@user_mgmt_bp.get("/roles")
async def get_all_roles(
    current_user: User = Depends(require_permission("user_read")),
    db: Session = Depends(get_db),
):
    roles = db.query(Role).filter(Role.is_active == True).all()
    return {
        "success": True,
        "roles": [
            {
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "permissions": role.get_permissions(),
            }
            for role in roles
        ],
    }


@user_mgmt_bp.post("/create")
async def create_user(
    body: CreateUserRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    username = body.username.strip()
    email = body.email.strip().lower()

    if not username or len(username) < 3 or len(username) > 20 or not re.match(r"^[a-zA-Z0-9_]+$", username):
        raise HTTPException(status_code=400, detail="Username must be 3-20 alphanumeric/underscore characters")

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")

    err = _validate_password(body.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="Username already exists")

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    role_obj = db.query(Role).filter(Role.name == body.role).first()

    user = User(
        username=username,
        email=email,
        role=body.role,
        role_id=role_obj.id if role_obj else None,
    )
    user.set_password(body.password)
    db.add(user)
    db.commit()
    db.refresh(user)

    AuditLog.log(
        action="admin_created_user",
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(user.id),
        details=f"Created user '{username}' with role '{body.role}'",
        db=db,
    )

    return {"success": True, "user": user.to_dict()}


@user_mgmt_bp.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    body: ResetPasswordRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    err = _validate_password(body.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    user.set_password(body.new_password)
    db.commit()

    AuditLog.log(
        action="admin_reset_password",
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(user_id),
        details=f"Admin reset password for user '{user.username}'",
        db=db,
    )

    return {"success": True, "message": f"Password reset for '{user.username}'"}


@user_mgmt_bp.post("/assign-role")
async def assign_role(
    body: AssignRoleRequest,
    request: Request,
    current_user: User = Depends(require_permission("user_manage_roles")),
    db: Session = Depends(get_db),
):
    try:
        user = RBACManager.assign_role_to_user(body.user_id, body.role, db)
        AuditLog.log(
            action="role_assigned",
            user_id=current_user.id,
            resource_type="user",
            resource_id=str(body.user_id),
            details=f"Assigned role '{body.role}' to user '{user.username}' by '{current_user.username}'",
            ip_address=_get_client_ip(request),
            db=db,
        )
        return {"success": True, "user": user.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@user_mgmt_bp.get("/sessions")
async def get_active_sessions(
    current_user: User = Depends(require_permission("system_logs")),
    db: Session = Depends(get_db),
):
    sessions = db.query(UserSession).filter(
        UserSession.is_active == True,
        UserSession.expires_at > datetime.utcnow(),
    ).all()

    return {
        "success": True,
        "sessions": [
            {
                "id": session.id,
                "user_id": session.user_id,
                "username": session.user.username,
                "ip_address": session.ip_address,
                "created_at": session.created_at.isoformat(),
                "last_activity": session.last_activity.isoformat(),
                "expires_at": session.expires_at.isoformat(),
            }
            for session in sessions
        ],
    }


@user_mgmt_bp.post("/revoke-session")
async def revoke_session(
    body: RevokeSessionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    session = db.query(UserSession).filter(
        UserSession.session_token == body.session_token
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.is_active = False
    db.commit()

    return {"success": True, "message": "Session revoked"}
