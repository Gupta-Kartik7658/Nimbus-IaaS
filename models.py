from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, JSON, ForeignKey, Text, UniqueConstraint
from sqlalchemy import Enum
import enum

# This is the base class for all your database tables
class Base(DeclarativeBase):
    pass

# This table comes from fastapi-users and handles all user/password logic
class User(SQLAlchemyBaseUserTableUUID, Base):
    pass

# This is your new VM table
class VMStatus(str, enum.Enum):
    provisioning = "Provisioning"
    starting = "Starting"
    active = "Active"
    stopping = "Stopping"
    stopped = "Stopped"
    deleting = "Deleting"
    error = "Error"
    
class VM(Base):
    __tablename__ = "vms"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # We use 'name' instead of 'username' for the VM identifier
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    
    key_name: Mapped[str] = mapped_column(String(100))
    ram: Mapped[int]
    cpu: Mapped[int]
    image: Mapped[str]
    private_ip: Mapped[str] = mapped_column(String(50), unique=True)
    
    # Store the list of rule objects directly as JSON
    inbound_rules: Mapped[dict] = mapped_column(JSON)
    status: Mapped[VMStatus] = mapped_column(
        Enum(VMStatus), default=VMStatus.provisioning, nullable=False
    )
    
    # This is the critical link back to the user who owns the VM
    owner_id: Mapped[str] = mapped_column(ForeignKey("user.id"))
    
class SSHKey(Base):
    __tablename__ = "ssh_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    
    # Use Text for potentially long key data
    public_key: Mapped[str] = mapped_column(Text)
    private_key: Mapped[str] = mapped_column(Text)
    
    # Foreign key to the user table
    owner_id: Mapped[str] = mapped_column(ForeignKey("user.id"))
    
    # Add a constraint to ensure a user cannot have two keys with the same name
    __table_args__ = (
        UniqueConstraint("name", "owner_id", name="uq_user_key_name"),
    )