from pydantic import BaseModel


class UserPreferences(BaseModel):
    size: str | None = None
    favorite_color: str | None = None
    style: str | None = None


class User(BaseModel):
    id: int
    username: str
    preferences: UserPreferences = UserPreferences()


class UserProfileUpdate(BaseModel):
    preferences: UserPreferences
