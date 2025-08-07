from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import os
from shutil import rmtree
from typing import List, Literal
import threading
import time
import json


app = FastAPI()


class InboundRule(BaseModel):
    type: Literal["http", "tcp"]
    vm_port: int
    localhost_port: int

class VirtualMachine(BaseModel):
    username: str
    key_name: str
    ram: int
    cpu: int
    image: str
    inbound_rules: List[InboundRule]
    private_ip: str
    

############################################################ SSH Key Generation and Download Endpoints ############################################################
@app.post("/generate-key/{key_name}")
async def generate_key(key_name: str):
    try:
        if not key_name.isalnum() or " " in key_name:
            raise HTTPException(status_code=400, detail="Key name must be alphanumeric and contain no spaces.")

        public_key_path = f".ssh/{key_name}.pub"
        private_key_path = f".ssh/{key_name}"

        if os.path.exists(public_key_path):
            raise HTTPException(status_code=400, detail=f"Key '{key_name}' already exists.")

        os.makedirs(".ssh", exist_ok=True)

        command = ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", private_key_path, "-N", "", "-C", key_name]

        process = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True
        )

        os.chmod(private_key_path, 0o600)

        return {"message": f"SSH key '{key_name}' generated successfully.", "download_path": f"/download/{key_name}"}

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"SSH keygen failed: {e.stderr.strip()}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{key_name}")
async def download_key(key_name: str):
    public_key_path = f".ssh/{key_name}.pub"
    private_key_path = f".ssh/{key_name}"

    if not os.path.exists(public_key_path) or not os.path.exists(private_key_path):
        raise HTTPException(status_code=404, detail=f"Key '{key_name}' does not exist.")

    return FileResponse(
        path=private_key_path,
        filename=key_name,
        media_type='application/octet-stream'
    )


#######################################################################################################################################################################






############################################################# VM Registry Management ###########################################################################

   

def get_vagrantfile_content(vm: VirtualMachine, private_ip) -> str:
    return f"""
    Vagrant.configure("2") do |config|
        # --- Ruby variables ---
        NEW_USERNAME = "{vm.username}"
        NEW_HOSTNAME = "{vm.username}"

        config.vm.box = "{vm.image}"
        config.vm.network "private_network", ip: "{private_ip}"

        # Set the hostname
        config.vm.hostname = NEW_HOSTNAME
        config.hostsupdater.aliases = [NEW_HOSTNAME]

        config.vm.provider "virtualbox" do |vb|
            vb.memory = "{vm.ram}"
            vb.cpus = "{vm.cpu}"
        end

        config.ssh.insert_key = false

        # Copy SSH public key to the guest
        config.vm.provision "file", source: "../../.ssh/{vm.key_name}.pub", destination: "/tmp/user_public_key.pub"

        # Provision VM using shell
        config.vm.provision "shell", inline: <<-SHELL
            NEW_USERNAME="{vm.username}"

            echo "Provisioning VM with user '$NEW_USERNAME'..."

            # Create user with home and bash shell
            useradd --create-home --shell /bin/bash "$NEW_USERNAME"
            usermod -aG wheel "$NEW_USERNAME"

            # Allow passwordless sudo for the new user
            echo "$NEW_USERNAME ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/$NEW_USERNAME
            chmod 440 /etc/sudoers.d/$NEW_USERNAME

            # Setup SSH key for the new user
            mkdir -p /home/$NEW_USERNAME/.ssh
            cat /tmp/user_public_key.pub > /home/$NEW_USERNAME/.ssh/authorized_keys
            chown -R $NEW_USERNAME:$NEW_USERNAME /home/$NEW_USERNAME/.ssh
            chmod 700 /home/$NEW_USERNAME/.ssh
            chmod 600 /home/$NEW_USERNAME/.ssh/authorized_keys

            # Ensure SSHD allows public key auth
            sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config || true
            systemctl restart sshd || systemctl restart ssh

            echo "Provisioning complete. You can SSH using:"
            echo "ssh -i ~/.ssh/{vm.key_name} {vm.username}@{private_ip}"
        SHELL
    end
    """
    

REGISTRY_FILE = ".vms/registry.json"

def load_vm_registry():
    if not os.path.exists(REGISTRY_FILE):
        return {}
    with open(REGISTRY_FILE, "r") as f:
        return json.load(f)

def save_vm_registry(registry):
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=4)
        
def stream_vagrant_up(vm_path: str):
    try:
        process = subprocess.Popen(
            ["vagrant", "up"],
            cwd=vm_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True
        )

        for line in process.stdout:
            print(f"[VAGRANT]: {line}", end="")

        process.wait()
        print(f"[INFO] Vagrant exited with code: {process.returncode}")

    except Exception as e:
        print(f"[ERROR] Exception during Vagrant up: {e}")


def find_ip(registry_path=".vms/registry.json", base_ip="192.168.56.", start=11, end=250):
    used_ips = set()

    if os.path.exists(registry_path):
        with open(registry_path, "r") as f:
            data = json.load(f)
            for vm_info in data.values():
                ip = vm_info.get("private_ip")
                if ip:
                    used_ips.add(ip)

    for i in range(start, end):
        candidate = f"{base_ip}{i}"
        if candidate not in used_ips:
            return candidate

    raise Exception("No available IP addresses in range.")

@app.post("/create-vm")
async def create_vm(vm: VirtualMachine, background_tasks: BackgroundTasks):
    try:
        vm_path = f".vms/{vm.username}"
        private_ip = find_ip()
        registry = load_vm_registry()
        
        registry[vm.username] = {
            "private_ip": private_ip,
            "key_name": vm.key_name,
            "ram": vm.ram,
            "cpu": vm.cpu,
            "image": vm.image,
            "inbound_rules": [rule.model_dump() for rule in vm.inbound_rules]
        }
        save_vm_registry(registry)

        if os.path.exists(vm_path):
            raise HTTPException(status_code=400, detail=f"VM '{vm.username}' already exists.")

        if not os.path.exists(f".ssh/{vm.key_name}.pub"):
            raise HTTPException(status_code=400, detail=f"SSH key '{vm.key_name}' does not exist. Generate it first.")

        os.makedirs(vm_path, exist_ok=True)

        vagrantfile_content = get_vagrantfile_content(vm, private_ip)
        vagrantfile_path = os.path.join(vm_path, "Vagrantfile")

        with open(vagrantfile_path, "w") as f:
            f.write(vagrantfile_content)

        background_tasks.add_task(stream_vagrant_up, vm_path)
        return {"message": f"VM '{vm.username}' is being provisioned. Logs are streaming in the server terminal."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.delete("/delete-vm/{username}")
async def delete_vm(username: str):
    try:
        vm_path = f".vms/{username}"

        if not os.path.exists(vm_path):
            raise HTTPException(status_code=404, detail=f"VM '{username}' does not exist.")

        # Destroy the VM
        destroy_proc = subprocess.run(
            ["vagrant", "destroy", "-f"],
            cwd=vm_path,
            capture_output=True,
            text=True
        )
        
        if destroy_proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Vagrant destroy failed: {destroy_proc.stderr.strip()}")

        # Remove VM directory
        rmtree(vm_path)
        
        # Remove VM from registry
        registry = load_vm_registry()
        if username in registry:
            del registry[username]
            save_vm_registry(registry)

        return {"message": f"VM '{username}' destroyed and directory removed successfully."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


#########################################################################################################################################################################




############################################################# Port Forwarding and Ngrok Setup ###########################################################################
def forward_and_expose_ports(vm: VirtualMachine):
    try:
        private_ip = vm.private_ip
        
        for rule in vm.inbound_rules:
            ssh_cmd = [
                "ssh",
                "-i", f".ssh/{vm.key_name}",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-N",
                "-L", f"{rule.localhost_port}:{private_ip}:{rule.vm_port}",
                f"{vm.username}@{private_ip}"
            ]
            def ssh_tunnel():
                print(f"[SSH] Forwarding localhost:{rule.localhost_port} → {private_ip}:{rule.vm_port}...")
                subprocess.run(ssh_cmd)

            threading.Thread(target=ssh_tunnel, daemon=True).start()
            time.sleep(1)  # Give tunnel time to start

            if rule.type == "http":
                ngrok_cmd = ["ngrok", "http", str(rule.localhost_port)]
            elif rule.type == "tcp":
                ngrok_cmd = ["ngrok", "tcp", str(rule.localhost_port)]
            else:
                print(f"[WARNING] Unknown rule type: {rule.type}")
                continue

            def start_ngrok():
                print(f"[NGROK] Exposing localhost:{rule.localhost_port} over {rule.type.upper()}...")
                subprocess.run(ngrok_cmd)

            threading.Thread(target=start_ngrok, daemon=True).start()
            time.sleep(2)

    except Exception as e:
        print(f"[ERROR] Error while forwarding ports: {e}")
        
        
        
        
@app.post("/expose-vm/{username}")
async def expose_vm(username: str, background_tasks: BackgroundTasks):
    try:
        registry = load_vm_registry()
        if username not in registry:
            raise HTTPException(status_code=404, detail="VM not found in registry.")

        metadata = registry[username]
        private_ip = metadata["private_ip"]
        key_name = metadata["key_name"]

        # Load VM's Vagrantfile to get box username (or assume `username`)

        vm = VirtualMachine(
            username=username,
            key_name=metadata["key_name"],
            ram=metadata['ram'], 
            cpu=metadata['cpu'], 
            image=metadata['image'],
            inbound_rules=metadata["inbound_rules"],
            private_ip=private_ip
        )

        background_tasks.add_task(forward_and_expose_ports, vm)

        return {"message": f"Inbound rules are being applied for VM '{username}'."}

    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))
        

##########################################################################################################################################################################


if __name__ == "__Server__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
