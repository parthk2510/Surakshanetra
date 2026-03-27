from typing import List, Callable
import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .models import User, Role

logger = logging.getLogger(__name__)

# -------------------------
# Permission constants
# -------------------------
PERMISSIONS = {
    "case_create": "Create new investigation cases",
    "case_read": "View investigation cases",
    "case_update": "Update investigation cases",
    "case_delete": "Delete investigation cases",
    "case_export": "Export case data",

    "analysis_run": "Run analysis on cases",
    "analysis_view": "View analysis results",
    "analysis_delete": "Delete analysis results",

    "user_create": "Create new users",
    "user_read": "View user information",
    "user_update": "Update user information",
    "user_delete": "Delete users",
    "user_manage_roles": "Manage user roles",

    "system_config": "Access system configuration",
    "system_logs": "View system logs",
    "system_backup": "Perform system backups",

    "admin_all": "Full administrative access"
}

ALL_PERMISSIONS = "*"


# -------------------------
# Custom Exceptions
# -------------------------
class RBACException(Exception):
    pass


class NotFoundError(RBACException):
    pass


class InvalidRoleError(RBACException):
    pass


# -------------------------
# RBAC Manager
# -------------------------
class RBACManager:

    @staticmethod
    def create_default_roles(db: Session) -> None:
        """Create default roles safely (idempotent)."""

        role_configs = {
            "admin": {
                "description": "System administrator with full access",
                "permissions": [ALL_PERMISSIONS],
            },
            "investigator": {
                "description": "Senior investigator",
                "permissions": [
                    "case_create", "case_read", "case_update", "case_delete", "case_export",
                    "analysis_run", "analysis_view", "analysis_delete",
                    "user_read"
                ],
            },
            "analyst": {
                "description": "Data analyst",
                "permissions": [
                    "case_create", "case_read", "case_update", "case_export",
                    "analysis_run", "analysis_view"
                ],
            },
            "viewer": {
                "description": "Read-only access",
                "permissions": ["case_read", "analysis_view"],
            },
        }

        try:
            for role_name, config in role_configs.items():
                existing_role = db.query(Role).filter(Role.name == role_name).first()

                if existing_role:
                    continue

                role = Role(
                    name=role_name,
                    description=config["description"]
                )
                role.set_permissions(config["permissions"])

                db.add(role)

            db.commit()
            logger.info("Default roles ensured successfully.")

        except SQLAlchemyError as e:
            db.rollback()
            logger.exception("Failed to create default roles.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initialize roles"
            ) from e

    @staticmethod
    def assign_role_to_user(user_id: int, role_name: str, db: Session) -> User:
        """Assign a role to a user with full validation."""

        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise NotFoundError(f"User with id {user_id} not found")

            role = db.query(Role).filter(Role.name == role_name).first()
            if not role:
                raise InvalidRoleError(f"Role '{role_name}' does not exist")

            user.role_id = role.id

            # Legacy fallback handling
            role_mapping = {
                "admin": "admin",
                "investigator": "analyst",
                "analyst": "analyst",
                "viewer": "viewer"
            }
            user.role = role_mapping.get(role_name, "viewer")

            db.commit()
            db.refresh(user)

            logger.info(f"Assigned role '{role_name}' to user {user_id}")
            return user

        except (NotFoundError, InvalidRoleError) as e:
            db.rollback()
            logger.warning(str(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

        except SQLAlchemyError as e:
            db.rollback()
            logger.exception("Database error while assigning role.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error"
            ) from e


# -------------------------
# Helper
# -------------------------

def _has_permission(user: User, permission: str) -> bool:
    try:
        user_permissions = user.get_all_permissions()
        return ALL_PERMISSIONS in user_permissions or permission in user_permissions
    except Exception:
        logger.exception("Error checking permissions.")
        return False


# -------------------------
# FastAPI dependency factories
# -------------------------

def require_permission(permission: str) -> Callable:
    from .auth import get_current_user

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not _has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )
        return current_user

    return dependency


def require_any_permission(permissions: List[str]) -> Callable:
    from .auth import get_current_user

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        user_permissions = current_user.get_all_permissions()
        if ALL_PERMISSIONS in user_permissions:
            return current_user
        if not any(p in user_permissions for p in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(permissions)}",
            )
        return current_user

    return dependency


def require_role(role: str) -> Callable:
    from .auth import get_current_user

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        user_role = (
            current_user.role_obj.name
            if getattr(current_user, "role_obj", None)
            else current_user.role
        )
        if user_role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required",
            )
        return current_user

    return dependency