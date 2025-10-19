const API_BASE_URL = "http://13.233.204.203:8000";

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface VM {
  id: number;
  name: string;
  key_name: string;
  ram: number;
  cpu: number;
  image: string;
  private_ip: string;
  inbound_rules: InboundRule[];
  owner_id: number;
  status?: "running" | "stopped" | "pending";
}

export interface InboundRule {
  type: "http" | "tcp" | "ssh" | "udp" | "icmp";
  vm_port: number;
  description?: string;
  remotePort?: number;
}

export interface SSHKey {
  name: string;
}

export interface CreateVMRequest {
  username: string;
  key_name: string;
  ram: number;
  cpu: number;
  image: string;
  inbound_rules?: InboundRule[];
  provisioning_script?: string;
}

class APIClient {
  private token: string | null = null;

  constructor() {
    // Load token from localStorage on init
    this.token = localStorage.getItem("auth_token");
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem("auth_token", token);
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem("auth_token");
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
      credentials: "include",
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "An error occurred" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // Auth endpoints
  async login(data: LoginRequest) {
    const formData = new FormData();
    formData.append("username", data.username);
    formData.append("password", data.password);

    const response = await fetch(`${API_BASE_URL}/auth/jwt/login`, {
      method: "POST",
      body: formData,
      credentials: "include",
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Login failed" }));
      throw new Error(error.detail);
    }

    const result = await response.json();
    this.setToken(result.access_token);
    return result;
  }

  async register(data: RegisterRequest) {
    return this.request("/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async logout() {
    try {
      await this.request("/auth/jwt/logout", { method: "POST" });
    } finally {
      this.clearToken();
    }
  }

  // VM endpoints
  async listVMs(): Promise<VM[]> {
    return this.request("/list-vms");
  }

  async createVM(data: CreateVMRequest) {
    return this.request("/create-vm", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async deleteVM(vmName: string) {
    return this.request(`/delete-vm/${vmName}`, { method: "DELETE" });
  }

  async startVM(vmName: string) {
    return this.request(`/start-vm/${vmName}`, { method: "POST" });
  }

  async stopVM(vmName: string) {
    return this.request(`/stop-vm/${vmName}`, { method: "POST" });
  }

  async addInboundRule(port: number, vmName: string, description: string) {
    return this.request(`/add-inbound-rule/${port}`, {
      method: "POST",
      body: JSON.stringify({ vm_name: vmName, description }),
    });
  }

  async removeInboundRule(vmName: string, remotePort: number) {
    return this.request(`/remove-inbound-rule/${vmName}/${remotePort}`, {
      method: "DELETE",
    });
  }

  // SSH Key endpoints
  async listKeys(): Promise<SSHKey[]> {
    return this.request("/list-keys");
  }

  async generateKey(keyName: string) {
    return this.request(`/generate-key/${keyName}`, { method: "POST" });
  }

  async downloadKey(keyName: string) {
    const response = await fetch(`${API_BASE_URL}/download-key/${keyName}`, {
      headers: { Authorization: `Bearer ${this.token}` },
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error("Failed to download key");
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = keyName;
    a.click();
    window.URL.revokeObjectURL(url);
  }

  async deleteKey(keyName: string) {
    return this.request(`/delete-key/${keyName}`, { method: "DELETE" });
  }
}

export const api = new APIClient();
