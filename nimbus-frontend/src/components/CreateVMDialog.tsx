import { useState, useEffect } from "react";
import { api, SSHKey } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";

interface CreateVMDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

const OS_IMAGES = [
  { value: "ubuntu/jammy64", label: "Ubuntu 22.04 (Jammy)" },
  { value: "ubuntu/focal64", label: "Ubuntu 20.04 (Focal)" },
  { value: "debian/bullseye64", label: "Debian 11 (Bullseye)" },
  { value: "centos/stream9", label: "CentOS Stream 9" },
];

export function CreateVMDialog({ open, onOpenChange, onSuccess }: CreateVMDialogProps) {
  const [loading, setLoading] = useState(false);
  const [keys, setKeys] = useState<SSHKey[]>([]);
  const [formData, setFormData] = useState({
    name: "",
    key_name: "",
    ram: "2048",
    cpu: "2",
    image: "ubuntu/jammy64",
    provisioning_script: "",
  });

  useEffect(() => {
    if (open) {
      loadKeys();
    }
  }, [open]);

  const loadKeys = async () => {
    try {
      const data = await api.listKeys();
      setKeys(data);
    } catch (error) {
      toast.error("Failed to load SSH keys");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.name || !formData.key_name) {
      toast.error("Please fill in all required fields");
      return;
    }

    setLoading(true);
    try {
      const result = await api.createVM({
        username: formData.name,
        key_name: formData.key_name,
        ram: parseInt(formData.ram),
        cpu: parseInt(formData.cpu),
        image: formData.image,
        inbound_rules: [{ type: "tcp", vm_port: 22, description: "SSH Access" }],
        provisioning_script: formData.provisioning_script || undefined,
      });
      
      toast.success("VM creation started!");
      if (result && typeof result === "object" && "message" in result) {
        toast.info(String(result.message), { duration: 10000 });
      }
      onSuccess();
      setFormData({
        name: "",
        key_name: "",
        ram: "2048",
        cpu: "2",
        image: "ubuntu/jammy64",
        provisioning_script: "",
      });
    } catch (error: any) {
      toast.error(error.message || "Failed to create VM");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create Virtual Machine</DialogTitle>
          <DialogDescription>Configure your new VM instance</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="name">VM Name *</Label>
              <Input
                id="name"
                placeholder="my-vm"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="key_name">SSH Key *</Label>
              <Select value={formData.key_name} onValueChange={(value) => setFormData({ ...formData, key_name: value })}>
                <SelectTrigger>
                  <SelectValue placeholder="Select SSH key" />
                </SelectTrigger>
                <SelectContent>
                  {keys.length === 0 ? (
                    <div className="p-2 text-sm text-muted-foreground">No SSH keys found. Create one first.</div>
                  ) : (
                    keys.map((key) => (
                      <SelectItem key={key.name} value={key.name}>
                        {key.name}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="image">Operating System</Label>
            <Select value={formData.image} onValueChange={(value) => setFormData({ ...formData, image: value })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {OS_IMAGES.map((img) => (
                  <SelectItem key={img.value} value={img.value}>
                    {img.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="cpu">CPU Cores</Label>
              <Input
                id="cpu"
                type="number"
                min="1"
                max="16"
                value={formData.cpu}
                onChange={(e) => setFormData({ ...formData, cpu: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="ram">RAM (MB)</Label>
              <Input
                id="ram"
                type="number"
                min="512"
                step="512"
                value={formData.ram}
                onChange={(e) => setFormData({ ...formData, ram: e.target.value })}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="script">Provisioning Script (Optional)</Label>
            <Textarea
              id="script"
              placeholder="#!/bin/bash&#10;apt-get update&#10;apt-get install -y nginx"
              value={formData.provisioning_script}
              onChange={(e) => setFormData({ ...formData, provisioning_script: e.target.value })}
              rows={5}
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Bash script to run after VM creation. Will execute as the VM user.
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading} className="gradient-primary">
              {loading ? "Creating..." : "Create VM"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
