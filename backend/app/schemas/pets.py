from pydantic import BaseModel

from app.models import Species


class PetCreate(BaseModel):
    name: str
    species: Species
    breed: str = ""
    birthday: str | None = None  # YYYY-MM-DD
    weight: float | None = None


class PetUpdate(BaseModel):
    name: str | None = None
    species: Species | None = None
    breed: str | None = None
    birthday: str | None = None
    weight: float | None = None
    profile_md: str | None = None


class PetResponse(BaseModel):
    id: str
    name: str
    species: Species
    breed: str
    birthday: str | None
    weight: float | None
    avatar_url: str
    color_hex: str
    profile_md: str | None = None
    created_at: str
