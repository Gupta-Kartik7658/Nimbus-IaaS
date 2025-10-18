import uuid
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_db
from models import User
import os
SECRET = os.environ.get("SECRET_KEY")


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
# This tells fastapi-users to look for the token in the "Authorization: Bearer ..." header
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")

def get_jwt_strategy() -> JWTStrategy:
    # This configures the JWT token itself
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600) # 1 hour expiry

# --- Authentication Backend ---
# This ties the transport (Bearer) and strategy (JWT) together
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# --- FastAPIUsers ---
# This is the main object that ties everything together
fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# --- Dependency ---
# This is the "magic" dependency you'll use in your endpoints
# to get the currently logged-in user.
current_active_user = fastapi_users.current_user(active=True)