from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import os

app = FastAPI()


class VirtualMachine(BaseModel):
    username: str
    key_name: str
    ram: int
    cpu: int
    image: str

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


@app.post("/create-vm")
async def create_vm(vm: VirtualMachine, background_tasks: BackgroundTasks):
    try:
        vm_path = f".vms/{vm.username}"
        private_ip = "192.168.56.11"

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


if __name__ == "__Server__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
