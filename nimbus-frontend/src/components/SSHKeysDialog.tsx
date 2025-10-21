import { useState, useEffect } from "react";
import { api, SSHKey } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Key, Download, Trash2, Plus } from "lucide-react";

interface SSHKeysDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SSHKeysDialog({ open, onOpenChange }: SSHKeysDialogProps) {
  const [keys, setKeys] = useState<SSHKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    if (open) {
      loadKeys();
    }
  }, [open]);

  const loadKeys = async () => {
    setLoading(true);
    try {
      const data = await api.listKeys();
      setKeys(data);
    } catch (error: any) {
      toast.error("Failed to load SSH keys");
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!newKeyName || !/^[a-zA-Z0-9]+$/.test(newKeyName)) {
      toast.error("Key name must be alphanumeric with no spaces");
      return;
    }

    setGenerating(true);
    try {
      await api.generateKey(newKeyName);
      toast.success(`SSH key "${newKeyName}" generated!`);
      setNewKeyName("");
      loadKeys();
    } catch (error: any) {
      toast.error(error.message || "Failed to generate key");
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async (keyName: string) => {
    try {
      await api.downloadKey(keyName);
      toast.success(`Key "${keyName}" downloaded`);
    } catch (error: any) {
      toast.error(error.message || "Failed to download key");
    }
  };

  const handleDelete = async (keyName: string) => {
    if (!confirm(`Delete SSH key "${keyName}"? VMs using this key must be deleted first.`)) {
      return;
    }

    try {
      await api.deleteKey(keyName);
      toast.success(`Key "${keyName}" deleted`);
      loadKeys();
    } catch (error: any) {
      toast.error(error.message || "Failed to delete key");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>SSH Key Management</DialogTitle>
          <DialogDescription>Generate and manage SSH keys for your VMs</DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Generate New Key */}
          <form onSubmit={handleGenerate} className="space-y-3 p-4 bg-muted/30 rounded-lg border border-border/50">
            <Label htmlFor="keyName">Generate New SSH Key</Label>
            <div className="flex gap-2">
              <Input
                id="keyName"
                placeholder="newKey"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                className="flex-1"
              />
              <Button type="submit" disabled={generating} className="gradient-primary">
                <Plus className="w-4 h-4 mr-2" />
                {generating ? "Generating..." : "Generate"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Alphanumeric characters only, no spaces
            </p>
          </form>

          {/* Keys List */}
          <div className="space-y-2">
            <Label>Your SSH Keys ({keys.length})</Label>
            {loading ? (
              <div className="flex justify-center py-8">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-accent border-t-transparent" />
              </div>
            ) : keys.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Key className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>No SSH keys found. Generate one to get started.</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {keys.map((key) => (
                  <div
                    key={key.name}
                    className="flex items-center justify-between p-3 bg-card rounded-lg border border-border/50"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-accent/20 flex items-center justify-center">
                        <Key className="w-5 h-5 text-accent" />
                      </div>
                      <div>
                        <p className="font-medium">{key.name}</p>
                        <p className="text-xs text-muted-foreground">SSH Key Pair</p>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        onClick={() => handleDownload(key.name)}
                        size="sm"
                        variant="outline"
                        className="border-accent/50 hover:bg-accent/10"
                      >
                        <Download className="w-4 h-4" />
                      </Button>
                      <Button
                        onClick={() => handleDelete(key.name)}
                        size="sm"
                        variant="outline"
                        className="border-destructive/50 hover:bg-destructive/10 text-destructive"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
