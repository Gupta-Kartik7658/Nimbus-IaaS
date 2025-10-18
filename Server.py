# region -----------Imports-------
import os
import time
import json
from sqlalchemy import select  # <-- ADD THIS IMPORT
import subprocess
from pathlib import Path
from shutil import rmtree
from typing import List, Set, Literal, Optional
from contextlib import asynccontextmanager
import asyncio
from asyncio import Lock  # <-- IMPORTANT
import psutil
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

# --- NEW IMPORTS ---
from database import get_async_db, engine, async_session_factory
from models import Base, User, VM
from auth import auth_backend, fastapi_users, current_active_user
from crud import (
    get_vm_by_name,
    get_user_vm_by_name,
    get_vms_for_user,
    get_all_used_ips,
    get_all_used_ports,
)
from fastapi_users.schemas import UserRead, UserCreate
 
# endregion



#region -------------Directory and File Paths--------
BASE_DIR = Path(__file__).parent
VMS_DIR = BASE_DIR / ".vms"
SSH_DIR = BASE_DIR / ".ssh"


FRP_DIR = BASE_DIR / "frp_0.59.0_windows_amd64"  # Adjust this path as needed
FRP_EXECUTABLE_PATH = FRP_DIR / "frpc.exe" # Or "frpc" on Linux/macOS
FRP_CONFIG_PATH = FRP_DIR / "frpc.toml"
frpc_process = None 
RESOURCE_LOCK = asyncio.Lock()  # <-- NEW: Lock for resource allocation
#endregion



#region --------Lifespan and Process Management--------
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    if not FRP_CONFIG_PATH.exists():
        raise FileNotFoundError(f"CRITICAL: {FRP_CONFIG_PATH} not found.")
    if not FRP_EXECUTABLE_PATH.exists():
        raise FileNotFoundError(f"CRITICAL: frpc executable not found at {FRP_EXECUTABLE_PATH}")
    start_frpc()
    
    yield
    
    # Code to run on shutdown
    print("Shutting down server...")
    stop_frpc()

app = FastAPI(
    title="Nimbus-IaaS Controller",
    description="An API to manage local VMs and their frp tunnels.",
    lifespan=lifespan
)
# NEW: Add the CORS middleware configuration
# This tells the backend to accept requests from your React app's origin
origins = [
    "http://localhost:5173", # The address of your React frontend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)


app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

# This one line creates /auth/register
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)


#endregion



#region ---- Model Definitions -------
class InboundRule(BaseModel):
    type: Literal["http", "tcp","ssh","udp","icmp"]
    vm_port: int
    description: Optional[str] = ""
    
# --- NEW: Modified AddRuleBody ---
class AddRuleBody(BaseModel):
    vm_name: str  # Changed from 'username'
    description: str

class VirtualMachine(BaseModel):
    username: str  # This will now be the 'vm_name'
    key_name: str
    ram: int
    cpu: int
    image: str
    inbound_rules: List[InboundRule] = [InboundRule(type="tcp", vm_port=22, description="SSH Access")]
    provisioning_script: Optional[str] = None
#endregion
    
    
    
#region --- SSH Key Management ---
@app.post("/generate-key/{key_name}")
def generate_key(key_name: str):
    try:
        if not key_name.isalnum() or " " in key_name:
            raise HTTPException(status_code=400, detail="Key name must be alphanumeric and contain no spaces.")

        SSH_DIR.mkdir(exist_ok=True)
        private_key_path = SSH_DIR / key_name

        if private_key_path.exists():
            raise HTTPException(status_code=400, detail=f"Key '{key_name}' already exists.")

        command = ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", str(private_key_path), "-N", "", "-C", key_name]

        subprocess.run(command, check=True, capture_output=True, text=True)
        private_key_path.chmod(0o600)

        return {"message": f"SSH key '{key_name}' generated successfully.", "download_path": f"/download/{key_name}"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"SSH keygen failed: {e.stderr.strip()}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{key_name}")
async def download_key(key_name: str):
    private_key_path = SSH_DIR / key_name
    if not private_key_path.exists():
        raise HTTPException(status_code=404, detail=f"Key '{key_name}' does not exist.")
    return FileResponse(path=private_key_path, filename=key_name, media_type='application/octet-stream')

@app.get("/list-keys/")
async def download_key():
    keys = []
    for i in SSH_DIR.glob("*"):
        if(i.suffix == ".pub"):
            keys.append(i.name)
    return keys

#endregion



#region --- Vagrantfile Generation ---
def get_vagrantfile_content(vm: VirtualMachine, private_ip: str) -> str:
    pub_key_path = SSH_DIR / f"{vm.key_name}.pub"
    if not pub_key_path.exists():
        raise FileNotFoundError(f"Public key file not found: {pub_key_path}")

    # This ensures the path is correctly formatted for Vagrant
    pub_key_path_str = str(pub_key_path).replace("\\", "/")

    # --- Prepare the custom provisioning script to be injected ---
    custom_script_injection = ""
    if vm.provisioning_script:
        custom_script_injection = f"""
    echo "--- Running Custom User Provisioning Script ---"
    # Run the custom script as the new user for better isolation and security
    sudo -i -u {vm.username} bash <<'EOF'
{vm.provisioning_script}
EOF
    echo "--- Custom Script Finished ---"
"""

    return f"""
Vagrant.configure("2") do |config|
    NEW_USERNAME = "{vm.username}"

    config.vm.box = "{vm.image}"
    config.vm.network "private_network", ip: "{private_ip}"
    config.vm.hostname = "{vm.username}"

    config.vm.provider "virtualbox" do |vb|
        vb.memory = "{vm.ram}"
        vb.cpus = "{vm.cpu}"
    end

    config.ssh.insert_key = false

    config.vm.provision "file", source: "{pub_key_path_str}", destination: "/tmp/user_public_key.pub"

    # --- THIS IS THE CORRECTED BLOCK ---
    config.vm.provision "shell", privileged: true, inline: <<-SHELL
        set -x # Enable debugging output

        NEW_USERNAME="{vm.username}"
        echo "Provisioning VM with user '$NEW_USERNAME'..."

        # 1. Create the user
        useradd --create-home --shell /bin/bash "$NEW_USERNAME"

        # 2. Grant Passwordless Sudo (Universal Method)
        if command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then
            usermod -aG wheel "$NEW_USERNAME"
            sed -i 's/^Defaults.*requiretty/#&/' /etc/sudoers
            if ! grep -q '^%wheel ALL=(ALL) NOPASSWD: ALL' /etc/sudoers; then
                echo '%wheel ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers
            fi
        elif command -v apt-get >/dev/null 2>&1; then
            usermod -aG sudo "$NEW_USERNAME"
            echo "$NEW_USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$NEW_USERNAME
            chmod 440 /etc/sudoers.d/$NEW_USERNAME
        fi

        # 3. Setup SSH key for the new user
        mkdir -p /home/$NEW_USERNAME/.ssh
        cat /tmp/user_public_key.pub > /home/$NEW_USERNAME/.ssh/authorized_keys
        chown -R $NEW_USERNAME:$NEW_USERNAME /home/$NEW_USERNAME/.ssh
        chmod 700 /home/$NEW_USERNAME/.ssh
        chmod 600 /home/$NEW_USERNAME/.ssh/authorized_keys

        # 4. Restart SSH daemon (AFTER provisioning)
        systemctl restart sshd || systemctl restart ssh

        echo "--- Base Provisioning Complete ---"

        # 5. Inject and run the custom user script
        {custom_script_injection}
    SHELL
end
"""
#endregion



#region --- Vagrant and VM Management ---
def stream_vagrant_up(vm_path: str):
    try:
        process = subprocess.Popen(["vagrant", "up"], cwd=vm_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(f"[VAGRANT]: {line}", end="")
        process.wait()
        print(f"[INFO] Vagrant exited with code: {process.returncode}")
    except Exception as e:
        print(f"[ERROR] Exception during Vagrant up: {e}")

def stream_vagrant_halt(vm_path: str):
    try:
        process = subprocess.Popen(["vagrant", "halt"], cwd=vm_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(f"[VAGRANT HALT]: {line}", end="")
        process.wait()
        print(f"[INFO] Vagrant halt exited with code: {process.returncode}")
    except Exception as e:
        print(f"[ERROR] Exception during Vagrant halt: {e}")
        
        
        
# --- NEW: delete_vm_background (MUST be async) ---
async def delete_vm_background(vm_id: int):
    """
    Fully self-contained background task to delete a VM and all its resources.
    It creates its own database session.
    """
    print(f"[BG Task] Starting deletion for VM ID: {vm_id}")
    async with async_session_factory() as db:
        try:
            # 1. Fetch the VM from the DB
            # --- (Your DB fetch logic is correct) ---
            result = await db.execute(select(VM).where(VM.id == vm_id)) # You were missing 'select'
            vm_to_delete = result.scalars().first()
            
            if not vm_to_delete:
                # ... (your log is correct) ...
                return

            vm_name = vm_to_delete.name
            vm_path = VMS_DIR / vm_name
            
            # 2. Destroy Vagrant VM
            # --- (Your vagrant/rmtree logic is correct) ---
            if vm_path.exists():
                destroy_proc = subprocess.run(["vagrant", "destroy", "-f"], cwd=vm_path, capture_output=True, text=True)
                if destroy_proc.returncode != 0:
                    print(f"Warning: Vagrant destroy failed for {vm_name}. Error: {destroy_proc.stderr.strip()}")
                rmtree(vm_path)
            
            # 3. Clean up AWS and frpc.toml
            proxy_names_to_delete = set()
            for rule in vm_to_delete.inbound_rules:
                if "remotePort" in rule:
                    proxy_names_to_delete.add(f"{vm_name}-{rule['vm_port']}")
                    remove_inbound_security_rule(port=rule["remotePort"])
            
            if proxy_names_to_delete:
                # --- THIS IS THE FIX ---
                # Run the blocking file I/O in a separate thread
                await asyncio.to_thread(
                    _remove_proxies_from_config, 
                    proxy_names_to_delete
                )
                # --- END FIX ---
                print(f"Removed proxies for '{vm_name}' from frpc.toml")
            
            # 4. Delete from Database
            # --- (Your DB delete logic is correct) ---
            await db.delete(vm_to_delete)
            await db.commit()
            
            print(f"[BG Task] Successfully deleted VM {vm_name} (ID: {vm_id}).")
            
            # 5. Reload frpc (Run as a sync command)
            execute_frpc_reload()

        except Exception as e:
            # ... (your exception logic is correct) ...
            print(f"[BG Task ERROR] Failed to delete VM ID {vm_id}: {e}")
            await db.rollback()
#endregion



#region --- IP and Port Management ---
def find_ip_from_set(used_ips: set[str], base_ip="192.168.56.", start=11, end=250):
    for i in range(start, end):
        candidate = f"{base_ip}{i}"
        if candidate not in used_ips:
            return candidate
    raise Exception("No available IP addresses in range.")

def find_port_from_set(all_used_ports: set[int], start=2222, end=3000):
    for port in range(start, end):
        if port not in all_used_ports:
            return port
    raise Exception("No available remote ports for tunnels.")
#endregion



#region --- AWS Security Group Management ---
EC2_CLIENT = boto3.client("ec2", region_name="ap-south-1") # Use your region
SECURITY_GROUP_ID = "sg-0b0cb6352cf1c28be" # <-- IMPORTANT: Replace with your actual Security Group ID

def add_inbound_security_rule(port: int, description: str):
    """Adds an inbound rule to the AWS Security Group."""
    try:
        print(f"AWS: Authorizing inbound traffic on port {port}...")
        EC2_CLIENT.authorize_security_group_ingress(
            GroupId=SECURITY_GROUP_ID,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": port,
                    "ToPort": port,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": description}],
                },
            ],
        )
        print(f"AWS: Successfully opened port {port}.")
        return True
    except ClientError as e:
        # This error code means the rule already exists, which is fine.
        if e.response["Error"]["Code"] == "InvalidPermission.Duplicate":
            print(f"AWS: Rule for port {port} already exists.")
            return True
        else:
            print(f"AWS: Error adding rule for port {port}: {e}")
            return False

def remove_inbound_security_rule(port: int):
    """Removes an inbound rule from the AWS Security Group."""
    try:
        print(f"AWS: Revoking inbound traffic on port {port}...")
        EC2_CLIENT.revoke_security_group_ingress(
            GroupId=SECURITY_GROUP_ID,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": port,
                    "ToPort": port,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
            ],
        )
        print(f"AWS: Successfully closed port {port}.")
        return True
    except ClientError as e:
        # This error means the rule was already gone, which is also fine.
        if e.response["Error"]["Code"] == "InvalidPermission.NotFound":
            print(f"AWS: Rule for port {port} was not found.")
            return True
        else:
            print(f"AWS: Error removing rule for port {port}: {e}")
            return False
#endregion    



#region --- FRPC Process Management Functions ---
def _append_proxies_to_config(proxy_toml_list: List[str]):
    """
    Appends a list of proxy definitions to the frpc.toml file.
    This is a blocking function intended to be run in a thread.
    """
    with open(FRP_CONFIG_PATH, "a") as f:
        for proxy_toml in proxy_toml_list:
            f.write(proxy_toml)

def _remove_proxies_from_config(proxy_names_to_delete: Set[str]):
    """
    Removes proxy sections from frpc.toml by name.
    This is a blocking function intended to be run in a thread.
    """
    with open(FRP_CONFIG_PATH, "r") as f:
        content = f.read()
    
    parts = content.split("\n[[proxies]]\n")
    server_config = parts[0]
    proxy_blocks = parts[1:]

    kept_blocks = []
    for block in proxy_blocks:
        if not any(f'name = "{name}"' in block for name in proxy_names_to_delete):
            kept_blocks.append(block)

    new_content = server_config
    if kept_blocks:
        new_content += "\n[[proxies]]\n" + "\n[[proxies]]\n".join(kept_blocks)
    
    with open(FRP_CONFIG_PATH, "w") as f:
        f.write(new_content)
def start_frpc():
    global frpc_process
    if frpc_process and psutil.pid_exists(frpc_process.pid):
        print("frpc is already running.")
        return
    print(f"Starting frpc with config: {FRP_CONFIG_PATH}")
    frpc_process = subprocess.Popen([str(FRP_EXECUTABLE_PATH), "-c", str(FRP_CONFIG_PATH)])
    print(f"frpc started successfully with PID: {frpc_process.pid}")

def stop_frpc():
    global frpc_process
    if not frpc_process or not psutil.pid_exists(frpc_process.pid):
        print("frpc is not running or PID not found.")
        return
    print(f"Stopping frpc process with PID: {frpc_process.pid}")
    try:
        p = psutil.Process(frpc_process.pid)
        p.terminate()
        p.wait(timeout=5)
    except psutil.NoSuchProcess:
        pass
    except psutil.TimeoutExpired:
        print("frpc did not terminate gracefully, killing it.")
        p.kill()
    print("frpc stopped.")
    frpc_process = None

# def reload_frpc_background(background_tasks: BackgroundTasks):
#     background_tasks.add_task(stop_frpc)
#     background_tasks.add_task(time.sleep, 1)
#     background_tasks.add_task(start_frpc)
    
    
def execute_frpc_reload():
    """Executes the frpc reload command."""
    if not frpc_process or not psutil.pid_exists(frpc_process.pid):
        print("frpc is not running, so not reloading. It will start on the next request or app start.")
        return

    print("Attempting to hot-reload frpc configuration...")
    try:
        # This command tells the running frpc process to reload its config
        reload_command = [str(FRP_EXECUTABLE_PATH), "reload", "-c", str(FRP_CONFIG_PATH)]
        result = subprocess.run(reload_command, capture_output=True, text=True)

        if result.returncode == 0:
            print("frpc reloaded successfully.")
        else:
            print(f"ERROR: frpc reload failed. Stderr: {result.stderr.strip()}")
            print("Please ensure the '[admin]' section is configured in frpc.toml.")

    except Exception as e:
        print(f"An exception occurred while trying to reload frpc: {e}")

def reload_frpc_background(background_tasks: BackgroundTasks):
    """Schedules a non-blocking frpc reload task."""
    # We add a tiny delay to ensure the file write has completed before reload.
    background_tasks.add_task(time.sleep, 1)
    background_tasks.add_task(execute_frpc_reload)
#endregion
    
    
    
#region  Vagrant commands and VM management endpoints
@app.get("/list-vms")
async def list_vms(current_user: User = Depends(current_active_user), db: AsyncSession = Depends(get_async_db)):
    """Returns the VMs for the CURRENT LOGGED-IN USER ONLY."""
    user_vms_data = await get_vms_for_user(db, current_user.id)
    # Convert SQLAlchemy models to dicts for JSON response
    return [vm.__dict__ for vm in user_vms_data]



@app.post('/add-inbound-rule/{port}')
async def add_inbound_rule(
    port: int, 
    body: AddRuleBody, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="Port must be between 1 and 65535.")

    new_proxy_toml = ""
    
    async with RESOURCE_LOCK:
        # Fetch VM and check ownership
        vm = await get_user_vm_by_name(db, body.vm_name, current_user.id)
        if not vm:
            raise HTTPException(status_code=403, detail="Forbidden: VM not found or you do not own it.")
        
        # Get all used ports from DB
        used_ports = await get_all_used_ports(db)
        remotePort = find_port_from_set(used_ports)
        
        current_rules = list(vm.inbound_rules) # Get a mutable copy
        for rule in current_rules:
            if rule.get("vm_port") == port:
                return {"message": f"Inbound rule for port {port} already exists."}
        
        # Add new rule to the list
        new_rule = {"type": "tcp", "vm_port": port, "description": body.description, "remotePort": remotePort}
        current_rules.append(new_rule)
        
        # Update the VM's JSON field and commit to DB
        vm.inbound_rules = current_rules
        db.add(vm)
        await db.commit()
        
        # Add AWS rule
        success = add_inbound_security_rule(remotePort, description=body.description)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add AWS rule.")
            # Note: A true rollback would remove the rule from the DB here.

        # Add to frpc.toml
        proxy_name = f"{vm.name}-{port}" # Use vm.name
        new_proxy_toml = f"""
[[proxies]]
name = "{proxy_name}"
type = "tcp"
localIP = "{vm.private_ip}"
localPort = {port}
remotePort = {remotePort}
"""
        await asyncio.to_thread(_append_proxies_to_config, [new_proxy_toml])
        print(f"Appended proxy for '{vm.name}' to frpc.toml")

    reload_frpc_background(background_tasks)
    return {"message": f"Inbound rule for port {port} added successfully."}


@app.delete("/remove-inbound-rule/{vm_name}/{remote_port}")
async def remove_inbound_rule(
    vm_name: str, 
    remote_port: int, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    async with RESOURCE_LOCK:
        # --- (Your VM fetch and ownership check is correct) ---
        vm = await get_user_vm_by_name(db, vm_name, current_user.id)
        if not vm:
            raise HTTPException(status_code=403, detail="Forbidden: VM not found or you do not own it.")

        # --- (Your rule finding logic is correct) ---
        current_rules = list(vm.inbound_rules)
        rule_to_remove = None
        for rule in current_rules:
            if rule.get("remotePort") == remote_port:
                rule_to_remove = rule
                break

        if not rule_to_remove:
            raise HTTPException(status_code=404, detail=f"Rule with public port {remote_port} not found.")

        try:
            # 1. Remove from AWS
            remove_inbound_security_rule(port=remote_port)
            
            # 2. Remove from frpc.toml
            vm_port = rule_to_remove["vm_port"]
            proxy_name_to_delete = f"{vm.name}-{vm_port}"
            
            # --- THIS IS THE FIX ---
            await asyncio.to_thread(
                _remove_proxies_from_config,
                {proxy_name_to_delete}
            )
            # --- END FIX ---
            
            # 3. Remove from DB
            # --- (Your DB update logic is correct) ---
            current_rules.remove(rule_to_remove)
            vm.inbound_rules = current_rules
            db.add(vm)
            await db.commit()

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    
    reload_frpc_background(background_tasks)
    return {"message": f"Successfully removed rule for public port {remote_port}."}




#region --- Create VM Endpoint ---
# --- MODIFIED: /create-vm ---
@app.post("/create-vm")
async def create_vm(
    vm: VirtualMachine, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        vm_path = VMS_DIR / vm.username # vm.username is the 'vm_name'
        if vm_path.exists():
            raise HTTPException(status_code=400, detail=f"VM '{vm.username}' directory already exists.")
        if not (SSH_DIR / f"{vm.key_name}.pub").exists():
            raise HTTPException(status_code=400, detail=f"SSH key '{vm.key_name}' does not exist.")

        async with RESOURCE_LOCK:
            # Check if VM name is taken in DB
            existing_vm = await get_vm_by_name(db, vm.username)
            if existing_vm:
                raise HTTPException(status_code=400, detail=f"VM name '{vm.username}' is already taken.")
            
            # Get all used IPs from DB and find a new one
            used_ips = await get_all_used_ips(db)
            private_ip = find_ip_from_set(used_ips)
            
            # Get all used ports from DB
            used_ports = await get_all_used_ports(db)
            
            proxies_to_add = []
            vm_rules_list = [] # This will be stored in the DB
            
            for rule_pydantic in vm.inbound_rules:
                rule = rule_pydantic.model_dump()
                remotePort = find_port_from_set(used_ports)
                used_ports.add(remotePort) # Reserve it for this request
                
                # Add AWS rule
                add_inbound_security_rule(remotePort, f"Tunnel for {vm.username} port {remotePort}")
                
                rule["remotePort"] = remotePort
                vm_rules_list.append(rule)
                
                # Prepare frpc.toml entry
                proxy_name = f"{vm.username}-{rule['vm_port']}"
                new_proxy_toml = f"""
[[proxies]]
name = "{proxy_name}"
type = "tcp"
localIP = "{private_ip}"
localPort = {rule['vm_port']}
remotePort = {remotePort}
"""
                proxies_to_add.append(new_proxy_toml)
            
            # Create the new VM record in the DB
            new_vm_record = VM(
                name=vm.username,
                key_name=vm.key_name,
                ram=vm.ram,
                cpu=vm.cpu,
                image=vm.image,
                private_ip=private_ip,
                inbound_rules=vm_rules_list,
                owner_id=current_user.id  # CRITICAL: Link to user
            )
            db.add(new_vm_record)
            await db.commit()
            
            # Write all proxies to frpc.toml
            await asyncio.to_thread(_append_proxies_to_config, proxies_to_add)
            
            await db.refresh(new_vm_record) # Get the new VM's ID, etc.

        # --- Lock is released here ---
        
        vm_path.mkdir(exist_ok=True)
        vagrantfile_content = get_vagrantfile_content(vm, private_ip)
        with open(vm_path / "Vagrantfile", "w") as f:
            f.write(vagrantfile_content)

        background_tasks.add_task(stream_vagrant_up, str(vm_path))
        reload_frpc_background(background_tasks)

        ssh_port = vm_rules_list[0]['remotePort']
        return {"message": f"ssh -i {vm.key_name} {vm.username}@13.233.204.203 -p {ssh_port}"}

    except Exception as e:
        # DB changes will be rolled back by the 'Depends(get_async_db)' context
        raise HTTPException(status_code=500, detail=str(e))
# endregion



#region --- Delete VM Endpoint ---
@app.delete("/delete-vm/{vm_name}")
async def delete_vm(
    vm_name: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    # Fetch VM and check ownership
    vm_to_delete = await get_user_vm_by_name(db, vm_name, current_user.id)
    if not vm_to_delete:
        raise HTTPException(status_code=403, detail="Forbidden: VM not found or you do not own it.")
    
    # Pass the serializable VM ID to the background task
    background_tasks.add_task(delete_vm_background, vm_to_delete.id)
    
    return {"message": f"VM '{vm_name}' deletion scheduled."}
# endregion

#endregion


#region --- Start VM Endpoints ---
@app.post("/start-vm/{vm_name}")
async def start_vm(
    vm_name: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    vm = await get_user_vm_by_name(db, vm_name, current_user.id)
    if not vm:
        raise HTTPException(status_code=403, detail="Forbidden: VM not found or you do not own it.")
    
    vm_path = VMS_DIR / vm.name
    if not vm_path.exists():
        raise HTTPException(status_code=404, detail="VM directory not found.")
    
    background_tasks.add_task(stream_vagrant_up, str(vm_path))
    return {"message": f"VM '{vm.name}' is booting..."}
#endregion


#region --- Stop VM Endpoints ---
@app.post("/stop-vm/{vm_name}")
async def stop_vm(
    vm_name: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    vm = await get_user_vm_by_name(db, vm_name, current_user.id)
    if not vm:
        raise HTTPException(status_code=403, detail="Forbidden: VM not found or you do not own it.")

    vm_path = VMS_DIR / vm.name
    if not vm_path.exists():
        raise HTTPException(status_code=404, detail="VM directory not found.")
        
    # You should create a 'stream_vagrant_halt' function for this
    background_tasks.add_task(stream_vagrant_halt, str(vm_path))
    return {"message": f"VM '{vm.name}' is stopping."}
#endregion

#endregion