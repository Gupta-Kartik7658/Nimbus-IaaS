import React from 'react';
import { publicIp } from '../api/apiClient';

const VMCard = ({ vm, onDelete, onStart, onStop, onManageFirewall }) => {
  
  // Find the primary SSH rule to create the copy command
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

  return (
    <div className="bg-gray-800/60 rounded-xl shadow-lg p-6 flex flex-col justify-between border border-gray-700 hover:border-cyan-500 transition-all duration-300">
      <div>
        {/* Header Section */}
        <div className="flex justify-between items-start">
            <h2 className="text-2xl font-bold text-cyan-400">{vm.username}</h2>
            <span className="text-xs font-mono bg-gray-700 px-2 py-1 rounded">{vm.image}</span>
        </div>
        
        {/* Specs Section */}
        <div className="text-sm text-gray-400 mt-2">
            <span>{vm.cpu} CPU(s)</span> &bull; <span>{vm.ram} MB RAM</span>
        </div>
        
        {/* REMOVED the long list of inbound rules */}

        {/* NEW: Dedicated SSH Access Section */}
        <div className="mt-4">
            <h3 className="font-semibold text-sm mb-2 text-gray-300">SSH Access</h3>
            <button 
              onClick={() => copyToClipboard(sshCommand)} 
              className="w-full text-left p-2 rounded bg-gray-900 hover:bg-gray-700 font-mono text-xs text-cyan-300 transition-colors duration-200"
            >
              {sshCommand}
            </button>
        </div>
      </div>
      
      {/* Action Buttons Section */}
      <div className="grid grid-cols-2 gap-2 mt-6">
        <button onClick={onManageFirewall} className="col-span-2 bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 px-3 rounded text-sm">
          Manage Firewall
        </button>
        <button onClick={onStart} className="bg-green-600 hover:bg-green-500 text-white font-bold py-1 px-3 rounded text-sm">Start</button>
        <button onClick={onStop} className="bg-yellow-600 hover:bg-yellow-500 text-white font-bold py-1 px-3 rounded text-sm">Stop</button>
        <button onClick={onDelete} className="col-span-2 bg-red-600 hover:bg-red-500 text-white font-bold py-1 px-3 rounded text-sm">Delete</button>
      </div>
    </div>
  );
};

export default VMCard;