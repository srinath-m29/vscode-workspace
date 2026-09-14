import React from 'react';
import { Code2, Shield, AlertTriangle } from 'lucide-react';
import { getLoginUrl } from '../services/api';

export const Login: React.FC = () => {
  const handleContinueWithGitHub = () => {
    window.location.href = getLoginUrl();
  };

  return (
    <div className="min-h-screen bg-vscode-bg flex flex-col justify-center items-center p-4 selection:bg-vscode-accent selection:text-white">
      <div className="max-w-md w-full bg-vscode-sidebar border border-vscode-border rounded-xl p-8 shadow-2xl space-y-6">
        {/* Branding & Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex p-3 rounded-xl bg-vscode-accent/10 border border-vscode-accent/20 text-vscode-accent mb-2">
            <Code2 className="w-8 h-8" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Cloud IDE</h1>
          <p className="text-sm text-vscode-text-muted">
            Private browser development environment
          </p>
        </div>

        {/* Access Notice */}
        <div className="bg-vscode-bg border border-vscode-border rounded-lg p-4 space-y-2 text-xs text-vscode-text-muted">
          <div className="flex items-center space-x-2 text-vscode-accent font-medium">
            <Shield className="w-4 h-4" />
            <span>Authorized Access Only</span>
          </div>
          <p className="leading-relaxed">
            Only two authorized users can access this system.
          </p>
        </div>

        {/* Temporary Storage Warning */}
        <div className="bg-vscode-warning/5 border border-vscode-warning/20 rounded-lg p-4 space-y-2 text-xs text-vscode-warning/90">
          <div className="flex items-center space-x-2 font-medium">
            <AlertTriangle className="w-4 h-4 text-vscode-warning" />
            <span>Storage Notice</span>
          </div>
          <p className="text-vscode-text-muted leading-relaxed">
            Workspace storage is temporary. Commit and push your work to GitHub to keep it permanently.
          </p>
        </div>

        {/* Action Button */}
        <div className="pt-2">
          <button
            onClick={handleContinueWithGitHub}
            className="w-full flex items-center justify-center space-x-2.5 bg-vscode-accent hover:bg-vscode-accent-hover text-white py-2.5 px-4 rounded-lg font-medium text-sm transition-all duration-150 shadow-lg shadow-vscode-accent/20 active:scale-[0.99]"
          >
            <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
              <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
            </svg>
            <span>Continue with GitHub</span>
          </button>
        </div>
      </div>

      <footer className="mt-8 text-center text-xs text-vscode-text-muted">
        Render Free Tier • ₹0 Budget Infrastructure
      </footer>
    </div>
  );
};
