import { useState, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { api, VM } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { Cloud, LogOut, Plus, Server, Key } from "lucide-react";
import { VMCard } from "@/components/VMCard";
import { CreateVMDialog } from "@/components/CreateVMDialog";
import { SSHKeysDialog } from "@/components/SSHKeysDialog";
import { useNavigate } from "react-router-dom";

export default function Dashboard() {
  const [vms, setVms] = useState<VM[]>([]);
  const [loading, setLoading] = useState(true);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [keysDialogOpen, setKeysDialogOpen] = useState(false);
  const { logout } = useAuth();
  const navigate = useNavigate();

  const loadVMs = async () => {
    try {
      const data = await api.listVMs();
      setVms(data);
    } catch (error: any) {
      toast.error("Failed to load VMs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
  loadVMs(); // initial fetch

  // 🔁 Poll every 5 seconds to refresh VM status
  const interval = setInterval(() => {
    loadVMs();
  }, 40000);

  // Cleanup when component unmounts
  return () => clearInterval(interval);
}, []);

  const handleLogout = async () => {
    try {
      await logout();
      toast.success("Logged out successfully");
      navigate("/login"); // ✅ redirect to login page
    } catch (error) {
      toast.error("Logout failed");
    }
  };

  const handleVMCreated = () => {
    setCreateDialogOpen(false);
    loadVMs();
  };

  const handleVMDeleted = () => {
    loadVMs();
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-border/50 bg-card/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl gradient-primary flex items-center justify-center shadow-glow">
              <Cloud className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold">Nimbus IaaS</h1>
              <p className="text-xs text-muted-foreground">Cloud Infrastructure Management</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={() => setKeysDialogOpen(true)} variant="outline" size="sm">
              <Key className="w-4 h-4 mr-2" />
              SSH Keys
            </Button>
            <Button onClick={handleLogout} variant="outline" size="sm">
              <LogOut className="w-4 h-4 mr-2" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h2 className="text-3xl font-bold mb-2">Virtual Machines</h2>
            <p className="text-muted-foreground">Manage and monitor your cloud infrastructure</p>
          </div>
          <Button onClick={() => setCreateDialogOpen(true)} className="gradient-primary font-semibold shadow-glow">
            <Plus className="w-4 h-4 mr-2" />
            Create VM
          </Button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="text-center">
              <div className="h-12 w-12 animate-spin rounded-full border-4 border-accent border-t-transparent mx-auto mb-4" />
              <p className="text-muted-foreground">Loading your VMs...</p>
            </div>
          </div>
        ) : vms.length === 0 ? (
          <Card className="border-border/50 shadow-card">
            <CardHeader className="text-center pb-4">
              <div className="mx-auto w-16 h-16 rounded-2xl bg-muted/50 flex items-center justify-center mb-4">
                <Server className="w-8 h-8 text-muted-foreground" />
              </div>
              <CardTitle>No Virtual Machines</CardTitle>
              <CardDescription>Get started by creating your first VM</CardDescription>
            </CardHeader>
            <CardContent className="text-center pb-8">
              <Button onClick={() => setCreateDialogOpen(true)} className="gradient-primary font-semibold">
                <Plus className="w-4 h-4 mr-2" />
                Create Your First VM
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {vms.map((vm) => (
              <VMCard key={vm.id} vm={vm} onDelete={handleVMDeleted} onUpdate={loadVMs} />
            ))}
          </div>
        )}
      </main>

      <CreateVMDialog open={createDialogOpen} onOpenChange={setCreateDialogOpen} onSuccess={handleVMCreated} />
      <SSHKeysDialog open={keysDialogOpen} onOpenChange={setKeysDialogOpen} />
    </div>
  );
}
