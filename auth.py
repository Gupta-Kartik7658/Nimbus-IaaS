import uuid
from dotenv import load_dotenv
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

# --- NEW IMPORTS ---
from fastapi_users import schemas  # <-- THIS IS THE CORRECT IMPORT
# --- END NEW IMPORTS ---

from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_db
from models import User
import os

#
# !! WARNING: DO NOT USE THIS IN PRODUCTION !!
#
# Create a real secret key using: openssl rand -hex 32
# Store it in an environment variable (e.g., os.environ.get("SECRET_KEY"))
#
load_dotenv()
# --- End loading ---


# --- 4. Retrieve the secret key ---
SECRET = os.environ.get("SECRET_KEY")
if SECRET is None:
    raise ValueError("SECRET_KEY not found in .env file. Please set it.")

# --- NEW SCHEMA DEFINITIONS ---
# These are the classes you were trying to import.
# We must define them ourselves.
# UserRead needs to be parameterized with the User's ID type (uuid.UUID)

class UserRead(schemas.BaseUser[uuid.UUID]):
    pass

class UserCreate(schemas.BaseUserCreate):
    pass

class UserUpdate(schemas.BaseUserUpdate):
    pass
# --- END NEW SCHEMA DEFINITIONS ---


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Request | None = None):
        print(f"User {user.id} has registered.")

async def get_user_db(session: AsyncSession = Depends(get_async_db)):
    yield SQLAlchemyUserDatabase(session, User)

async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)

# --- Bearer Token Transport ---
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600) # 1 hour expiry

# --- Authentication Backend ---
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# --- FastAPIUsers ---
fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# --- Dependency ---
current_active_user = fastapi_users.current_user(active=True)