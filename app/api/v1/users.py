from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import notifications as notifications_routes
from app.database import get_db
from app.models.entities import User
from app.schemas.users import UserCreate, UserRead, UserUpdate
from app.security import hash_password
from app.services.users import delete_user, update_user

router = APIRouter(prefix="/users", tags=["users"])
router.include_router(notifications_routes.router)


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


@router.post("", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="El email ya está registrado")

    user = User(
        nombre=payload.nombre,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: UUID, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


@router.patch("/{user_id}", response_model=UserRead)
def patch_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    update_user(db, user, payload)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def remove_user(user_id: UUID, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    delete_user(db, user)
    db.commit()
