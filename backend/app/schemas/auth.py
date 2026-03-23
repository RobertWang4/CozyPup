from pydantic import BaseModel


class AuthRequest(BaseModel):
    id_token: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str


class DevAuthRequest(BaseModel):
    name: str
    email: str = "dev@cozypup.app"


class FirebaseAuthRequest(BaseModel):
    id_token: str


class EmailRegisterRequest(BaseModel):
    email: str
    password: str
    name: str | None = None
    phone_number: str  # Required for email registration


class EmailLoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    auth_provider: str
    phone_number: str | None
