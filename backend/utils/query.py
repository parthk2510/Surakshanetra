from sqlalchemy.orm import Session

ALL_PERMISSIONS = "*"


def owned_query(model, user, db: Session, allow_all: bool = False):
    q = db.query(model)
    if allow_all and ALL_PERMISSIONS in user.get_all_permissions():
        return q
    return q.filter(model.user_id == user.id)
