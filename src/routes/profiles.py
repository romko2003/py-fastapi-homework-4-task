from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from config import get_jwt_auth_manager
from database import get_db
from database.models.accounts import UserModel, UserGroupEnum, UserProfileModel
from schemas.profiles import ProfileCreateSchema, ProfileResponseSchema
from security.http import get_token  # твій helper з Bearer parsing
from security.interfaces import JWTAuthManagerInterface
from storages.interfaces import S3StorageInterface
from config.dependencies import get_s3_storage_client  # або звідки воно в тебе
from exceptions.storage import StorageError  # якщо є; якщо ні — прибери


router = APIRouter(prefix="/api/v1", tags=["Profiles"])


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    user_id: int,
    form_data_and_file: tuple[ProfileCreateSchema, object] = Depends(ProfileCreateSchema.from_form),
    token: str = Depends(get_token),
    db: Session = Depends(get_db),
    jwt: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
):
    data, avatar = form_data_and_file  # avatar: UploadFile

    # 1) Token validation (expired/invalid)
    try:
        payload = jwt.decode_access_token(token)  # <-- звір назву у своєму JWTAuthManager
    except Exception:
        # В ідеалі: розрізнити expired vs invalid якщо в тебе є специфічні ексепшени
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        )

    current_user_id = int(payload.get("user_id") or payload.get("sub") or 0)
    if not current_user_id:
        raise HTTPException(status_code=401, detail="Token has expired.")

    # 2) Current user existence/status
    current_user: UserModel | None = (
        db.query(UserModel)
        .filter(UserModel.id == current_user_id, UserModel.is_active.is_(True))
        .first()
    )
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active.",
        )

    # 3) Authorization rules
    is_admin = False
    # у тебе може бути current_user.group.name або current_user.group_id — підлаштуй під свою модель
    if getattr(current_user, "group", None) is not None:
        is_admin = current_user.group.name == UserGroupEnum.ADMIN
    if current_user_id != user_id and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this profile.",
        )

    # 4) Target user existence/status
    target_user: UserModel | None = (
        db.query(UserModel)
        .filter(UserModel.id == user_id, UserModel.is_active.is_(True))
        .first()
    )
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active.",
        )

    # 5) Check existing profile
    existing_profile = (
        db.query(UserProfileModel)
        .filter(UserProfileModel.user_id == user_id)
        .first()
    )
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile.",
        )

    # 6) Upload avatar to S3/MinIO
    avatar_url: str | None = None
    try:
        ext = (avatar.filename or "avatar").split(".")[-1].lower()
        key = f"avatars/{user_id}_{uuid4().hex}.{ext}"

        # ВАЖЛИВО: звір сигнатуру у твоєму S3StorageClient.
        # Часто це або upload_file(file=UploadFile, key=str)->str(url)
        # або put_object(bucket, key, bytes, content_type)->None + get_url(key)->str
        avatar_url = s3_client.upload_file(avatar, key)  # <-- підлаштуй під свій інтерфейс

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later.",
        )

    # 7) Create profile and store in DB
    profile = UserProfileModel(
        user_id=user_id,
        first_name=data.first_name.lower(),
        last_name=data.last_name.lower(),
        gender=data.gender,
        date_of_birth=data.date_of_birth,
        info=data.info,
        avatar=avatar_url,
    )

    try:
        db.add(profile)
        db.commit()
        db.refresh(profile)
    except SQLAlchemyError:
        db.rollback()
        raise

    return profile
