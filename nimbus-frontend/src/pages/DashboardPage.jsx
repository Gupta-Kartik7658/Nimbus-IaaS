import React, { useState, useEffect, useCallback } from 'react';
import {
  Cpu,
  MemoryStick,
  Box,
  Play,
  Square,
  Trash2,
  Shield,
  Copy,
  Key,
  X,
  Plus,
  Loader
} from 'lucide-react';
import {
  listVMs,
  deleteVM,
  startVM,
  stopVM,
  createVM,
  generateKey,
  downloadKeyURL,
  listKeys,
  addInboundRule,
  removeInboundRule,
  publicIp
} from '../api/apiClient';

const VMCard = ({ vm, onDelete, onStart, onStop, onManageFirewall }) => {
  const sshRule = vm.inbound_rules.find(rule => rule.vm_port === 22);
  const sshCommand = sshRule
    ? `ssh -i ${vm.key_name} ${vm.username}@${publicIp} -p ${sshRule.remotePort}`
    : 'SSH rule not found.';

  const copyToClipboard = (text) => {
    if (!sshRule) {
      alert(text);
      return;
    }
    navigator.clipboard.writeText(text);
    alert('SSH command copied to clipboard!');
  };

  const getStatusColor = (status) => {
    return status === 'Running' ? 'bg-green-500' : 'bg-slate-500';
  };

  return (
    <div className="bg-slate-800/60 rounded-xl shadow-lg p-6 flex flex-col justify-between border border-slate-700 hover:border-cyan-500 transition-all duration-300">
      <div>
        <div className="flex justify-between items-start mb-4">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${getStatusColor(vm.status || 'Running')}`}></div>
            <h2 className="text-2xl font-bold text-white">{vm.username}</h2>
          </div>
          <span className={`text-xs font-medium px-2 py-1 rounded ${getStatusColor(vm.status || 'Running')} text-white`}>
            {vm.status || 'Running'}
          </span>
        </div>

        <div className="flex flex-wrap gap-4 mb-4 text-sm text-slate-300">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-cyan-400" />
            <span>{vm.cpu} CPU</span>
          </div>
          <div className="flex items-center gap-2">
            <MemoryStick className="w-4 h-4 text-cyan-400" />
            <span>{vm.ram} MB</span>
          </div>
          <div className="flex items-center gap-2">
            <Box className="w-4 h-4 text-cyan-400" />
            <span className="text-xs">{vm.image}</span>
          </div>
        </div>

        <div className="mt-4">
          <h3 className="font-semibold text-sm mb-2 text-slate-300">SSH Access</h3>
          <button
            onClick={() => copyToClipboard(sshCommand)}
            className="w-full text-left p-3 rounded-lg bg-slate-900/80 hover:bg-slate-900 border border-slate-700 hover:border-cyan-500 font-mono text-xs text-cyan-300 transition-all duration-200 flex items-center justify-between group"
          >
            <span className="truncate">{sshCommand}</span>
            <Copy className="w-4 h-4 text-slate-500 group-hover:text-cyan-400 flex-shrink-0 ml-2" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2 mt-6">
        <button
          onClick={onManageFirewall}
          className="col-span-4 bg-cyan-500 hover:bg-cyan-400 text-white font-semibold py-2.5 px-4 rounded-lg transition-all duration-200 flex items-center justify-center gap-2"
        >
          <Shield className="w-4 h-4" />
          Manage Firewall
        </button>
        <button
          onClick={onStart}
          className="col-span-2 bg-green-600 hover:bg-green-500 text-white font-semibold py-2 px-3 rounded-lg transition-all duration-200 flex items-center justify-center gap-2"
        >
          <Play className="w-4 h-4" />
          Start
        </button>
        <button
          onClick={onStop}
          className="col-span-2 bg-yellow-600 hover:bg-yellow-500 text-white font-semibold py-2 px-3 rounded-lg transition-all duration-200 flex items-center justify-center gap-2"
        >
          <Square className="w-4 h-4" />
          Stop
        </button>
        <button
          onClick={onDelete}
          className="col-span-4 bg-red-600 hover:bg-red-500 text-white font-semibold py-2 px-3 rounded-lg transition-all duration-200 flex items-center justify-center gap-2"
        >
          <Trash2 className="w-4 h-4" />
          Delete
        </button>
      </div>
    </div>
  );
};

const SSHKeyList = ({ keys, onDelete }) => {
  if (!keys || keys.length === 0) {
    return (
      <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
        <h2 className="text-xl font-bold mb-4 text-white">SSH Keys</h2>
        <p className="text-slate-400 text-sm text-center py-8">No SSH keys found</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
      <h2 className="text-xl font-bold mb-4 text-white">SSH Keys</h2>
      <div className="space-y-2">
        {keys.map(keyFile => {
          const keyName = keyFile.replace('.pub', '');
          return (
            <div
              key={keyName}
              className="flex items-center justify-between p-3 bg-slate-900/50 rounded-lg border border-slate-700 hover:border-cyan-500 transition-all duration-200"
            >
              <div className="flex items-center gap-2">
                <Key className="w-4 h-4 text-cyan-400" />
                <span className="text-sm text-slate-300 font-mono">{keyName}</span>
              </div>
              <button
                onClick={() => onDelete(keyName)}
                className="text-red-400 hover:text-red-300 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const CreateVMModal = ({ onClose, onVMCreated }) => {
  const [vmData, setVmData] = useState({
    username: '',
    key_name: '',
    ram: 1024,
    cpu: 1,
    image: 'ubuntu/focal64',
    provisioning_script: '#!/bin/bash\n# Your script here, e.g.\n# sudo apt-get update\n# sudo apt-get install -y nginx',
  });

  const [availableKeys, setAvailableKeys] = useState([]);
  const [showNewKeyForm, setShowNewKeyForm] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [downloadLink, setDownloadLink] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [keyLoading, setKeyLoading] = useState(false);

  useEffect(() => {
    const fetchKeys = async () => {
      try {
        const response = await listKeys();
        setAvailableKeys(response.data);
        if (response.data.length > 0) {
          const keyNameWithoutExt = response.data[0].replace('.pub', '');
          setVmData(prev => ({ ...prev, key_name: keyNameWithoutExt }));
        } else {
          setShowNewKeyForm(true);
        }
      } catch (error) {
        console.error("Failed to fetch SSH keys:", error);
        setShowNewKeyForm(true);
      }
    };
    fetchKeys();
  }, []);

  const handleKeyGenSubmit = async (e) => {
    e.preventDefault();
    setKeyLoading(true);
    try {
      await generateKey(newKeyName);
      setDownloadLink(downloadKeyURL(newKeyName));
      alert(`Key '${newKeyName}' generated! Don't forget to download it.`);
      setAvailableKeys(prev => [...prev, `${newKeyName}.pub`]);
      setVmData(prev => ({ ...prev, key_name: newKeyName }));
      setShowNewKeyForm(false);
    } catch (error) {
      alert('Error generating key: ' + (error.response?.data?.detail || error.message));
    } finally {
      setKeyLoading(false);
    }
  };

  const handleVMSubmit = async (e) => {
    e.preventDefault();
    if (!vmData.key_name) {
      alert("Please select or generate an SSH key before creating the VM.");
      return;
    }
    setIsLoading(true);
    try {
      const payload = { ...vmData, inbound_rules: [{type: "tcp", vm_port: 22, description: "SSH Access"}] };
      await createVM(payload);
      alert('VM creation process has started in the background! It may take a few minutes to become available.');
      onVMCreated();
    } catch (error) {
      alert('Error creating VM: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsLoading(false);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setVmData(prev => ({...prev, [name]: name === 'ram' || name === 'cpu' ? parseInt(value) : value}));
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex justify-center items-center z-50 p-4">
      <div className="bg-slate-800 p-8 rounded-xl shadow-2xl w-full max-w-2xl border border-slate-700">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-cyan-400">Create New VM</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <form onSubmit={handleVMSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-300">SSH Key</label>
            <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-700">
              <select
                name="key_name"
                value={vmData.key_name}
                onChange={(e) => setVmData(prev => ({...prev, key_name: e.target.value}))}
                className="w-full p-2.5 rounded-lg bg-slate-700 border border-slate-600 text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all"
              >
                <option value="" disabled>-- Select a key --</option>
                {availableKeys.map(keyFile => {
                  const keyName = keyFile.replace('.pub', '');
                  return <option key={keyName} value={keyName}>{keyName}</option>
                })}
              </select>

              {!showNewKeyForm ? (
                <div className="text-center mt-3">
                  <button
                    type="button"
                    onClick={() => setShowNewKeyForm(true)}
                    className="text-cyan-400 text-sm hover:text-cyan-300 transition-colors"
                  >
                    Or generate a new SSH key...
                  </button>
                </div>
              ) : (
                <form onSubmit={handleKeyGenSubmit} className="mt-4 pt-4 border-t border-slate-700">
                  <label className="block text-sm font-medium mb-2 text-slate-300">New Key Name</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="e.g., my-project-key"
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      className="flex-grow p-2.5 rounded-lg bg-slate-700 border border-slate-600 text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all"
                      required
                    />
                    <button
                      type="submit"
                      disabled={keyLoading}
                      className="bg-cyan-600 hover:bg-cyan-500 text-white font-semibold py-2 px-6 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {keyLoading ? <Loader className="w-5 h-5 animate-spin" /> : 'Create'}
                    </button>
                  </div>
                </form>
              )}
              {downloadLink && (
                <div className="mt-3 text-center">
                  <a
                    href={downloadLink}
                    download={newKeyName}
                    className="text-green-400 hover:text-green-300 font-semibold transition-colors"
                  >
                    Download your new key: {newKeyName}
                  </a>
                </div>
              )}
            </div>
          </div>

          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-300">Username</label>
            <input
              name="username"
              value={vmData.username}
              onChange={handleChange}
              className="w-full p-2.5 rounded-lg bg-slate-700 border border-slate-600 text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold mb-2 text-slate-300">RAM (MB)</label>
              <input
                name="ram"
                type="number"
                value={vmData.ram}
                onChange={handleChange}
                className="w-full p-2.5 rounded-lg bg-slate-700 border border-slate-600 text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-semibold mb-2 text-slate-300">CPU Cores</label>
              <input
                name="cpu"
                type="number"
                value={vmData.cpu}
                onChange={handleChange}
                className="w-full p-2.5 rounded-lg bg-slate-700 border border-slate-600 text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-300">Vagrant Box Image</label>
            <select
              name="image"
              value={vmData.image}
              onChange={handleChange}
              className="w-full p-2.5 rounded-lg bg-slate-700 border border-slate-600 text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all"
            >
              <option value="ubuntu/focal64">Ubuntu 20.04</option>
              <option value="generic/debian11">Debian 11</option>
              <option value="almalinux/8">AlmaLinux 8</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-300">Provisioning Script (Optional)</label>
            <textarea
              name="provisioning_script"
              value={vmData.provisioning_script}
              onChange={handleChange}
              rows="5"
              className="w-full p-2.5 rounded-lg bg-slate-700 border border-slate-600 text-white font-mono text-sm focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="mt-6 bg-cyan-500 hover:bg-cyan-400 text-white font-bold py-3 px-6 rounded-lg w-full text-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <>
                <Loader className="w-5 h-5 animate-spin" />
                Provisioning...
              </>
            ) : (
              <>
                <Plus className="w-5 h-5" />
                Create VM
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

const CreateKeyModal = ({ onClose, onKeyCreated }) => {
  const [newKeyName, setNewKeyName] = useState('');
  const [downloadLink, setDownloadLink] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      await generateKey(newKeyName);
      setDownloadLink(downloadKeyURL(newKeyName));
      alert(`Key '${newKeyName}' generated! Don't forget to download it.`);
      onKeyCreated();
    } catch (error) {
      alert('Error generating key: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex justify-center items-center z-50 p-4">
      <div className="bg-slate-800 p-8 rounded-xl shadow-2xl w-full max-w-md border border-slate-700">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-cyan-400">Create SSH Key</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-semibold mb-2 text-slate-300">Key Name</label>
            <input
              type="text"
              placeholder="e.g., my-project-key"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              className="w-full p-2.5 rounded-lg bg-slate-700 border border-slate-600 text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all"
              required
            />
          </div>

          {downloadLink && (
            <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
              <a
                href={downloadLink}
                download={newKeyName}
                className="text-green-400 hover:text-green-300 font-semibold transition-colors flex items-center justify-center gap-2"
              >
                <Key className="w-4 h-4" />
                Download {newKeyName}
              </a>
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="bg-cyan-500 hover:bg-cyan-400 text-white font-bold py-3 px-6 rounded-lg w-full transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <>
                <Loader className="w-5 h-5 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Plus className="w-5 h-5" />
                Create Key
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

const SecurityGroupModal = ({ vm, onClose, onUpdate }) => {
  const [port, setPort] = useState('');
  const [description, setDescription] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleAddRule = async (e) => {
    e.preventDefault();
    if (!port || port < 1 || port > 65535) {
      alert("Please enter a valid port number (1-65535).");
      return;
    }
    setIsLoading(true);
    try {
      await addInboundRule(vm.username, parseInt(port), description);
      alert(`Successfully added rule for port ${port}.`);
      setPort('');
      setDescription('');
      onUpdate();
    } catch (error) {
      alert("Error adding rule: " + (error.response?.data?.detail || error.message));
    } finally {
      setIsLoading(false);
    }
  };

  const handleRemoveRule = async (ruleToRemove) => {
    if (!window.confirm(`Are you sure you want to remove the rule for public port ${ruleToRemove.remotePort}?`)) {
      return;
    }

    setIsLoading(true);
    try {
      await removeInboundRule(vm.username, ruleToRemove.remotePort);
      alert(`Successfully removed rule for port ${ruleToRemove.remotePort}.`);
      onUpdate();
    } catch (error) {
      alert("Error removing rule: " + (error.response?.data?.detail || error.message));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex justify-center items-center z-50 p-4">
      <div className="bg-slate-800 p-8 rounded-xl shadow-2xl w-full max-w-2xl border border-slate-700">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-cyan-400 flex items-center gap-2">
            <Shield className="w-5 h-5" />
            Firewall Rules for <span className="text-white">{vm.username}</span>
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="space-y-3 mb-6 max-h-72 overflow-y-auto pr-2">
          <h3 className="font-semibold text-slate-300">Current Rules:</h3>
          {vm.inbound_rules.map(rule => (
            <div
              key={rule.remotePort}
              className="bg-slate-900/50 p-4 rounded-lg border border-slate-700 hover:border-cyan-500 transition-all duration-200 flex justify-between items-center text-sm"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-cyan-300 font-semibold">Port {rule.remotePort}</span>
                  <span className="text-slate-500">&rarr;</span>
                  <span className="font-mono text-slate-300">VM Port {rule.vm_port}</span>
                </div>
                <p className="text-slate-400 text-xs mt-1">{rule.description || rule.type}</p>
              </div>
              <button
                onClick={() => handleRemoveRule(rule)}
                disabled={isLoading}
                className="text-red-400 hover:text-red-300 transition-colors ml-4 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>

        <form onSubmit={handleAddRule} className="border-t border-slate-700 pt-6 space-y-4">
          <h3 className="font-semibold text-slate-300">Add New Inbound Rule:</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <input
              type="number"
              placeholder="VM Port (e.g., 8080)"
              value={port}
              onChange={(e) => setPort(e.target.value)}
              className="p-2.5 rounded-lg bg-slate-700 border border-slate-600 text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all"
              required
            />
            <input
              type="text"
              placeholder="Description (e.g., Web App)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="p-2.5 rounded-lg bg-slate-700 border border-slate-600 text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition-all md:col-span-2"
              required
            />
          </div>
          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-cyan-500 hover:bg-cyan-400 text-white font-semibold py-2.5 px-4 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <>
                <Loader className="w-4 h-4 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                Add Rule
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

const DashboardPage = () => {
  const [vms, setVms] = useState({});
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isCreateVMModalOpen, setIsCreateVMModalOpen] = useState(false);
  const [isCreateKeyModalOpen, setIsCreateKeyModalOpen] = useState(false);
  const [selectedVmForFirewall, setSelectedVmForFirewall] = useState(null);

  const fetchVMs = useCallback(async () => {
    try {
      setLoading(true);
      const response = await listVMs();
      setVms(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to fetch VMs. Is the backend server running?');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchKeys = useCallback(async () => {
    try {
      const response = await listKeys();
      setKeys(response.data);
    } catch (err) {
      console.error("Failed to fetch SSH keys:", err);
    }
  }, []);

  useEffect(() => {
    fetchVMs();
    fetchKeys();
  }, [fetchVMs, fetchKeys]);

  const handleVMCreated = () => {
    setIsCreateVMModalOpen(false);
    setTimeout(fetchVMs, 2000);
  };

  const handleKeyCreated = () => {
    setIsCreateKeyModalOpen(false);
    fetchKeys();
  };

  const handleFirewallUpdate = () => {
    setSelectedVmForFirewall(null);
    fetchVMs();
  };

  const handleAction = async (actionFunc, username, actionName) => {
    if (actionName === 'delete' && !window.confirm(`Are you sure you want to delete ${username}? This action is irreversible.`)) {
      return;
    }

    try {
      alert(`The '${actionName}' process for ${username} has started. This may take a moment.`);
      await actionFunc(username);
      alert(`VM ${username} ${actionName}d successfully!`);
      fetchVMs();
    } catch (err) {
      const errorMessage = err.response?.data?.detail || `Failed to ${actionName} VM.`;
      alert(`Error: ${errorMessage}`);
      console.error(err);
    }
  };

  const handleDeleteKey = async (keyName) => {
    if (!window.confirm(`Are you sure you want to delete the key "${keyName}"?`)) {
      return;
    }
    alert('Key deletion is not implemented in the backend yet.');
  };

  return (
    <div className="min-h-screen bg-slate-900 text-white" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
          <h1 className="text-4xl font-bold text-white">Dashboard</h1>
          <div className="flex gap-3">
            <button
              onClick={() => setIsCreateKeyModalOpen(true)}
              className="bg-slate-700 hover:bg-slate-600 text-white font-semibold py-2.5 px-5 rounded-lg shadow-lg transition-all duration-200 flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Create SSH Key
            </button>
            <button
              onClick={() => setIsCreateVMModalOpen(true)}
              className="bg-cyan-500 hover:bg-cyan-400 text-white font-semibold py-2.5 px-5 rounded-lg shadow-lg transition-all duration-200 flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Create VM
            </button>
          </div>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader className="w-8 h-8 animate-spin text-cyan-400" />
            <span className="ml-3 text-slate-400">Loading your resources...</span>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6">
            <p className="text-red-400">{error}</p>
          </div>
        )}

        {!loading && Object.keys(vms).length === 0 && (
          <div className="text-center py-20 bg-slate-800/50 rounded-xl border border-slate-700">
            <h2 className="text-2xl font-semibold text-slate-300">No Virtual Machines Found</h2>
            <p className="text-slate-400 mt-3">Click "Create VM" to get started with your first virtual machine!</p>
          </div>
        )}

        {!loading && Object.keys(vms).length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <h2 className="text-2xl font-bold mb-4 text-white">Virtual Machines</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {Object.entries(vms).map(([username, vmDetails]) => (
                  <VMCard
                    key={username}
                    vm={vmDetails}
                    onDelete={() => handleAction(deleteVM, username, 'delete')}
                    onStart={() => handleAction(startVM, username, 'start')}
                    onStop={() => handleAction(stopVM, username, 'stop')}
                    onManageFirewall={() => setSelectedVmForFirewall(vmDetails)}
                  />
                ))}
              </div>
            </div>

            <div>
              <SSHKeyList keys={keys} onDelete={handleDeleteKey} />
            </div>
          </div>
        )}
      </div>

      {isCreateVMModalOpen && (
        <CreateVMModal
          onClose={() => setIsCreateVMModalOpen(false)}
          onVMCreated={handleVMCreated}
        />
      )}

      {isCreateKeyModalOpen && (
        <CreateKeyModal
          onClose={() => setIsCreateKeyModalOpen(false)}
          onKeyCreated={handleKeyCreated}
        />
      )}

      {selectedVmForFirewall && (
        <SecurityGroupModal
          vm={selectedVmForFirewall}
          onClose={() => setSelectedVmForFirewall(null)}
          onUpdate={handleFirewallUpdate}
        />
      )}
    </div>
  );
};

export default DashboardPage;
