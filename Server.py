import os
import subprocess
import asyncio
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# --- Cryptography for SSH Key Generation ---
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# --- App Initialization ---
app = FastAPI(
    title="Nimbus-IaaS API",
    description="An API to manage a local IaaS platform using Vagrant.",
    version="0.1.0",
)

# --- Configuration ---
# Base directory for storing VM-related files
VMS_DIR = Path("running_vms")
# Directory to store generated SSH keys
SSH_DIR = Path(".ssh")
# Ensure directories exist
VMS_DIR.mkdir(exist_ok=True)
SSH_DIR.mkdir(exist_ok=True)
# Network configuration
IP_SUBNET = "192.168.56"
MAX_VMS = 5  # Limit to 5 VMs as requested

# --- Pydantic Models for Data Validation ---

class VMCreateRequest(BaseModel):
    username: str = Field(..., description="Username for the VM user. Also used as the hostname.")
    ram: int = Field(1024, description="RAM for the VM in MB.")
    cpu: int = Field(1, description="Number of CPU cores for the VM.")
    image: str = Field("eurolinux-vagrant/centos-stream-9", description="Vagrant box image to use.")
    ssh_key_name: str = Field(..., description="The filename of the public SSH key to use (without extension).")

class KeyPairResponse(BaseModel):
    key_name: str
    message: str

# --- Helper Functions ---

def is_ip_in_use(ip_address: str) -> bool:
    try:
        param = "-n" if os.name == "nt" else "-c"
        command = ["ping", "-n", "1", ip_address]
        subprocess.check_output(command, stderr=subprocess.STDOUT)
        return True  # Host is reachable
    except subprocess.CalledProcessError:
        return False # Host is not reachable

def find_available_ip() -> str:
    for i in range(10, 255):
        ip = f"{IP_SUBNET}.{i}"
        if not is_ip_in_use(ip):
            return ip
    raise HTTPException(status_code=500, detail="No available IP addresses found in the subnet.")

def get_vagrantfile_template(vm_request: VMCreateRequest, ip_address: str) -> str:
    """Dynamically generates the content for a Vagrantfile."""
    
    # The public key file name inside the .ssh directory
    public_key_filename = f"{vm_request.ssh_key_name}.pub"

    return f"""
# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
    # --- Variables for Customization ---
    vm_request.username = "{vm_request.username}" # Using username as hostname

    config.vm.box = "{vm_request.image}"
    config.vm.network "private_network", ip: "{ip_address}"
    
    config.vm.hostname = {vm_request.username}
    config.hostsupdater.aliases = [{vm_request.username}]

    config.vm.provider "virtualbox" do |vb|
        vb.memory = "{vm_request.ram}"
        vb.cpus = "{vm_request.cpu}"
        vb.name = {vm_request.username} # Set the name in VirtualBox GUI
    end
    
    config.ssh.insert_key = false
    # NOTE: The source path is relative to the project root, not the VM directory
    config.vm.provision "file", source: "../.ssh/{public_key_filename}", destination: "/tmp/user_public_key.pub"

    config.vm.provision "shell", inline: <<-SHELL
        echo "Provisioning VM with custom user and hostname..."
        
        useradd --create-home --shell /bin/bash {vm_request.username}
        usermod -aG wheel {vm_request.username}

        echo "Granting passwordless sudo to {vm_request.username}"
        echo '{vm_request.username} ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/{vm_request.username}
        
        echo "Setting up key-based SSH for {vm_request.username}"
        mkdir -p /home/{vm_request.username}/.ssh
        cat /tmp/user_public_key.pub > /home/{vm_request.username}/.ssh/authorized_keys
        chown -R {vm_request.username}:{vm_request.username} /home/{vm_request.username}/.ssh
        chmod 700 /home/{vm_request.username}/.ssh
        chmod 600 /home/{vm_request.username}/.ssh/authorized_keys

        echo "Provisioning complete."
        echo "SSH as: ssh -i .ssh/{vm_request.ssh_key_name} {vm_request.username}@{ip_address}"
    SHELL
end
"""

async def run_vagrant_up(vm_path: Path):

    process = await asyncio.create_subprocess_shell(
        "vagrant up",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=vm_path  # Run the command in the specific VM's directory
    )
    
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        # You would add more robust logging/error handling here in a real app
        print(f"Error provisioning VM at {vm_path}:")
        print(f"STDOUT: {stdout.decode()}")
        print(f"STDERR: {stderr.decode()}")
    else:
        print(f"Successfully provisioned VM at {vm_path}")


# --- API Endpoints ---

@app.post("/keys", response_model=KeyPairResponse)
async def create_ssh_key_pair(key_name: str):
    """
    Generates a new RSA SSH key pair and saves it to the .ssh directory.
    The private key is returned for the user to download.
    """
    private_key_path = SSH_DIR / key_name
    public_key_path = SSH_DIR / f"{key_name}.pub"

    if private_key_path.exists() or public_key_path.exists():
        raise HTTPException(status_code=400, detail=f"Key with name '{key_name}' already exists.")

    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Serialize private key in PEM format
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Generate public key
    public_key = private_key.public_key()
    ssh_public_key = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH
    )

    # Save keys to files
    with open(private_key_path, "wb") as f:
        f.write(pem)
    os.chmod(private_key_path, 0o600) # Set strict permissions

    with open(public_key_path, "wb") as f:
        f.write(ssh_public_key)

    return {
        "key_name": key_name,
        "message": f"Successfully created key pair '{key_name}'. Use the /keys/download/{key_name} endpoint to get the private key."
    }

@app.get("/keys/download/{key_name}")
async def download_private_key(key_name: str):
    """
    Allows the user to download their generated private SSH key.
    """
    private_key_path = SSH_DIR / key_name
    if not private_key_path.is_file():
        raise HTTPException(status_code=404, detail="Private key not found.")
    
    return FileResponse(
        path=private_key_path,
        filename=key_name,
        media_type='application/octet-stream'
    )

@app.post("/vms")
async def create_vm(vm_request: VMCreateRequest, background_tasks: BackgroundTasks):
    """
    Creates and provisions a new virtual machine based on user specifications.
    This process is run in the background.
    """
    # --- Pre-flight Checks ---
    # Check if the requested SSH key exists
    public_key_path = SSH_DIR / f"{vm_request.ssh_key_name}.pub"
    if not public_key_path.is_file():
        raise HTTPException(status_code=404, detail=f"SSH public key '{vm_request.ssh_key_name}.pub' not found.")

    # Check if a VM with this name already exists
    vm_path = VMS_DIR / vm_request.username
    if vm_path.exists():
        raise HTTPException(status_code=400, detail=f"A VM with the name '{vm_request.username}' already exists.")
    
    # Check against the max VM limit
    current_vms = len(list(VMS_DIR.iterdir()))
    if current_vms >= MAX_VMS:
        raise HTTPException(status_code=400, detail=f"Reached maximum VM limit of {MAX_VMS}.")

    # --- Provisioning Logic ---
    available_ip = find_available_ip()
    
    # Create a dedicated directory for this VM
    vm_path.mkdir()
    
    # Generate the Vagrantfile content
    vagrantfile_content = get_vagrantfile_template(vm_request, available_ip)
    
    # Write the Vagrantfile
    with open(vm_path / "Vagrantfile", "w") as f:
        f.write(vagrantfile_content)
        
    # Run 'vagrant up' in the background so the API can return immediately
    background_tasks.add_task(run_vagrant_up, vm_path)
    
    return {
        "message": "VM creation initiated in the background.",
        "vm_name": vm_request.username,
        "ip_address": available_ip,
        "details": "The VM will be provisioned shortly. This may take a few minutes."
    }

# To run the app, save this file as main.py and run: uvicorn main:app --reload
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
