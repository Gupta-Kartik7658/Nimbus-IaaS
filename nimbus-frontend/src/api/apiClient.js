import axios from 'axios';

// Configure the base URL for your FastAPI backend
const apiClient = axios.create({
  baseURL: 'http://127.0.0.1:8000', // Your backend server address
  headers: {
    'Content-Type': 'application/json',
  },
});

// Centralized public IP for the EC2 instance
export const publicIp = "13.233.204.203";

// --- VM Management ---
export const listVMs = () => apiClient.get('/list-vms');
export const createVM = (vmData) => apiClient.post('/create-vm', vmData);
export const deleteVM = (username) => apiClient.delete(`/delete-vm/${username}`);
export const startVM = (username) => apiClient.post(`/start-vm/${username}`);
export const stopVM = (username) => apiClient.post(`/stop-vm/${username}`);

// --- Key Management ---
export const listKeys = () => apiClient.get('/list-keys/');
export const generateKey = (keyName) => apiClient.post(`/generate-key/${keyName}`);
export const downloadKeyURL = (keyName) => `${apiClient.defaults.baseURL}/download/${keyName}`;

// --- Security Group / Firewall Management ---
// UPDATED: This function now sends data as form data to match the backend.
export const addInboundRule = (username, port, description) => {
  return apiClient.post(`/add-inbound-rule/${port}`, { username, description });
};
export const removeInboundRule = (username, remotePort) => {
  return apiClient.delete(`/remove-inbound-rule/${username}/${remotePort}`);
};

export default apiClient;