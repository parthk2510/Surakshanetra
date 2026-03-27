from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from .models import SessionLocal, User, UserSession, AuditLog, get_db
import re
import uuid
import logging
import os

logger = logging.getLogger(__name__)

def _log_security(event_type: str, details: str, user_id=None, ip_address=None):
    logging.getLogger("security").warning(
        "SECURITY %s: %s [user_id=%s, ip=%s]", event_type, details, user_id, ip_address
    )

JWT_SECRET_KEY = os.environ.get("CHAINBREAK_SECRET_KEY", "").strip()
if not JWT_SECRET_KEY:
    import secrets as _secrets
    JWT_SECRET_KEY = _secrets.token_hex(32)
    logger.warning(
        "CHAINBREAK_SECRET_KEY not set — auto-generated ephemeral key for this process. "
        "Sessions will NOT persist across restarts. "
        "Set CHAINBREAK_SECRET_KEY in your .env file for production use."
    )
elif len(JWT_SECRET_KEY) < 32:
    raise RuntimeError(
        "CHAINBREAK_SECRET_KEY is too short (minimum 32 characters required)."
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_EXPIRE_DAYS = 30
SESSION_EXPIRE_HOURS = 24

_SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "true").lower() != "false"
_TRUSTED_PROXIES = {
    p.strip() for p in os.environ.get("TRUSTED_PROXIES", "127.0.0.1,::1,172.16.0.0/12,10.0.0.0/8").split(",")
    if p.strip()
}

token_blocklist: set = set()

# ── Simple in-process rate limiter (no external deps) ─────────────────────────
import threading as _threading
import time as _time

class _RateLimiter:
    """Token-bucket rate limiter keyed by IP address."""
    def __init__(self, max_calls: int, window_seconds: int):
        self._max = max_calls
        self._window = window_seconds
        self._counts: dict = {}  # ip -> [call_time, ...]
        self._lock = _threading.Lock()

    def is_allowed(self, ip: str) -> bool:
        now = _time.monotonic()
        cutoff = now - self._window
        with self._lock:
            calls = self._counts.get(ip, [])
            calls = [t for t in calls if t > cutoff]
            if len(calls) >= self._max:
                self._counts[ip] = calls
                return False
            calls.append(now)
            self._counts[ip] = calls
            return True

_login_limiter = _RateLimiter(max_calls=10, window_seconds=60)
_register_limiter = _RateLimiter(max_calls=5, window_seconds=60)
# ──────────────────────────────────────────────────────────────────────────────

auth_bp = APIRouter(prefix="/api/auth", tags=["auth"])


def create_access_token(identity: str, jti: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": identity, "exp": expire, "type": "access", "jti": jti},
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def create_refresh_token(identity: str, jti: str) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": identity, "exp": expire, "type": "refresh", "jti": jti},
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def _decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _extract_bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("access_token_cookie")


def _is_trusted_proxy(ip: str) -> bool:
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
        for proxy in _TRUSTED_PROXIES:
            try:
                if "/" in proxy:
                    if addr in ipaddress.ip_network(proxy, strict=False):
                        return True
                elif addr == ipaddress.ip_address(proxy):
                    return True
            except ValueError:
                continue
    except ValueError:
        pass
    return False


def _get_client_ip(request: Request) -> str:
    client_ip = request.client.host if request.client else "unknown"
    if _is_trusted_proxy(client_ip):
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP", "")
        if real_ip:
            return real_ip.strip()
    return client_ip


def _identity_to_user_id(identity) -> int:
    try:
        return int(identity)
    except (TypeError, ValueError) as exc:
        logger.error("Malformed JWT sub claim: %r — %s", identity, exc)
        raise HTTPException(status_code=401, detail="Invalid token claims")


def _set_auth_cookies(resp: JSONResponse, access_token: str, refresh_token: str, session_token: str = None):
    resp.set_cookie(
        "access_token_cookie", access_token,
        httponly=True, secure=_SECURE_COOKIES, samesite="strict",
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    )
    resp.set_cookie(
        "refresh_token_cookie", refresh_token,
        httponly=True, secure=_SECURE_COOKIES, samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )
    if session_token is not None:
        resp.set_cookie(
            "session_token", session_token,
            httponly=True, secure=_SECURE_COOKIES, samesite="strict",
            max_age=SESSION_EXPIRE_HOURS * 3600,
        )


def create_user_session(user_id: int, request: Request, db: Session) -> str:
    user = db.query(User).filter(User.id == user_id).first()
    
    # Enforce strict single-session constraint for admin users
    if user and user.role == "admin":
        active_sessions = db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.is_active == True
        ).all()
        
        for session in active_sessions:
            session.is_active = False
            
    session_token = str(uuid.uuid4())
    user_session = UserSession(
        user_id=user_id,
        session_token=session_token,
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("User-Agent", "")[:500],
        expires_at=datetime.utcnow() + timedelta(hours=SESSION_EXPIRE_HOURS),
    )
    db.add(user_session)
    db.commit()
    return session_token


def revoke_user_session(session_token: str, db: Session):
    session = db.query(UserSession).filter(
        UserSession.session_token == session_token
    ).first()
    if session:
        session.is_active = False
        db.commit()


def get_active_user_sessions(user_id: int, db: Session) -> List[UserSession]:
    return db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.is_active == True,
        UserSession.expires_at > datetime.utcnow()
    ).all()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    jti = payload.get("jti")
    if not jti or jti in token_blocklist:
        raise HTTPException(status_code=401, detail="Token has been revoked")

    session = db.query(UserSession).filter(
        UserSession.session_token == jti,
        UserSession.is_active == True,
        UserSession.expires_at > datetime.utcnow(),
    ).first()
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or revoked")

    session.last_activity = datetime.utcnow()
    db.commit()

    identity = payload.get("sub")
    user_id = _identity_to_user_id(identity)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


jwt_required = get_current_user
admin_required = require_admin


def get_jwt_identity(request: Request) -> Optional[str]:
    try:
        token = _extract_bearer(request)
        if token:
            payload = _decode_token(token)
            return payload.get("sub")
    except HTTPException:
        return None
    except Exception as exc:
        logger.debug("get_jwt_identity: unexpected error: %s", exc)
        return None
    return None


@auth_bp.post("/register")
async def register(request: Request, db: Session = Depends(get_db)):
    client_ip = _get_client_ip(request)
    if not _register_limiter.is_allowed(client_ip):
        _log_security("RATE_LIMITED", f"Register rate limit exceeded from {client_ip}", ip_address=client_ip)
        return JSONResponse({"error": "Too many registration attempts. Please try again later."}, status_code=429)
    logger.info("Registration attempt from %s", client_ip)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not username or len(username) < 3 or len(username) > 20 or not re.match(r"^[a-zA-Z0-9_]+$", username):
        return JSONResponse({"error": "Username must be 3-20 characters, letters/numbers/underscores only"}, status_code=400)

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return JSONResponse({"error": "Valid email address required"}, status_code=400)

    err = _validate_password(password)
    if err:
        return JSONResponse({"error": err}, status_code=400)

    try:
        if db.query(User).filter(User.username == username).first():
            return JSONResponse({"error": "Username already exists"}, status_code=409)

        if db.query(User).filter(User.email == email).first():
            return JSONResponse({"error": "Email already registered"}, status_code=409)

        from .models import Role
        analyst_role = db.query(Role).filter(Role.name == "analyst").first()
        user = User(
            username=username,
            email=email,
            role="analyst",
            role_id=analyst_role.id if analyst_role else None,
        )
        user.set_password(password)
        db.add(user)
        db.commit()
        db.refresh(user)

        try:
            AuditLog.log(
                action="user_registered",
                user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
                ip_address=_get_client_ip(request),
                user_agent=request.headers.get("User-Agent", "")[:500],
                db=db,
            )
        except Exception as audit_exc:
            logger.warning("AuditLog write failed on register: %s", audit_exc)

        session_token = create_user_session(user.id, request, db)
        access_token = create_access_token(str(user.id), jti=session_token)
        refresh_jti = str(uuid.uuid4())
        refresh_token = create_refresh_token(str(user.id), jti=refresh_jti)

        role_name = user.role
        try:
            if user.role_obj:
                role_name = user.role_obj.name
        except Exception as role_exc:
            logger.debug("Could not resolve role_obj on register: %s", role_exc)

        permissions = []
        try:
            permissions = user.get_all_permissions()
        except Exception as perm_exc:
            logger.debug("Could not get permissions on register: %s", perm_exc)

        resp = JSONResponse(
            {
                "success": True,
                "user": user.to_dict(),
                "access_token": access_token,
                "refresh_token": refresh_token,
                "permissions": permissions,
                "role": role_name,
            },
            status_code=201,
        )
        _set_auth_cookies(resp, access_token, refresh_token, session_token)
        logger.info("User '%s' registered successfully from %s", username, _get_client_ip(request))
        return resp

    except Exception as e:
        logger.error("Registration error for '%s': %s", username, e, exc_info=True)
        db.rollback()
        return JSONResponse({"error": "Registration failed. Please try again."}, status_code=500)


def _validate_password(password: str) -> str:
    if not password or len(password) < 8:
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


@auth_bp.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    client_ip = _get_client_ip(request)
    if not _login_limiter.is_allowed(client_ip):
        _log_security("RATE_LIMITED", f"Login rate limit exceeded from {client_ip}", ip_address=client_ip)
        return JSONResponse({"error": "Too many login attempts. Please try again later."}, status_code=429)
    logger.info("Login attempt from %s", client_ip)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return JSONResponse({"error": "Username and password required"}, status_code=400)

    try:
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.check_password(password):
            logger.warning("Login failed: invalid credentials for '%s' from %s", username, client_ip)
            _log_security("LOGIN_FAILED", f"Invalid credentials for '{username}'", ip_address=client_ip)
            try:
                AuditLog.log(
                    action="login_failed",
                    resource_type="user",
                    details=f"Failed login for '{username}'",
                    ip_address=client_ip,
                    user_agent=request.headers.get("User-Agent", "")[:500],
                    db=db,
                )
            except Exception as audit_exc:
                logger.warning("AuditLog write failed on login_failed: %s", audit_exc)
            return JSONResponse({"error": "Invalid credentials"}, status_code=401)

        if not user.is_active:
            return JSONResponse({"error": "Account is disabled"}, status_code=403)

        session_token = create_user_session(user.id, request, db)
        user.last_login = datetime.utcnow()
        db.commit()

        access_token = create_access_token(str(user.id), jti=session_token)
        refresh_jti = str(uuid.uuid4())
        refresh_token = create_refresh_token(str(user.id), jti=refresh_jti)

        try:
            AuditLog.log(
                action="login",
                user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
                ip_address=client_ip,
                user_agent=request.headers.get("User-Agent", "")[:500],
                db=db,
            )
        except Exception as audit_exc:
            logger.warning("AuditLog write failed on login: %s", audit_exc)

        role_name = user.role
        try:
            if user.role_obj:
                role_name = user.role_obj.name
        except Exception as role_exc:
            logger.debug("Could not resolve role_obj on login: %s", role_exc)

        permissions = []
        try:
            permissions = user.get_all_permissions()
        except Exception as perm_exc:
            logger.debug("Could not get permissions on login: %s", perm_exc)

        resp = JSONResponse({
            "success": True,
            "user": user.to_dict(),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "permissions": permissions,
            "role": role_name,
        })
        _set_auth_cookies(resp, access_token, refresh_token, session_token)
        logger.info("User '%s' logged in from %s", username, client_ip)
        return resp

    except Exception as e:
        logger.error("Login error for '%s': %s", username, e, exc_info=True)
        db.rollback()
        return JSONResponse({"error": "Login failed. Please try again."}, status_code=500)


@auth_bp.post("/refresh")
async def refresh(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("refresh_token_cookie") or (
        request.headers.get("Authorization", "")[7:]
        if request.headers.get("Authorization", "").startswith("Bearer ")
        else None
    )
    if not token:
        return JSONResponse({"error": "No refresh token"}, status_code=401)

    try:
        payload = _decode_token(token)
    except HTTPException:
        return JSONResponse({"error": "Invalid refresh token"}, status_code=401)

    if payload.get("type") != "refresh":
        return JSONResponse({"error": "Invalid token type"}, status_code=401)

    jti = payload.get("jti")
    if jti and jti in token_blocklist:
        return JSONResponse({"error": "Token has been revoked"}, status_code=401)

    identity = payload.get("sub")
    user_id = _identity_to_user_id(identity)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        return JSONResponse({"error": "User not found or inactive"}, status_code=401)

    new_session_token = create_user_session(user.id, request, db)
    new_access = create_access_token(identity, jti=new_session_token)
    resp = JSONResponse({"success": True, "access_token": new_access})
    resp.set_cookie(
        "access_token_cookie", new_access,
        httponly=True, secure=_SECURE_COOKIES, samesite="strict",
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    )
    return resp


@auth_bp.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    token = _extract_bearer(request)
    if token:
        try:
            payload = _decode_token(token)
            jti = payload.get("jti")
            if jti:
                token_blocklist.add(jti)
                revoke_user_session(jti, db)
        except HTTPException:
            pass
        except Exception as exc:
            logger.warning("Logout token revoke error: %s", exc)

    try:
        AuditLog.log(
            action="logout",
            user_id=current_user.id,
            ip_address=_get_client_ip(request),
            db=db,
        )
    except Exception as audit_exc:
        logger.warning("AuditLog write failed on logout: %s", audit_exc)

    resp = JSONResponse({"success": True, "message": "Logged out"})
    resp.delete_cookie("access_token_cookie", samesite="strict")
    resp.delete_cookie("refresh_token_cookie", samesite="strict")
    resp.delete_cookie("session_token", samesite="strict")
    return resp


@auth_bp.get("/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    try:
        role_name = current_user.role
        try:
            if current_user.role_obj:
                role_name = current_user.role_obj.name
        except Exception as role_exc:
            logger.debug("Could not resolve role_obj in /me: %s", role_exc)

        permissions = []
        try:
            permissions = current_user.get_all_permissions()
        except Exception as perm_exc:
            logger.debug("Could not get permissions in /me: %s", perm_exc)

        return JSONResponse({
            "success": True,
            "user": current_user.to_dict(),
            "permissions": permissions,
            "role": role_name,
        })
    except Exception as e:
        logger.error("/me endpoint error: %s", e, exc_info=True)
        return JSONResponse({"error": "Failed to retrieve user info"}, status_code=500)


@auth_bp.get("/users")
async def list_users(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return JSONResponse({"success": True, "users": [u.to_dict() for u in users]})


@auth_bp.put("/users/{user_id}")
async def update_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse({"error": "User not found"}, status_code=404)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    allowed_roles = {"admin", "investigator", "analyst", "viewer"}
    if "role" in data:
        if data["role"] not in allowed_roles:
            return JSONResponse({"error": f"Invalid role. Must be one of: {', '.join(sorted(allowed_roles))}"}, status_code=400)
        user.role = data["role"]
    if "is_active" in data:
        user.is_active = bool(data["is_active"])
    db.commit()
    db.refresh(user)

    try:
        AuditLog.log(
            action="user_updated",
            user_id=current_user.id,
            resource_type="user",
            resource_id=str(user_id),
            details=f"Updated fields: {list(data.keys())}",
            ip_address=_get_client_ip(request),
            db=db,
        )
    except Exception as audit_exc:
        logger.warning("AuditLog write failed on user update: %s", audit_exc)

    return JSONResponse({"success": True, "user": user.to_dict()})

@auth_bp.get("/sessions")
async def list_sessions(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        sessions = db.query(UserSession).filter(
            UserSession.is_active == True,
            UserSession.expires_at > datetime.utcnow()
        ).all()
        
        session_list = []
        for s in sessions:
            user = db.query(User).filter(User.id == s.user_id).first()
            if user:
                session_list.append({
                    "id": s.id,
                    "session_token": s.session_token,
                    "username": user.username,
                    "role": user.role,
                    "ip_address": s.ip_address,
                    "last_activity": s.last_activity.isoformat() if s.last_activity else s.created_at.isoformat(),
                    "user_agent": s.user_agent
                })
                
        return JSONResponse({"success": True, "sessions": session_list})
    except Exception as e:
        logger.error(f"Error listing sessions: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)

@auth_bp.post("/revoke-session")
async def revoke_session(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    try:
        data = await request.json()
        session_token = data.get("session_token")
        
        if not session_token:
            return JSONResponse({"success": False, "error": "Missing session_token"}, status_code=400)
            
        session = db.query(UserSession).filter(UserSession.session_token == session_token).first()
        if not session:
            return JSONResponse({"success": False, "error": "Session not found"}, status_code=404)
            
        session.is_active = False
        db.commit()
        
        # Add to blocklist for immediate stateless invalidation
        token_blocklist.add(session_token)
        
        return JSONResponse({"success": True, "message": "Session revoked"})
    except Exception as e:
        logger.error(f"Error revoking session: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@auth_bp.post("/password-change")
@auth_bp.put("/password-change")
async def update_profile(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    old_password = data.get("old_password")
    new_password = data.get("new_password")

    if new_password:
        logger.info("Password change attempt by user '%s'", current_user.username)
        if not old_password:
            return JSONResponse({"error": "Old password required"}, status_code=400)
        if not current_user.check_password(old_password):
            return JSONResponse({"error": "Incorrect old password"}, status_code=401)

        err = _validate_password(new_password)
        if err:
            return JSONResponse({"error": err}, status_code=400)

        current_user.set_password(new_password)
        db.commit()

        try:
            AuditLog.log(
                action="password_updated",
                user_id=current_user.id,
                resource_type="user",
                resource_id=str(current_user.id),
                ip_address=_get_client_ip(request),
                user_agent=request.headers.get("User-Agent", "")[:500],
                db=db,
            )
        except Exception as audit_exc:
            logger.warning("AuditLog write failed on password change: %s", audit_exc)

        return JSONResponse({"success": True, "message": "Password updated successfully"})

    return JSONResponse({"success": True, "message": "No updates performed"})


def init_jwt(app=None):
    pass
