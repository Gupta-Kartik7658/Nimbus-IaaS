import React, { useState, useEffect } from 'react';
import { createVM, generateKey, downloadKeyURL, listKeys } from '../api/apiClient';

const CreateVMModal = ({ onClose, onVMCreated }) => {
  // State for the main VM form
  const [vmData, setVmData] = useState({
    username: '',
    key_name: '',
    ram: 1024,
    cpu: 1,
    image: 'ubuntu/focal64',
    provisioning_script: '#!/bin/bash\n# Your script here, e.g.\n# sudo apt-get update\n# sudo apt-get install -y nginx',
  });
  
  // State for key management
  const [availableKeys, setAvailableKeys] = useState([]);
  const [showNewKeyForm, setShowNewKeyForm] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [downloadLink, setDownloadLink] = useState('');

  const [isLoading, setIsLoading] = useState(false);
  const [keyLoading, setKeyLoading] = useState(false);

  // Fetch existing keys when the component mounts
  useEffect(() => {
    const fetchKeys = async () => {
      try {
        const response = await listKeys();
        setAvailableKeys(response.data);
        // If keys exist, pre-select the first one
        if (response.data.length > 0) {
          // We remove the .pub extension for the key_name
          const keyNameWithoutExt = response.data[0].replace('.pub', '');
          setVmData(prev => ({ ...prev, key_name: keyNameWithoutExt }));
        } else {
          // If no keys exist, automatically show the form to create one
          setShowNewKeyForm(true);
        }
      } catch (error) {
        console.error("Failed to fetch SSH keys:", error);
        setShowNewKeyForm(true); // Show form if fetching fails
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
      // Add the new key to our list and select it
      setAvailableKeys(prev => [...prev, `${newKeyName}.pub`]);
      setVmData(prev => ({ ...prev, key_name: newKeyName }));
      setShowNewKeyForm(false); // Hide the form after success
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
      // The default SSH rule is added here before sending
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
    <div className="fixed inset-0 bg-black bg-opacity-70 flex justify-center items-center z-50">
      <div className="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-2xl border border-gray-600">
        <div className="flex justify-between items-center mb-6">
            <h2 className="text-2xl font-bold text-cyan-400">Create Your Nimbus-VM</h2>
            <button onClick={onClose} className="font-bold text-2xl leading-none">&times;</button>
        </div>
        
        <form onSubmit={handleVMSubmit} className="space-y-4">
          {/* SSH Key Section */}
          <div>
            <label className="font-semibold">SSH Key</label>
            <div className="mt-2 p-4 bg-gray-900/50 rounded-lg">
              <select 
                name="key_name" 
                value={vmData.key_name} 
                onChange={(e) => setVmData(prev => ({...prev, key_name: e.target.value}))}
                className="w-full p-2 rounded bg-gray-700 border border-gray-600"
              >
                <option value="" disabled>-- Select a key --</option>
                {availableKeys.map(keyFile => {
                  const keyName = keyFile.replace('.pub', '');
                  return <option key={keyName} value={keyName}>{keyName}</option>
                })}
              </select>

              {!showNewKeyForm ? (
                // UPDATED: Wrapped button in a div for centering and removed the comma
                <div className="text-center mt-2">
                  <button type="button" onClick={() => setShowNewKeyForm(true)} className="text-cyan-400 text-sm hover:underline">
                    Or generate a new SSH key...
                  </button>
                </div>
              ) : (
                <form onSubmit={handleKeyGenSubmit} className="mt-4 p-4 border-t border-gray-600">
                  <label className="block text-sm mb-1">New Key Name</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="e.g., my-project-key"
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      className="flex-grow p-2 rounded bg-gray-600 border border-gray-500"
                      required
                    />
                    <button type="submit" disabled={keyLoading} className="bg-cyan-600 hover:bg-cyan-500 text-white font-bold py-2 px-4 rounded">
                      {keyLoading ? '...' : 'Create'}
                    </button>
                  </div>
                </form>
              )}
               {downloadLink && (
                  <div className="mt-3 text-center">
                    <a href={downloadLink} download={newKeyName} className="text-green-400 hover:underline font-bold">
                      Download your new key: {newKeyName}
                    </a>
                  </div>
                )}
            </div>
          </div>

          {/* VM Details Section */}
          <div>
              <label>Username</label>
              <input name="username" value={vmData.username} onChange={handleChange} className="w-full p-2 rounded bg-gray-700 border border-gray-600" required />
          </div>
          <div className="grid grid-cols-2 gap-4">
              <div>
                  <label>RAM (MB)</label>
                  <input name="ram" type="number" value={vmData.ram} onChange={handleChange} className="w-full p-2 rounded bg-gray-700 border border-gray-600" required />
              </div>
              <div>
                  <label>CPU Cores</label>
                  <input name="cpu" type="number" value={vmData.cpu} onChange={handleChange} className="w-full p-2 rounded bg-gray-700 border border-gray-600" required />
              </div>
          </div>
          <div>
              <label>Vagrant Box Image</label>
              <select name="image" value={vmData.image} onChange={handleChange} className="w-full p-2 rounded bg-gray-700 border border-gray-600">
                  <option value="ubuntu/focal64">Ubuntu 20.04</option>
                  <option value="generic/debian11">Debian 11</option>
                  <option value="almalinux/8">AlmaLinux 8</option>
              </select>
          </div>
          <div>
              <label>Provisioning Script (Optional)</label>
              <textarea name="provisioning_script" value={vmData.provisioning_script} onChange={handleChange} rows="5" className="w-full p-2 rounded bg-gray-700 border border-gray-600 font-mono text-sm"></textarea>
          </div>
          
          <button type="submit" disabled={isLoading} className="mt-6 bg-cyan-500 hover:bg-cyan-400 text-white font-bold py-3 px-4 rounded w-full text-lg">
              {isLoading ? 'Provisioning...' : '🚀 Create VM'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default CreateVMModal;