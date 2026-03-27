from sqlalchemy import Table, create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
import os

# ── Database URL ──────────────────────────────────────────────────────────────
_DB_PATH = os.environ.get("CHAINBREAK_DB_PATH", "instance/chainbreak.db")
os.makedirs(os.path.dirname(_DB_PATH) if os.path.dirname(
    _DB_PATH) else ".", exist_ok=True)
DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_db():
    """FastAPI dependency — yields a DB session, closes on exit."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Models ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(20), default="analyst", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    role_id = Column(Integer, ForeignKey(
        "roles.id"), nullable=True, index=True)
    role_obj = relationship("Role", back_populates="users", lazy="joined")
    sessions = relationship(
        "UserSession", back_populates="user", lazy="dynamic")

    investigations = relationship(
        "Investigation", back_populates="user", lazy="dynamic")
    audit_logs = relationship(
        "AuditLog", back_populates="user", lazy="dynamic")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def has_permission(self, permission):
        """Check if user has specific permission"""
        if self.role == "admin":  # Backward compatibility
            return True
        if self.role_obj:
            return self.role_obj.has_permission(permission)
        return False

    def get_all_permissions(self):
        """Get all user permissions"""
        if self.role == "admin":  # Backward compatibility
            return ["*"]  # All permissions
        if self.role_obj:
            return self.role_obj.get_permissions()
        return []

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "is_active": self.is_active,
        }


class Investigation(Base):
    __tablename__ = "investigations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    case_id = Column(String(50), unique=True, nullable=False, index=True)
    case_name = Column(String(200), nullable=False)
    primary_address = Column(String(100), index=True, nullable=True)
    json_data = Column(Text, nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    user = relationship("User", back_populates="investigations")

    def set_data(self, data):
        self.json_data = json.dumps(data)

    def get_data(self):
        return json.loads(self.json_data) if self.json_data else {}

    def to_dict(self, include_data=False):
        result = {
            "id": self.id,
            "user_id": self.user_id,
            "case_id": self.case_id,
            "case_name": self.case_name,
            "primary_address": self.primary_address,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_data:
            result["data"] = self.get_data()
        return result


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(
        "users.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="audit_logs")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    @classmethod
    def log(
        cls,
        action,
        user_id=None,
        resource_type=None,
        resource_id=None,
        details=None,
        ip_address=None,
        user_agent=None,
        db: Session = None,
    ):
        """Log an audit entry. Accepts an optional db session; creates its own if not provided."""
        created_session = False
        if db is None:
            db = SessionLocal()
            created_session = True
        try:
            log_entry = cls(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)
            return log_entry
        except Exception:
            db.rollback()
            raise
        finally:
            if created_session:
                db.close()


class APICache(Base):
    __tablename__ = "api_cache"

    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String(256), unique=True, nullable=False, index=True)
    data = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    @classmethod
    def get_cached(cls, key, db: Session = None):
        created_session = False
        if db is None:
            db = SessionLocal()
            created_session = True
        try:
            entry = db.query(cls).filter(cls.cache_key == key).first()
            if entry and entry.expires_at > datetime.utcnow():
                return json.loads(entry.data) if entry.data else None
            if entry:
                db.delete(entry)
                db.commit()
            return None
        finally:
            if created_session:
                db.close()

    @classmethod
    def set_cached(cls, key, data, ttl_seconds=3600, db: Session = None):
        from datetime import timedelta
        created_session = False
        if db is None:
            db = SessionLocal()
            created_session = True
        try:
            entry = db.query(cls).filter(cls.cache_key == key).first()
            if entry:
                entry.data = json.dumps(data)
                entry.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
            else:
                entry = cls(
                    cache_key=key,
                    data=json.dumps(data),
                    expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds),
                )
                db.add(entry)
            db.commit()
        finally:
            if created_session:
                db.close()


# ── DB Init ───────────────────────────────────────────────────────────────────

def init_db():
    """Create all tables, seed default roles, and seed the default admin user."""
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        from .rbac import RBACManager
        RBACManager.create_default_roles(db)

        admin_role = db.query(Role).filter(Role.name == "admin").first()

        _admin_username = os.environ.get("ADMIN_USERNAME", "admin")
        _admin_email = os.environ.get("ADMIN_EMAIL", "admin@chainbreak.local").lower()
        _admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()

        import logging as _logging
        _log = _logging.getLogger(__name__)

        admin = db.query(User).filter(User.username == _admin_username).first()
        if not admin:
            if not _admin_password:
                _log.warning(
                    "ADMIN_PASSWORD env var not set — skipping default admin creation. "
                    "Set ADMIN_PASSWORD to seed an admin user on first startup."
                )
            else:
                admin = User(
                    username=_admin_username,
                    email=_admin_email,
                    role="admin",
                    role_id=admin_role.id if admin_role else None,
                )
                admin.set_password(_admin_password)
                db.add(admin)
                db.commit()
        elif admin_role and admin.role_id != admin_role.id:
            admin.role_id = admin_role.id
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    # admin, analyst, viewer, investigator
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))
    permissions = Column(Text)  # JSON string of permissions
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="role_obj")

    def get_permissions(self):
        """Get permissions as a list"""
        return json.loads(self.permissions) if self.permissions else []

    def set_permissions(self, permissions_list):
        """Set permissions from a list"""
        self.permissions = json.dumps(permissions_list)

    def has_permission(self, permission):
        """Check if role has specific permission"""
        return permission in self.get_permissions()


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    session_token = Column(String(128), unique=True,
                           nullable=False, index=True)  # UUID
    # JWT ID claim (optional)
    jti = Column(String(64), unique=True, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="sessions")


class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))


role_permission = Table(
    "role_permission",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id")),
    Column("permission_id", Integer, ForeignKey("permissions.id")),
    UniqueConstraint("role_id", "permission_id")
)
