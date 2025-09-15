import React, { useState } from 'react';
// NEW: import removeInboundRule
import { addInboundRule, removeInboundRule } from '../api/apiClient';

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
      onUpdate(); 
    } catch (error) {
      alert("Error adding rule: " + (error.response?.data?.detail || error.message));
    } finally {
      setIsLoading(false);
    }
  };

  // NEW: Handler for removing a rule
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
       alert("Error removing rule: " + (error.response?.data?.detail || error.message) + "\n\nNote: This feature requires a backend endpoint.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-70 flex justify-center items-center z-50">
      <div className="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-lg border border-gray-600">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-cyan-400">
            Firewall Rules for <span className="text-white">{vm.username}</span>
          </h2>
          <button onClick={onClose} className="font-bold text-2xl leading-none">&times;</button>
        </div>

        {/* List existing rules */}
        <div className="space-y-2 mb-6 max-h-60 overflow-y-auto pr-2">
          <h3 className="font-semibold">Current Rules:</h3>
          {vm.inbound_rules.map(rule => (
            <div key={rule.remotePort} className="bg-gray-700/50 p-3 rounded-lg flex justify-between items-center text-sm">
              <div className="flex-1">
                <span className="font-mono text-cyan-300">Port {rule.remotePort}</span>
                <span className="text-gray-400 mx-2">&rarr;</span>
                <span className="font-mono">VM Port {rule.vm_port}</span>
              </div>
              <span className="text-gray-400 truncate mx-4 flex-1">{rule.description || rule.type}</span>
              {/* NEW: Remove button */}
              <button 
                onClick={() => handleRemoveRule(rule)} 
                disabled={isLoading}
                className="text-red-400 hover:text-red-300 font-bold text-lg leading-none"
              >
                &times;
              </button>
            </div>
          ))}
        </div>

        {/* Add new rule form */}
        <form onSubmit={handleAddRule} className="border-t border-gray-600 pt-4">
          <h3 className="font-semibold mb-2">Add New Inbound Rule:</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <input 
              type="number"
              placeholder="VM Port (e.g., 8080)"
              value={port}
              onChange={(e) => setPort(e.target.value)}
              className="p-2 rounded bg-gray-700 border border-gray-600"
              required
            />
            <input 
              type="text"
              placeholder="Description (e.g., Web App)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="p-2 rounded bg-gray-700 border border-gray-600 md:col-span-2"
              required
            />
          </div>
          <button type="submit" disabled={isLoading} className="mt-4 w-full bg-cyan-500 hover:bg-cyan-400 text-white font-bold py-2 px-4 rounded">
            {isLoading ? 'Processing...' : '+ Add Rule'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default SecurityGroupModal;