from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import Form, UploadFile, File
from pydantic import BaseModel, Field, field_validator

from validation import (
    validate_name,
    validate_gender,
    validate_birth_date,
    validate_image,
)


class ProfileCreateSchema(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    gender: str
    date_of_birth: date
    info: str = Field(..., min_length=1)

    @field_validator("first_name")
    @classmethod
    def _validate_first_name(cls, v: str) -> str:
        return validate_name(v)

    @field_validator("last_name")
    @classmethod
    def _validate_last_name(cls, v: str) -> str:
        return validate_name(v)

    @field_validator("gender")
    @classmethod
    def _validate_gender(cls, v: str) -> str:
        return validate_gender(v)

    @field_validator("date_of_birth")
    @classmethod
    def _validate_birth_date(cls, v: date) -> date:
        return validate_birth_date(v)

    @field_validator("info")
    @classmethod
    def _validate_info(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Info cannot be empty.")
        return v.strip()

    @classmethod
    def from_form(  # dependency-friendly
        cls,
        first_name: str = Form(...),
        last_name: str = Form(...),
        gender: str = Form(...),
        date_of_birth: date = Form(...),
        info: str = Form(...),
        avatar: UploadFile = File(...),
    ) -> tuple["ProfileCreateSchema", UploadFile]:
        # Валідація файлу окремо (бо UploadFile не є “чистим” pydantic-типом)
        validate_image(avatar)
        return cls(
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            date_of_birth=date_of_birth,
            info=info,
        ), avatar


class ProfileResponseSchema(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: Optional[str] = None

    class Config:
        from_attributes = True
