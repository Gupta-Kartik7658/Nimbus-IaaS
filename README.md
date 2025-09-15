# 🌩️ Nimbus-IaaS

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Status: Development](https://img.shields.io/badge/status-development-orange)
![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi)
![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react)

A lightweight IaaS (Infrastructure as a Service) platform to create, manage, and expose local VirtualBox VMs to the internet with a clean, modern web interface.

---

## Table of Contents

- [About The Project](#about-the-project)
- [Screenshots](#screenshots)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Setup](#setup)
- [API Reference](#api-reference)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## About The Project

Nimbus-IaaS bridges the gap between local development and global access. It leverages the power of **Vagrant** to provision and manage virtual machines on your local PC and uses **FRP (Fast Reverse Proxy)** to tunnel traffic, giving each VM a public-facing port. This eliminates the need for expensive cloud providers for development, testing, or personal projects that require public accessibility.

The entire system is controlled by a robust **FastAPI** backend and a responsive **React** frontend, providing a seamless, cloud-like experience for managing your local infrastructure.



---

## Screenshots

| Dashboard View                                    | Create VM Modal                                  | Firewall Management                              |
| ------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------ |
|  |  |  |

---

## Key Features

-   **🖥️ Full VM Lifecycle Management**: Create, start, stop, and delete VirtualBox VMs directly from the web UI.
-   **🔑 SSH Key Management**: Generate new SSH key pairs or use existing ones for secure VM access.
-   **🌐 Global Accessibility**: Each VM service is exposed via a public IP and port, managed by an FRP tunnel.
-   **🔒 Dynamic Firewall Control**: Manage inbound rules for each VM in real-time. Changes are automatically synced with your cloud provider's (AWS) security group.
-   **📜 Provisioning Scripts**: Bootstrap your VMs with custom shell scripts on creation.
-   **✨ Modern UI**: A clean, responsive, and intuitive interface built with React and Tailwind CSS.

---

## Tech Stack

The project is built with a modern, decoupled architecture.

### Backend

-   **Framework**: [Python](https://www.python.org/) with [FastAPI](https://fastapi.tiangolo.com/)
-   **VM Provisioning**: [Vagrant](https://www.vagrantup.com/)
-   **Virtualization**: [Oracle VirtualBox](https://www.virtualbox.org/)
-   **Tunneling/Proxy**: [FRP (Fast Reverse Proxy)](https://github.com/fatedier/frp)
-   **Cloud Integration**: [Boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) (for AWS Security Group management)

### Frontend

-   **Framework**: [React](https://reactjs.org/) (with Vite)
-   **Styling**: [Tailwind CSS](https://tailwindcss.com/)
-   **API Communication**: [Axios](https://axios-http.com/)

---

## Getting Started

Follow these instructions to get a local copy up and running.

### Prerequisites

Ensure you have the following software installed and configured on your host machine:

-   **Python** (v3.8+) and `pip`
-   **Node.js** (v16+) and `npm`
-   **Vagrant**
-   **Oracle VirtualBox**
-   **FRP Server (frps)**: You must have an `frps` server running on a cloud instance (like an AWS EC2 t2.micro) with a public IP.
    -   Your EC2 instance's security group must allow traffic on the `frps` port (default `7000`) and the range of ports you intend to use for tunnels (e.g., `2222-3000`).
-   **AWS CLI**: Configured with credentials that have permission to manage EC2 Security Groups.

### Setup

1.  **Clone the repository:**
    ```sh
    git clone [https://github.com/your-username/nimbus-iaas.git](https://github.com/your-username/nimbus-iaas.git)
    cd nimbus-iaas
    ```

2.  **Backend Setup:**
    ```sh
    # Navigate to the backend directory
    # (Assuming your main.py is in the root or a 'backend' folder)

    # Create and activate a virtual environment
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate

    # Install Python dependencies
    pip install -r requirements.txt

    # Configure FRP Client
    # Edit frpc.toml and set the 'serverAddr' to your cloud instance's public IP.

    # Run the backend server
    uvicorn main:app --reload
    ```
    The backend server will be running at `http://127.0.0.1:8000`.

3.  **Frontend Setup:**
    ```sh
    # Navigate to the frontend directory
    cd nimbus-iaas-frontend

    # Install NPM packages
    npm install

    # Start the development server
    npm run dev
    ```
    The frontend will be available at `http://localhost:5173`.

---

## API Reference

The following API endpoints are available:

| Method   | Path                                            | Description                                          |
| :------- | :---------------------------------------------- | :--------------------------------------------------- |
| `GET`    | `/list-vms`                                     | Retrieves a list of all managed VMs.                 |
| `POST`   | `/create-vm`                                    | Creates a new virtual machine.                       |
| `DELETE` | `/delete-vm/{username}`                         | Destroys a VM and cleans up its resources.           |
| `POST`   | `/start-vm/{username}`                          | Boots up an existing VM.                             |
| `POST`   | `/stop-vm/{username}`                           | Gracefully shuts down an existing VM.                |
| `GET`    | `/list-keys`                                    | Lists all available public SSH keys.                 |
| `POST`   | `/generate-key/{key_name}`                      | Generates a new RSA SSH key pair.                    |
| `GET`    | `/download/{key_name}`                          | Downloads the private key file.                      |
| `POST`   | `/add-inbound-rule/{port}`                      | Adds a new firewall rule/tunnel to an existing VM.   |
| `DELETE` | `/remove-inbound-rule/{username}/{remote_port}` | Removes a firewall rule from an existing VM.         |

---

## Roadmap

-   [ ] **User Authentication**: Implement a login system to support multiple users.
-   [ ] **Resource Monitoring**: Display real-time CPU and RAM usage for each VM.
-   [ ] **Support for Docker**: Add an option to provision Docker containers alongside VMs.
-   [ ] **Enhanced Logging**: Provide a view of Vagrant and provisioning logs in the UI.
-   [ ] **VM Snapshots**: Add functionality to create and restore VM snapshots.

See the [open issues](https://github.com/your-username/nimbus-iaas/issues) for a full list of proposed features (and known issues).

---

## Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

---

## License

Distributed under the MIT License. See `LICENSE.txt` for more information.