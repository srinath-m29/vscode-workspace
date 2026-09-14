import React, { useState, useEffect, useCallback } from 'react';
import { User, Repository } from '../types';
import { TopBar } from '../components/TopBar/TopBar';
import { Sidebar } from '../components/Sidebar/Sidebar';
import { RepositoryCard } from '../components/RepositoryCard/RepositoryCard';
import { getRepositories } from '../services/github';
import { ApiError } from '../services/api';
import {
  Search,
  AlertTriangle,
  RefreshCw,
  Loader2,
  AlertCircle,
  LogIn,
  ChevronLeft,
  ChevronRight,
  FolderGit2,
} from 'lucide-react';

interface DashboardProps {
  user: User;
  onLogout: () => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ user, onLogout }) => {
  const [activeTab, setActiveTab] = useState<string>('Projects');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [debouncedQuery, setDebouncedQuery] = useState<string>('');

  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [page, setPage] = useState<number>(1);
  const [hasNextPage, setHasNextPage] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isAuthError, setIsAuthError] = useState<boolean>(false);

  // Debounce search query by 300ms to avoid excessive API requests
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery);
      setPage(1); // Reset to page 1 on new query
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  const loadRepositories = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setIsAuthError(false);
    try {
      const res = await getRepositories({
        search: debouncedQuery,
        page,
        per_page: 30,
      });
      setRepositories(res.repositories);
      setHasNextPage(res.hasNextPage);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        setIsAuthError(true);
        setError('GitHub authentication is no longer valid. Please sign in again.');
      } else if (err instanceof ApiError && err.status === 429) {
        setError('GitHub API rate limit reached. Please try again later.');
      } else if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
        setError('Unable to access this repository.');
      } else {
        setError('Unable to load GitHub data.');
      }
      setRepositories([]);
    } finally {
      setIsLoading(false);
    }
  }, [debouncedQuery, page]);

  useEffect(() => {
    loadRepositories();
  }, [loadRepositories]);

  const handleOpenIDE = (repoName: string) => {
    alert(
      `Open in IDE for ${repoName} is a placeholder for STEP 8.\nWorkspace cloning will be implemented next.`
    );
  };

  const handleDeploy = (repoName: string) => {
    alert(
      `Render deployment for ${repoName} is a placeholder for STEP 12.\nDeployment API will be integrated later.`
    );
  };

  return (
    <div className="min-h-screen bg-vscode-bg flex flex-col">
      <TopBar currentPage={activeTab} user={user} onLogout={onLogout} />

      <div className="flex-1 flex overflow-hidden">
        <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />

        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Ephemeral Storage Warning Banner */}
          <div className="bg-vscode-warning/10 border border-vscode-warning/30 rounded-lg p-4 flex items-start space-x-3 text-vscode-warning">
            <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <div className="text-xs space-y-0.5">
              <p className="font-semibold text-white">Storage Notice</p>
              <p className="text-vscode-text leading-relaxed">
                Workspace storage is temporary. Commit and push your work to GitHub to keep it permanently.
              </p>
            </div>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="bg-rose-500/10 border border-rose-500/30 rounded-lg p-4 flex items-start justify-between text-rose-400">
              <div className="flex items-start space-x-3">
                <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                <div className="text-xs">
                  <p className="font-semibold text-white">Error Loading Repositories</p>
                  <p className="mt-0.5">{error}</p>
                </div>
              </div>
              {isAuthError && (
                <a
                  href="/api/auth/login"
                  className="flex items-center space-x-1 px-3 py-1.5 bg-rose-500 text-white rounded text-xs font-medium hover:bg-rose-600 transition-colors"
                >
                  <LogIn className="w-3.5 h-3.5" />
                  <span>Sign in again</span>
                </a>
              )}
            </div>
          )}

          {/* Header & Search Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-white flex items-center space-x-2">
                <span>My Repositories</span>
                {!isLoading && (
                  <span className="text-xs font-normal text-vscode-text-muted px-2 py-0.5 rounded-full bg-vscode-badge">
                    {repositories.length} repos
                  </span>
                )}
              </h1>
              <p className="text-xs text-vscode-text-muted mt-1">
                Connected GitHub repositories accessible to {user.username}.
              </p>
            </div>

            <div className="flex items-center space-x-2">
              <div className="relative">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search repositories..."
                  className="bg-vscode-sidebar border border-vscode-border rounded-lg pl-9 pr-4 py-1.5 text-xs text-vscode-text placeholder:text-vscode-text-muted focus:outline-none focus:border-vscode-accent w-64 transition-colors"
                />
                <Search className="w-4 h-4 text-vscode-text-muted absolute left-3 top-2.5" />
              </div>

              <button
                onClick={() => {
                  setSearchQuery('');
                  loadRepositories();
                }}
                disabled={isLoading}
                className="p-2 bg-vscode-sidebar border border-vscode-border rounded-lg text-vscode-text-muted hover:text-white transition-colors disabled:opacity-50"
                title="Refresh Repositories"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-vscode-accent' : ''}`} />
              </button>
            </div>
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-20 space-y-3">
              <Loader2 className="w-8 h-8 animate-spin text-vscode-accent" />
              <p className="text-sm text-vscode-text-muted">Loading repositories...</p>
            </div>
          )}

          {/* Empty State */}
          {!isLoading && !error && repositories.length === 0 && (
            <div className="bg-vscode-sidebar border border-vscode-border rounded-lg p-12 text-center flex flex-col items-center justify-center space-y-3">
              <FolderGit2 className="w-10 h-10 text-vscode-text-muted/60" />
              <p className="text-sm text-white font-medium">No repositories found</p>
              <p className="text-xs text-vscode-text-muted max-w-sm">
                {searchQuery
                  ? `No repositories matched your search for "${searchQuery}".`
                  : "We couldn't find any GitHub repositories associated with your account."}
              </p>
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="text-xs text-vscode-accent hover:underline mt-2"
                >
                  Clear search query
                </button>
              )}
            </div>
          )}

          {/* Repositories Grid */}
          {!isLoading && !error && repositories.length > 0 && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {repositories.map((repo) => (
                  <RepositoryCard
                    key={repo.id}
                    repository={repo}
                    onOpen={() => handleOpenIDE(repo.name)}
                    onDeploy={() => handleDeploy(repo.name)}
                  />
                ))}
              </div>

              {/* Pagination Controls */}
              {(page > 1 || hasNextPage) && (
                <div className="flex items-center justify-center space-x-3 pt-4 border-t border-vscode-border">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1 || isLoading}
                    className="flex items-center space-x-1 px-3 py-1.5 bg-vscode-sidebar border border-vscode-border rounded text-xs text-vscode-text hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    <ChevronLeft className="w-3.5 h-3.5" />
                    <span>Previous</span>
                  </button>
                  <span className="text-xs text-vscode-text-muted">Page {page}</span>
                  <button
                    onClick={() => setPage((p) => p + 1)}
                    disabled={!hasNextPage || isLoading}
                    className="flex items-center space-x-1 px-3 py-1.5 bg-vscode-sidebar border border-vscode-border rounded text-xs text-vscode-text hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    <span>Next</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </>
          )}

          {/* Footer Info */}
          <div className="mt-8 pt-6 border-t border-vscode-border flex flex-col sm:flex-row items-center justify-between text-xs text-vscode-text-muted gap-2">
            <span>OpenVSCode Server • Python 3 • GCC • G++ • Make • Git</span>
            <span>Render Free Tier • ₹0 Infrastructure Budget</span>
          </div>
        </main>
      </div>
    </div>
  );
};
