from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os 
import subprocess
import uvicorn
from fastapi.responses import FileResponse

app = FastAPI()

class sshKey(BaseModel):
    key: str
    name: str
    
class VirtualMachine(BaseModel):
    username: str
    ssh_key: sshKey
    ram: int 
    cpu: int 
    image: str
    
@app.post("/generate-key/{key_name}")
async def generate_key(key_name: str):
    try:
        if not key_name.isalnum() or " " in key_name:
            raise HTTPException(
                status_code=400,
                detail="Key name must be alphanumeric and contain no spaces."
            )
        public_key_path = f".ssh/{key_name}.pub"
        private_key_path = f".ssh/{key_name}"
        
        if os.path.exists(public_key_path):
            raise HTTPException(
                status_code=400,
                detail=f"A key with the name '{key_name}' already exists."
            )
            
        command = ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", private_key_path, "-N", "", "-C", key_name]
        
        try:
            # Run the command
            process = subprocess.run(
                command,
                check=True, # Raises CalledProcessError if the command returns a non-zero exit code
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error generating SSH key: {e.stderr.strip()}"
            )
            
        # Set strict permissions on the private key for security
        os.chmod(private_key_path, 0o600)
        
        return {"message": f"SSH key '{key_name}' generated successfully.", "download_path": f"/download/{key_name}"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/download/{key_name}")
async def download_key(key_name: str):
    public_key_path = f".ssh/{key_name}.pub"
    private_key_path = f".ssh/{key_name}"
    if not os.path.exists(public_key_path) or not os.path.exists(private_key_path):
        raise HTTPException(
            status_code=404,
            detail=f"Key '{key_name}' does not exist."
        )
    
    return FileResponse(
        path=private_key_path,
        filename=key_name,
        media_type='application/octet-stream'
    )

if __name__ == "__Server__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

