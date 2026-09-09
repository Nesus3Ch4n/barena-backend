from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    nombre_completo: str = Field(min_length=2, max_length=120)

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10)

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class MeOut(BaseModel):
    id: str
    email: str
    nombre_completo: Optional[str]
    roles: List[str]
    created_at: datetime

class ReclamarIn(BaseModel):
    codigo: str = Field(min_length=8, max_length=8)
