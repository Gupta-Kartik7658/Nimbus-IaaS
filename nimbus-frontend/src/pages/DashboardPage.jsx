import React, { useState, useEffect, useCallback } from 'react';
import { listVMs, deleteVM, startVM, stopVM } from '../api/apiClient';
import VMCard from '../components/VMCard';
import CreateVMModal from '../components/CreateVMModal';
import SecurityGroupModal from '../components/SecurityGroupModal'; // NEW

const DashboardPage = () => {
  const [vms, setVms] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [selectedVmForFirewall, setSelectedVmForFirewall] = useState(null); // NEW

  const fetchVMs = useCallback(async () => {
    // No changes here
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

  useEffect(() => {
    fetchVMs();
  }, [fetchVMs]);
  
  const handleVMCreated = () => {
    setIsCreateModalOpen(false);
    setTimeout(fetchVMs, 2000);
  };
  
  // NEW: Handler for when a firewall rule is updated
  const handleFirewallUpdate = () => {
    setSelectedVmForFirewall(null); // Close the modal
    fetchVMs(); // Refresh the list
  }

  const handleAction = async (actionFunc, username, actionName) => {
    // No changes here
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

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold">Your Nimbus-VMs</h1>
        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="bg-cyan-500 hover:bg-cyan-400 text-white font-bold py-2 px-4 rounded-lg shadow-lg transition duration-300"
        >
          + Create New Nimbus-VM
        </button>
      </div>

      {/* No changes to loading/error/empty state display */}
      {loading && <p>Loading your VMs...</p>}
      {error && <p className="text-red-400">{error}</p>}
      {!loading && Object.keys(vms).length === 0 && (
         <div className="text-center py-20 bg-gray-800/50 rounded-lg">
            <h2 className="text-xl font-semibold">No VMs Found</h2>
            <p className="text-gray-400 mt-2">Click "Create New Nimbus-VM" to get started!</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {Object.entries(vms).map(([username, vmDetails]) => (
          <VMCard 
            key={username} 
            vm={vmDetails}
            onDelete={() => handleAction(deleteVM, username, 'delete')}
            onStart={() => handleAction(startVM, username, 'start')}
            onStop={() => handleAction(stopVM, username, 'stop')}
            onManageFirewall={() => setSelectedVmForFirewall(vmDetails)} // NEW
          />
        ))}
      </div>
      
      {isCreateModalOpen && <CreateVMModal onClose={() => setIsCreateModalOpen(false)} onVMCreated={handleVMCreated} />}
      
      {/* NEW: Render the security group modal when a VM is selected */}
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