import React from 'react';
import { User } from '../../types';
import { Code2, Settings as SettingsIcon, LogOut, User as UserIcon } from 'lucide-react';

interface TopBarProps {
  currentPage?: string;
  user: User;
  onSettingsClick?: () => void;
  onLogout: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  currentPage = 'Projects',
  user,
  onSettingsClick,
  onLogout,
}) => {
  return (
    <header className="h-14 bg-vscode-topbar border-b border-vscode-border px-4 flex items-center justify-between select-none">
      {/* Left: Branding & Current Page */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2 text-vscode-accent">
          <Code2 className="w-5 h-5" />
          <span className="font-semibold text-base text-white tracking-wide">Cloud IDE</span>
        </div>
        <span className="text-vscode-border">/</span>
        <span className="text-xs font-medium text-vscode-text">{currentPage}</span>
      </div>

      {/* Right: Real Authenticated User Display, Settings, Logout */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2 border-l border-vscode-border pl-3">
          {user.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user.username}
              className="w-7 h-7 rounded-full border border-vscode-border object-cover"
            />
          ) : (
            <div className="w-7 h-7 rounded-full bg-vscode-badge flex items-center justify-center text-vscode-text-muted border border-vscode-border">
              <UserIcon className="w-4 h-4" />
            </div>
          )}
          <span className="text-xs font-medium text-white">{user.username}</span>
        </div>

        <button
          onClick={onSettingsClick || (() => alert('Settings menu (UI placeholder)'))}
          className="p-1.5 text-vscode-text-muted hover:text-white hover:bg-vscode-border rounded transition-colors"
          title="Settings"
        >
          <SettingsIcon className="w-4 h-4" />
        </button>

        <button
          onClick={onLogout}
          className="p-1.5 text-vscode-text-muted hover:text-white hover:bg-vscode-border rounded transition-colors"
          title="Sign Out"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
