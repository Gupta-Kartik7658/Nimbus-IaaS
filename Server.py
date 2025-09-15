# region -----------Imports-------
import os
import time
import json
import subprocess
from pathlib import Path
from shutil import rmtree
from typing import List, Set, Literal, Optional
from contextlib import asynccontextmanager
import psutil
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
from fastapi.middleware.cors import CORSMiddleware
 
# endregion



#region -------------Directory and File Paths--------
BASE_DIR = Path(__file__).parent
VMS_DIR = BASE_DIR / ".vms"
SSH_DIR = BASE_DIR / ".ssh"
REGISTRY_FILE = VMS_DIR / "registry.json"

FRP_DIR = BASE_DIR / "frp_0.59.0_windows_amd64"  # Adjust this path as needed
FRP_EXECUTABLE_PATH = FRP_DIR / "frpc.exe" # Or "frpc" on Linux/macOS
FRP_CONFIG_PATH = FRP_DIR / "frpc.toml"
frpc_process = None # Global variable to hold the frpc process
#endregion



#region --------Lifespan and Process Management--------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    if not FRP_CONFIG_PATH.exists():
        raise FileNotFoundError(f"CRITICAL: {FRP_CONFIG_PATH} not found.")
    if not FRP_EXECUTABLE_PATH.exists():
        raise FileNotFoundError(f"CRITICAL: frpc executable not found at {FRP_EXECUTABLE_PATH}")
    start_frpc()
    
    yield # The application runs
    
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
    "http://localhost:3000", # A common alternative for React dev servers
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)


#endregion



#region ---- Model Definitions -------
class InboundRule(BaseModel):
    type: Literal["http", "tcp","ssh","udp","icmp"]
    vm_port: int
    description: Optional[str] = ""
    
# 1. NEW: Add this Pydantic model for the request body
class AddRuleBody(BaseModel):
    username: str
    description: str


class VirtualMachine(BaseModel):
    username: str
    key_name: str
    ram: int
    cpu: int
    image: str
    inbound_rules: List[InboundRule] = [InboundRule(type="tcp", vm_port=22, description="SSH Access")]
    provisioning_script: Optional[str] = None
#endregion
    
    
    
#region --- SSH Key Management ---
@app.post("/generate-key/{key_name}")
async def generate_key(key_name: str):
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

def load_vm_registry():
    if not REGISTRY_FILE.exists():
        return {}
    with open(REGISTRY_FILE, "r") as f:
        return json.load(f)

def save_vm_registry(registry):
    VMS_DIR.mkdir(exist_ok=True)
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=4)

#endregion



#region --- IP and Port Management ---
def find_ip(base_ip="192.168.56.", start=11, end=250):
    registry = load_vm_registry()
    used_ips = {vm.get("private_ip") for vm in registry.values()}
    for i in range(start, end):
        candidate = f"{base_ip}{i}"
        if candidate not in used_ips:
            return candidate
    raise Exception("No available IP addresses in range.")

def find_available_remotePort(exclude_ports: Set[int] = None, start=2222, end=3000):
    if exclude_ports is None:
        exclude_ports = set()
    
    registry = load_vm_registry()
    used_ports = set()
    for vm in registry.values():
        for rule in vm.get("inbound_rules", []):
            # --- THIS IS THE CORRECTED LINE ---
            if "remotePort" in rule:
                used_ports.add(rule["remotePort"])
    
    # Combine saved ports with ports assigned in the current request
    all_used_ports = used_ports.union(exclude_ports)

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

# Add this endpoint to your FastAPI python file

@app.get("/list-vms")
async def list_vms():
    """Returns the current VM registry."""
    registry = load_vm_registry()
    return registry


@app.post('/add-inbound-rule/{port}')
async def add_inbound_rule(port: int, body: AddRuleBody, background_tasks: BackgroundTasks):
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="Port must be between 1 and 65535.")

    registry = load_vm_registry()
    # Use body.username instead of username
    vm = registry.get(body.username)
    
    if not vm:
        # Use body.username instead of username
        raise HTTPException(status_code=404, detail=f"VM '{body.username}' not found in registry.")
    
    remotePort = find_available_remotePort()
    for rule in vm.get("inbound_rules", []):
        if rule.get("vm_port") == port:
            # Use body.username instead of username
            return {"message": f"Inbound rule for port {port} already exists for VM '{body.username}'."}
            
    vm["inbound_rules"].append({"type": "tcp", "vm_port": port, "description": body.description, "remotePort": remotePort})
    save_vm_registry(registry)
    # Use body.description instead of description
    success = add_inbound_security_rule(remotePort, description=body.description)
    
    # Use body.username instead of username
    proxy_name = f"{body.username}-{port}"
    new_proxy_toml = f"""
[[proxies]]
name = "{proxy_name}"
type = "tcp"
localIP = "{vm['private_ip']}"
localPort = {port}
remotePort = {remotePort}
"""

    with open(FRP_CONFIG_PATH, "a") as f:
        f.write(new_proxy_toml)
        # Use body.username instead of username
        print(f"Appended proxy for '{body.username}' to frpc.toml")
    reload_frpc_background(background_tasks)
    
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to add inbound rule for port {port}.")
    return {"message": f"Inbound rule for port {port} added successfully."}

# Add this endpoint to your FastAPI python file

@app.delete("/remove-inbound-rule/{username}/{remote_port}")
async def remove_inbound_rule(username: str, remote_port: int, background_tasks: BackgroundTasks):
    registry = load_vm_registry()
    
    # 1. Find the VM in the registry
    if username not in registry:
        raise HTTPException(status_code=404, detail=f"VM '{username}' not found.")
    
    vm_data = registry[username]
    
    # 2. Find the specific rule to remove by its remote_port
    rule_to_remove = None
    for rule in vm_data.get("inbound_rules", []):
        if rule.get("remotePort") == remote_port:
            rule_to_remove = rule
            break

    if not rule_to_remove:
        raise HTTPException(status_code=404, detail=f"Rule with public port {remote_port} not found for VM '{username}'.")

    # 3. Clean up resources associated with the rule
    try:
        # a. Remove the rule from the AWS security group
        remove_inbound_security_rule(port=remote_port)
        
        # b. Remove the proxy from the frpc.toml file
        vm_port = rule_to_remove["vm_port"]
        proxy_name_to_delete = f"{username}-{vm_port}"
        
        with open(FRP_CONFIG_PATH, "r") as f:
            lines = f.readlines()
        
        new_lines = []
        in_proxy_to_delete = False
        for line in lines:
            if f'name = "{proxy_name_to_delete}"' in line:
                in_proxy_to_delete = True
                continue # Skip the 'name' line
            if in_proxy_to_delete and line.strip() == "[[proxies]]":
                in_proxy_to_delete = False # We've reached the next proxy block
            
            if not in_proxy_to_delete:
                new_lines.append(line)
        
        # Clean up extra newlines that might result from the deletion
        cleaned_content = "".join(new_lines).replace("\n\n[[proxies]]", "\n[[proxies]]")

        with open(FRP_CONFIG_PATH, "w") as f:
            f.write(cleaned_content)
        
        # c. Remove the rule from the registry object
        vm_data["inbound_rules"].remove(rule_to_remove)
        save_vm_registry(registry)
        
        # d. Reload the frpc service to apply changes
        reload_frpc_background(background_tasks)

        return {"message": f"Successfully removed rule for public port {remote_port}."}
        
    except Exception as e:
        # If anything goes wrong, we should ideally roll back, but for now, we'll report the error.
        raise HTTPException(status_code=500, detail=f"An error occurred while removing the rule: {str(e)}")




#region --- Create VM Endpoint ---
@app.post("/create-vm")
async def create_vm(vm: VirtualMachine, background_tasks: BackgroundTasks):
    try:
        vm_path = VMS_DIR / vm.username
        if vm_path.exists():
            raise HTTPException(status_code=400, detail=f"VM '{vm.username}' already exists.")
        if not (SSH_DIR / f"{vm.key_name}.pub").exists():
            raise HTTPException(status_code=400, detail=f"SSH key '{vm.key_name}' does not exist. Generate it first.")

        private_ip = find_ip()
        registry = load_vm_registry()
        
        vm_data = vm.model_dump()
        vm_data["private_ip"] = private_ip
        
        proxies_to_add = []
        ## FIXED ## --- Logic to assign unique ports within the same request ---
        ports_assigned_in_this_request = set()
        for rule in vm_data["inbound_rules"]:
            remotePort = find_available_remotePort(exclude_ports=ports_assigned_in_this_request)
            add_inbound_security_rule(remotePort, f"Tunnel for {vm.username} on port {remotePort}")
            ports_assigned_in_this_request.add(remotePort)
            rule["remotePort"] = remotePort
            proxy_name = f"{vm.username}-{rule['vm_port']}"
            
            ## FIXED ## --- Changed remotePort to remotePort ---
            new_proxy_toml = f"""
[[proxies]]
name = "{proxy_name}"
type = "tcp"
localIP = "{private_ip}"
localPort = {rule['vm_port']}
remotePort = {remotePort}
"""
            proxies_to_add.append(new_proxy_toml)
        
        registry[vm.username] = vm_data
        save_vm_registry(registry)

        with open(FRP_CONFIG_PATH, "a") as f:
            for proxy_toml in proxies_to_add:
                f.write(proxy_toml)
        print(f"Appended {len(proxies_to_add)} proxies for '{vm.username}' to frpc.toml")

        vm_path.mkdir(exist_ok=True)
        vagrantfile_content = get_vagrantfile_content(vm, private_ip)
        with open(vm_path / "Vagrantfile", "w") as f:
            f.write(vagrantfile_content)

        background_tasks.add_task(stream_vagrant_up, str(vm_path))
        reload_frpc_background(background_tasks)

        return {"message": f"You will now be able to SSH into your Nimbus-VM using ssh -i {vm.key_name} {vm.username}@13.233.204.203 -p {registry[vm.username]['inbound_rules'][0]['remotePort']}"}

    except Exception as e:
        registry = load_vm_registry()
        if vm.username in registry:
            del registry[vm.username]
            save_vm_registry(registry)
        raise HTTPException(status_code=500, detail=str(e))

#endregion


#region --- Delete VM Endpoint ---
@app.delete("/delete-vm/{username}")
async def delete_vm(username: str, background_tasks: BackgroundTasks):
    try:
        vm_path = VMS_DIR / username
        if not vm_path.exists():
            raise HTTPException(status_code=404, detail=f"VM '{username}' does not exist.")

        destroy_proc = subprocess.run(["vagrant", "destroy", "-f"], cwd=vm_path, capture_output=True, text=True)
        if destroy_proc.returncode != 0:
            print(f"Warning: Vagrant destroy failed for {username}, but proceeding with cleanup. Error: {destroy_proc.stderr.strip()}")

        rmtree(vm_path)
        
        registry = load_vm_registry()
        if username in registry:
            vm_to_delete = registry[username]
            proxy_names_to_delete = {f"{username}-{rule['vm_port']}" for rule in vm_to_delete.get("inbound_rules", [])}
            
            for rule in vm_to_delete.get("inbound_rules", []):
                if "remotePort" in rule:
                    remove_inbound_security_rule(port=rule["remotePort"])
                    print(f"Removed AWS security group rule for port {rule['remotePort']}")
            
            if proxy_names_to_delete:
                with open(FRP_CONFIG_PATH, "r") as f:
                    content = f.read()
                
                # The first part is the server config, the rest are proxy blocks
                parts = content.split("\n[[proxies]]\n")
                server_config = parts[0]
                proxy_blocks = parts[1:]

                # Keep only the proxy blocks that we don't want to delete
                kept_blocks = []
                for block in proxy_blocks:
                    # Check if this block's name is in our deletion set
                    # We construct the full 'name = "..."' string for a precise match
                    if not any(f'name = "{name}"' in block for name in proxy_names_to_delete):
                        kept_blocks.append(block)

                # Rebuild the file content
                new_content = server_config
                if kept_blocks:
                    # Add the [[proxies]] delimiter back for each kept block
                    new_content += "\n[[proxies]]\n" + "\n[[proxies]]\n".join(kept_blocks)
                
                # Write the new content back to the file
                with open(FRP_CONFIG_PATH, "w") as f:
                    f.write(new_content)
                # --- End of replaced block ---

                print(f"Removed proxies for '{username}' from frpc.toml")
                reload_frpc_background(background_tasks)

            del registry[username]
            save_vm_registry(registry)

        return {"message": f"VM '{username}' destroyed and directory/tunnels removed successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#endregion


#region --- Start VM Endpoints ---
@app.post("/start-vm/{username}")
async def start_vm(username: str):
    try:
        vm_path = VMS_DIR / username
        print(vm_path)
        if not vm_path.exists():
            raise HTTPException(status_code=404, detail=f"VM '{username}' does not exist.")
        start_proc = subprocess.run(["vagrant", "up"], cwd=vm_path, capture_output=True, text=True)
        if start_proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"VM booting failed: {start_proc.stderr.strip()}")
        return {"message": f"VM '{username}' booted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
#endregion


#region --- Stop VM Endpoints ---

@app.post("/stop-vm/{username}")
async def stop_vm(username: str):
    try:
        vm_path = VMS_DIR / username
        if not vm_path.exists():
            raise HTTPException(status_code=404, detail=f"VM '{username}' does not exist.")
        stop_proc = subprocess.run(["vagrant", "halt"], cwd=vm_path, capture_output=True, text=True)
        if stop_proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Vagrant halt failed: {stop_proc.stderr.strip()}")
        return {"message": f"VM '{username}' Stopped successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#endregion

#endregion