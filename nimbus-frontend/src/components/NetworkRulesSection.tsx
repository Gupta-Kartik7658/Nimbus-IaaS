import { useState } from "react";
import { api, VM } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Plus, Trash2, Network } from "lucide-react";

interface NetworkRulesSectionProps {
  vm: VM;
  onUpdate: () => void;
}

export function NetworkRulesSection({ vm, onUpdate }: NetworkRulesSectionProps) {
  const [newPort, setNewPort] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [loading, setLoading] = useState(false);

  const handleAddRule = async (e: React.FormEvent) => {
    e.preventDefault();
    const port = parseInt(newPort);

    if (isNaN(port) || port < 1 || port > 65535) {
      toast.error("Port must be between 1 and 65535");
      return;
    }

    setLoading(true);
    try {
      await api.addInboundRule(port, vm.name, newDescription);
      toast.success(`Rule for port ${port} added`);
      setNewPort("");
      setNewDescription("");
      onUpdate();
    } catch (error: any) {
      toast.error(error.message || "Failed to add rule");
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveRule = async (remotePort: number) => {
    if (!confirm(`Remove rule for public port ${remotePort}?`)) {
      return;
    }

    setLoading(true);
    try {
      await api.removeInboundRule(vm.name, remotePort);
      toast.success("Rule removed");
      onUpdate();
    } catch (error: any) {
      toast.error(error.message || "Failed to remove rule");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3 p-3 bg-muted/30 rounded-lg border border-border/50">
      <div className="space-y-2">
        {vm.inbound_rules?.map((rule, index) => (
          <div
            key={index}
            className="flex items-center justify-between p-2 bg-card rounded border border-border/30"
          >
            <div className="flex items-center gap-2 flex-1">
              <Network className="w-4 h-4 text-accent" />
              <div className="flex-1">
                <p className="text-sm font-medium">
                  {rule.type.toUpperCase()} - Port {rule.vm_port}
                  {rule.remotePort && ` → ${rule.remotePort}`}
                </p>
                {rule.description && (
                  <p className="text-xs text-muted-foreground">{rule.description}</p>
                )}
              </div>
            </div>
            {rule.remotePort && (
              <Button
                onClick={() => handleRemoveRule(rule.remotePort!)}
                disabled={loading}
                size="sm"
                variant="ghost"
                className="h-8 w-8 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            )}
          </div>
        ))}
      </div>

      <form onSubmit={handleAddRule} className="space-y-3 pt-2 border-t border-border/30">
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label htmlFor={`port-${vm.id}`} className="text-xs">
              VM Port
            </Label>
            <Input
              id={`port-${vm.id}`}
              type="number"
              placeholder="8080"
              value={newPort}
              onChange={(e) => setNewPort(e.target.value)}
              min={1}
              max={65535}
              className="h-8"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`desc-${vm.id}`} className="text-xs">
              Description
            </Label>
            <Input
              id={`desc-${vm.id}`}
              type="text"
              placeholder="Web server"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              className="h-8"
            />
          </div>
        </div>
        <Button type="submit" disabled={loading} size="sm" className="w-full" variant="outline">
          <Plus className="w-4 h-4 mr-2" />
          Add Rule
        </Button>
      </form>
    </div>
  );
}
