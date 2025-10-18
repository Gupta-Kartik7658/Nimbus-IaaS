from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select  # <-- IMPORT SELECT HERE TOO
from models import VM, User

async def get_vm_by_name(db: AsyncSession, vm_name: str) -> VM | None:
    """Fetches a single VM by its name."""
    result = await db.execute(select(VM).where(VM.name == vm_name))
    return result.scalars().first()

async def get_user_vm_by_name(db: AsyncSession, vm_name: str, user_id: str) -> VM | None:
    """Fetches a single VM by name, ONLY if it belongs to the specified user."""
    result = await db.execute(
        select(VM).where(VM.name == vm_name, VM.owner_id == user_id)
    )
    return result.scalars().first()

async def get_vms_for_user(db: AsyncSession, user_id: str) -> list[VM]:
    """Fetches all VMs owned by a specific user."""
    result = await db.execute(select(VM).where(VM.owner_id == user_id))
    return result.scalars().all()

async def get_all_used_ips(db: AsyncSession) -> set[str]:
    """Returns a set of all private_ip strings currently in the DB."""
    result = await db.execute(select(VM.private_ip))
    return set(result.scalars().all())

async def get_all_used_ports(db: AsyncSession) -> set[int]:
    """
    Returns a set of all remotePort integers currently in use.
    This queries the JSON field, so it's a bit more complex.
    """
    used_ports = set()
    result = await db.execute(select(VM.inbound_rules))
    
    # The result contains lists of rule-dictionaries
    for rules_list in result.scalars().all():
        if not rules_list:
            continue
        for rule in rules_list:
            if "remotePort" in rule:
                used_ports.add(rule["remotePort"])
    return used_ports