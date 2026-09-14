import React, { useState, useEffect } from 'react';
import { User } from './types';
import { getMe, logout } from './services/api';
import { Dashboard } from './pages/Dashboard';
import { Login } from './pages/Login';
import { Loader2 } from 'lucide-react';

export const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const checkAuthentication = async () => {
      try {
        const response = await getMe();
        if (response.authenticated && response.user) {
          setUser(response.user);
        } else {
          setUser(null);
        }
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    checkAuthentication();
  }, []);

  const handleLogout = async () => {
    try {
      await logout();
    } catch {
      // Even if network fails, clear local user state
    } finally {
      setUser(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-vscode-bg flex flex-col items-center justify-center space-y-3 text-vscode-text-muted select-none">
        <Loader2 className="w-8 h-8 animate-spin text-vscode-accent" />
        <p className="text-xs tracking-wider font-mono">INITIALIZING CLOUD IDE...</p>
      </div>
    );
  }

  if (!user) {
    return <Login />;
  }

  return <Dashboard user={user} onLogout={handleLogout} />;
};

export default App;
