import React from 'react';
import { FolderGit2, HardDrive, Settings, BookOpen } from 'lucide-react';

interface SidebarProps {
  activeTab?: string;
  onTabChange?: (tab: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab = 'Projects',
  onTabChange,
}) => {
  const items = [
    { name: 'Projects', icon: FolderGit2 },
    { name: 'Workspaces', icon: HardDrive },
    { name: 'Settings', icon: Settings },
    { name: 'Docs', icon: BookOpen },
  ];

  return (
    <aside className="w-16 bg-vscode-sidebar border-r border-vscode-border flex flex-col items-center py-4 space-y-4 select-none">
      {items.map((item) => {
        const Icon = item.icon;
        const isActive = activeTab === item.name;
        return (
          <button
            key={item.name}
            onClick={() => onTabChange ? onTabChange(item.name) : alert(`${item.name} (UI placeholder)`)}
            className={`p-3 rounded-lg transition-colors relative ${
              isActive
                ? 'text-white bg-vscode-badge/60'
                : 'text-vscode-text-muted hover:text-white hover:bg-vscode-badge/30'
            }`}
            title={item.name}
          >
            <Icon className="w-5 h-5" />
            {isActive && (
              <div className="absolute left-0 top-2 bottom-2 w-0.5 bg-vscode-accent rounded-r" />
            )}
          </button>
        );
      })}
    </aside>
  );
};
