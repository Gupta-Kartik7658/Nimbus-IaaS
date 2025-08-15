from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import os
from shutil import rmtree
from typing import List, Literal, Set
import time
import json
from pathlib import Path
import psutil
from contextlib import asynccontextmanager

# --- Configuration ---
BASE_DIR = Path(__file__).parent
VMS_DIR = BASE_DIR / ".vms"
SSH_DIR = BASE_DIR / ".ssh"
REGISTRY_FILE = VMS_DIR / "registry.json"

# --- FRP Configuration ---
FRP_DIR = BASE_DIR / "frp_0.59.0_windows_amd64"  # Adjust this path as needed
FRP_EXECUTABLE_PATH = FRP_DIR / "frpc.exe" # Or "frpc" on Linux/macOS
FRP_CONFIG_PATH = FRP_DIR / "frpc.toml"
frpc_process = None # Global variable to hold the frpc process

# --- Lifespan Manager (Replaces deprecated on_event) ---
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

class InboundRule(BaseModel):
    type: Literal["http", "tcp"]
    vm_port: int

class VirtualMachine(BaseModel):
    username: str
    key_name: str
    ram: int
    cpu: int
    image: str
    inbound_rules: List[InboundRule]

############################################################ SSH Key Generation and Download Endpoints ############################################################
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

#######################################################################################################################################################################

############################################################# VM Registry Management ###########################################################################
def get_vagrantfile_content(vm: VirtualMachine, private_ip) -> str:
    pub_key_path = SSH_DIR / f"{vm.key_name}.pub"
    if not pub_key_path.exists():
        raise FileNotFoundError(f"Public key file not found: {pub_key_path}")

    # Escape backslashes for Vagrant's Ruby parser
    pub_key_path_str = str(pub_key_path).replace("\\", "/")

    return f"""
Vagrant.configure("2") do |config|
    NEW_USERNAME = "{vm.username}"
    NEW_HOSTNAME = "{vm.username}"
    config.vm.box = "{vm.image}"
    config.vm.network "private_network", ip: "{private_ip}"
    config.vm.hostname = NEW_HOSTNAME
    config.hostsupdater.aliases = [NEW_HOSTNAME]
    config.vm.provider "virtualbox" do |vb|
        vb.memory = "{vm.ram}"
        vb.cpus = "{vm.cpu}"
    end
    config.ssh.insert_key = false
    config.vm.provision "file", source: "{pub_key_path_str}", destination: "/tmp/user_public_key.pub"
    config.vm.provision "shell", inline: <<-SHELL
        NEW_USERNAME="{vm.username}"
        echo "Provisioning VM with user '$NEW_USERNAME'..."
        useradd --create-home --shell /bin/bash "$NEW_USERNAME"
        usermod -aG wheel "$NEW_USERNAME"
        echo "$NEW_USERNAME ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/$NEW_USERNAME
        chmod 440 /etc/sudoers.d/$NEW_USERNAME
        mkdir -p /home/$NEW_USERNAME/.ssh
        cat /tmp/user_public_key.pub > /home/$NEW_USERNAME/.ssh/authorized_keys
        chown -R $NEW_USERNAME:$NEW_USERNAME /home/$NEW_USERNAME/.ssh
        chmod 700 /home/$NEW_USERNAME/.ssh
        chmod 600 /home/$NEW_USERNAME/.ssh/authorized_keys
        sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config || true
        systemctl restart sshd || systemctl restart ssh
        echo "Provisioning complete."
    SHELL
end
"""


def load_vm_registry():
    if not REGISTRY_FILE.exists():
        return {}
    with open(REGISTRY_FILE, "r") as f:
        return json.load(f)

def save_vm_registry(registry):
    VMS_DIR.mkdir(exist_ok=True)
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=4)

def stream_vagrant_up(vm_path: str):
    try:
        process = subprocess.Popen(["vagrant", "up"], cwd=vm_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(f"[VAGRANT]: {line}", end="")
        process.wait()
        print(f"[INFO] Vagrant exited with code: {process.returncode}")
    except Exception as e:
        print(f"[ERROR] Exception during Vagrant up: {e}")

def find_ip(base_ip="192.168.56.", start=11, end=250):
    registry = load_vm_registry()
    used_ips = {vm.get("private_ip") for vm in registry.values()}
    for i in range(start, end):
        candidate = f"{base_ip}{i}"
        if candidate not in used_ips:
            return candidate
    raise Exception("No available IP addresses in range.")

## FIXED ## --- Function to find available remote port for frp ---
def find_available_remotePort(exclude_ports: Set[int] = None, start=2222, end=3000):
    if exclude_ports is None:
        exclude_ports = set()
    
    registry = load_vm_registry()
    used_ports = set()
    for vm in registry.values():
        for rule in vm.get("inbound_rules", []):
            if "" in rule:
                used_ports.add(rule["remotePort"])
    
    # Combine saved ports with ports assigned in the current request
    all_used_ports = used_ports.union(exclude_ports)

    for port in range(start, end):
        if port not in all_used_ports:
            return port
    raise Exception("No available remote ports for tunnels.")

## --- FRPC Process Management Functions ---
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

def restart_frpc_background(background_tasks: BackgroundTasks):
    background_tasks.add_task(stop_frpc)
    background_tasks.add_task(time.sleep, 1)
    background_tasks.add_task(start_frpc)

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
        restart_frpc_background(background_tasks)

        return {"message": f"VM '{vm.username}' is being provisioned. Tunnels are being configured."}

    except Exception as e:
        registry = load_vm_registry()
        if vm.username in registry:
            del registry[vm.username]
            save_vm_registry(registry)
        raise HTTPException(status_code=500, detail=str(e))

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
                restart_frpc_background(background_tasks)

            del registry[username]
            save_vm_registry(registry)

        return {"message": f"VM '{username}' destroyed and directory/tunnels removed successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/start-vm/{username}")
async def start_vm(username: str):
    try:
        vm_path = VMS_DIR / username
        if not vm_path.exists():
            raise HTTPException(status_code=404, detail=f"VM '{username}' does not exist.")
        start_proc = subprocess.run(["vagrant", "up"], cwd=vm_path, capture_output=True, text=True)
        if start_proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"VM booting failed: {start_proc.stderr.strip()}")
        return {"message": f"VM '{username}' booted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
