import { useState } from "react";
import { api, VM } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Server, Play, Square, Trash2, Cpu, HardDrive, Network, ChevronDown, ChevronUp } from "lucide-react";
import { NetworkRulesSection } from "./NetworkRulesSection";
import { Copy } from "lucide-react";


interface VMCardProps {
  vm: VM;
  onDelete: () => void;
  onUpdate: () => void;
}

export function VMCard({ vm, onDelete, onUpdate }: VMCardProps) {
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const handleStart = async () => {
    setLoading(true);
    try {
      await api.startVM(vm.name);
      toast.success(`VM ${vm.name} is starting...`);
      onUpdate();
    } catch (error: any) {
      toast.error(error.message || "Failed to start VM");
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await api.stopVM(vm.name);
      toast.success(`VM ${vm.name} is stopping...`);
      onUpdate();
    } catch (error: any) {
      toast.error(error.message || "Failed to stop VM");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Are you sure you want to delete VM "${vm.name}"? This action cannot be undone.`)) {
      return;
    }

    setLoading(true);
    try {
      await api.deleteVM(vm.name);
      toast.success(`VM ${vm.name} deletion scheduled`);
      onDelete();
    } catch (error: any) {
      toast.error(error.message || "Failed to delete VM");
    } finally {
      setLoading(false);
    }
  };

  const sshRule = vm.inbound_rules?.find(rule => rule.type === "ssh" || rule.vm_port === 22);
  const sshPort = sshRule?.remotePort;

  return (
    <Card className="border-border/50 shadow-card hover:shadow-glow transition-all duration-300 gradient-card">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
              <Server className="w-5 h-5 text-accent" />
            </div>
            <div>
              <CardTitle className="text-lg">{vm.name}</CardTitle>
              <p className="text-sm text-muted-foreground">{vm.image}</p>
            </div>
          </div>
          <Badge variant="outline" className="border-success/50 text-success">
            Active
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex items-center gap-2 text-sm">
            <Cpu className="w-4 h-4 text-muted-foreground" />
            <span className="text-muted-foreground">{vm.cpu} CPU</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <HardDrive className="w-4 h-4 text-muted-foreground" />
            <span className="text-muted-foreground">{vm.ram} MB</span>
          </div>
          <div className="flex items-center gap-2 text-sm col-span-2">
            <Network className="w-4 h-4 text-muted-foreground" />
            <span className="text-muted-foreground">{vm.private_ip}</span>
          </div>
        </div>

        {sshPort && (
  <div className="p-3 bg-muted/50 rounded-lg flex flex-col gap-2">
    <div className="flex items-center justify-between">
      <p className="text-xs text-muted-foreground">SSH Connection:</p>
      <Button
  variant="ghost"
  size="sm"
  className="h-6 px-2 text-xs hover:bg-primary/10"
  onClick={() => {
    navigator.clipboard.writeText(
      `ssh -i ${vm.key_name} ${vm.name}@13.233.204.203 -p ${sshPort}`
    );
    toast.success("SSH command copied!");
  }}
>
  <Copy className="w-3 h-3 mr-1" />
</Button>
    </div>
    <code className="text-xs font-mono text-foreground break-all">
      ssh -i {vm.key_name} {vm.name}@13.233.204.203 -p {sshPort}
    </code>
  </div>
)}

        <div className="flex flex-col gap-2">
          <Button
            onClick={() => setExpanded(!expanded)}
            variant="outline"
            size="sm"
            className="w-full justify-between"
          >
            <span>Network Rules ({vm.inbound_rules?.length || 0})</span>
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </Button>

          {expanded && (
            <NetworkRulesSection vm={vm} onUpdate={onUpdate} />
          )}
        </div>

        <div className="grid grid-cols-3 gap-2 pt-2">
          <Button onClick={handleStart} disabled={loading} size="sm" variant="outline" className="border-success/50 hover:bg-success/10">
            <Play className="w-4 h-4" />
          </Button>
          <Button onClick={handleStop} disabled={loading} size="sm" variant="outline" className="border-warning/50 hover:bg-warning/10">
            <Square className="w-4 h-4" />
          </Button>
          <Button onClick={handleDelete} disabled={loading} size="sm" variant="outline" className="border-destructive/50 hover:bg-destructive/10">
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
