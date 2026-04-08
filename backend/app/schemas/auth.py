from pydantic import BaseModel


class AuthRequest(BaseModel):
    id_token: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    email: str | None = None
    name: str | None = None
    auth_provider: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str


class DevAuthRequest(BaseModel):
    name: str
    email: str = "dev@cozypup.app"


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    auth_provider: str
    phone_number: str | None
