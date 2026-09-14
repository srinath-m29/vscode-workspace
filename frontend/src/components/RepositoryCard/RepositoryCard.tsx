import React, { useState, useEffect } from 'react';
import { RepositoryCardProps, Branch, Commit, DeploymentNormalizedStatus } from '../../types';
import { getBranches, getLatestCommit } from '../../services/github';
import { openProject } from '../../services/projects';
import { triggerDeployment, getDeploymentStatus } from '../../services/deployments';
import { isValidOpenUrl } from '../../utils/urlValidation';
import {
  GitBranch,
  GitCommit,
  ExternalLink,
  Rocket,
  FolderOpen,
  Lock,
  Globe,
  Loader2,
  ChevronDown,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
} from 'lucide-react';

export const RepositoryCard: React.FC<RepositoryCardProps> = ({
  repository,
  onDeploy,
}) => {
  const [selectedBranch, setSelectedBranch] = useState<string>(repository.defaultBranch || 'main');
  const [branches, setBranches] = useState<Branch[]>([]);
  const [isLoadingBranches, setIsLoadingBranches] = useState<boolean>(false);
  const [branchesLoaded, setBranchesLoaded] = useState<boolean>(false);

  const [latestCommit, setLatestCommit] = useState<Commit | null>(null);
  const [isLoadingCommit, setIsLoadingCommit] = useState<boolean>(false);
  const [commitError, setCommitError] = useState<string | null>(null);

  // Workspace preparation states for STEP 8
  const [isPreparingWorkspace, setIsPreparingWorkspace] = useState<boolean>(false);
  const [workspaceStatus, setWorkspaceStatus] = useState<'idle' | 'ready' | 'dirty' | 'error'>('idle');
  const [workspaceMessage, setWorkspaceMessage] = useState<string | null>(null);

  // Deployment states for STEP 12
  const [isStartingDeploy, setIsStartingDeploy] = useState<boolean>(false);
  const [deployStatus, setDeployStatus] = useState<DeploymentNormalizedStatus | 'idle'>('idle');
  const [deployId, setDeployId] = useState<string | null>(null);
  const [deployUrl, setDeployUrl] = useState<string | null>(null);
  const [deployMessage, setDeployMessage] = useState<string | null>(null);
  const [deployCommit, setDeployCommit] = useState<string | null>(null);
  const [deployBranch, setDeployBranch] = useState<string | null>(null);

  // Fetch initial latest commit for default branch on mount
  useEffect(() => {
    let isMounted = true;
    async function fetchInitialCommit() {
      if (!repository.owner || !repository.name) return;
      setIsLoadingCommit(true);
      setCommitError(null);
      try {
        const commit = await getLatestCommit(
          repository.owner,
          repository.name,
          selectedBranch
        );
        if (isMounted) {
          setLatestCommit(commit);
        }
      } catch (err: any) {
        if (isMounted) {
          setCommitError(err.message || 'Failed to load commit');
        }
      } finally {
        if (isMounted) {
          setIsLoadingCommit(false);
        }
      }
    }

    fetchInitialCommit();
    return () => {
      isMounted = false;
    };
  }, [repository.owner, repository.name, selectedBranch]);

  // Lazy-load branches on dropdown focus or click
  const handleLoadBranches = async () => {
    if (branchesLoaded || isLoadingBranches) return;
    setIsLoadingBranches(true);
    try {
      const branchList = await getBranches(repository.owner, repository.name);
      setBranches(branchList);
      setBranchesLoaded(true);
    } catch (err) {
      console.error('Failed to load branches', err);
    } finally {
      setIsLoadingBranches(false);
    }
  };

  const handleBranchChange = (newBranch: string) => {
    setSelectedBranch(newBranch);
    setWorkspaceStatus('idle');
    setWorkspaceMessage(null);
  };

  // STEP 12: Deployment handler
  const handleDeploy = async () => {
    if (onDeploy) {
      onDeploy();
    }

    // If workspace is dirty, warn user
    if (workspaceStatus === 'dirty') {
      setDeployMessage('Commit and push your changes before deploying.');
      return;
    }

    setIsStartingDeploy(true);
    setDeployMessage('Starting deployment...');
    setDeployStatus('in_progress');

    try {
      const res = await triggerDeployment(repository.owner, repository.name, {
        branch: selectedBranch,
        clearCache: 'do_not_clear',
      });

      setDeployId(res.id);
      setDeployStatus(res.status);
      setDeployCommit(res.commit || null);
      setDeployBranch(selectedBranch);
      if (res.url) {
        setDeployUrl(res.url);
      }

      if (res.status === 'live') {
        setDeployMessage('Deployment successful');
      } else {
        setDeployMessage('Deployment in progress...');
      }
    } catch (err: any) {
      setDeployStatus('idle');
      setDeployMessage(err.message || 'Deployment failed');
    } finally {
      setIsStartingDeploy(false);
    }
  };

  // STEP 12: Conservative Polling for in-progress deployment
  useEffect(() => {
    if (!deployId || deployStatus !== 'in_progress') return;

    let isMounted = true;
    let timerId: ReturnType<typeof setTimeout> | null = null;
    let pollCount = 0;
    const startTime = Date.now();
    const MAX_POLL_DURATION_MS = 10 * 60 * 1000; // 10 minutes maximum

    const getNextInterval = (count: number): number => {
      if (count < 3) return 2000; // First ~6 seconds: 2s
      if (count < 7) return 5000; // Next ~20 seconds: 5s
      return 10000; // Subsequent: 10s
    };

    const poll = async () => {
      if (!isMounted) return;

      if (Date.now() - startTime > MAX_POLL_DURATION_MS) {
        if (isMounted) {
          setDeployMessage('Polling timed out. Check Render dashboard.');
        }
        return;
      }

      try {
        const res = await getDeploymentStatus(repository.owner, repository.name, deployId);
        if (!isMounted) return;

        setDeployStatus(res.status);
        if (res.commit) setDeployCommit(res.commit);
        if (res.url) setDeployUrl(res.url);

        if (res.status === 'live') {
          setDeployMessage('Deployment successful');
          return;
        } else if (res.status === 'build_failed') {
          setDeployMessage('Deployment failed');
          return;
        } else if (res.status === 'canceled') {
          setDeployMessage('Deployment canceled');
          return;
        } else {
          setDeployMessage('Deployment in progress...');
        }
      } catch (err) {
        console.error('Failed to poll deployment status:', err);
      }

      pollCount++;
      const nextDelay = getNextInterval(pollCount);
      timerId = setTimeout(poll, nextDelay);
    };

    const initialDelay = getNextInterval(0);
    timerId = setTimeout(poll, initialDelay);

    return () => {
      isMounted = false;
      if (timerId) clearTimeout(timerId);
    };
  }, [deployId, deployStatus, repository.owner, repository.name]);

  // STEP 9: Prepare workspace and navigate to OpenVSCode with safe same-origin URL
  const handleOpenIDE = async () => {
    setIsPreparingWorkspace(true);
    setWorkspaceStatus('idle');
    setWorkspaceMessage(null);
    try {
      const res = await openProject({
        owner: repository.owner,
        repo: repository.name,
        branch: selectedBranch,
      });

      if (res.status === 'ready') {
        setWorkspaceStatus('ready');
        setWorkspaceMessage('Workspace ready. Opening IDE...');

        // Strict same-origin validation: must match /vscode/?folder=... and reject external/arbitrary URLs
        const openUrl = res.open_url;
        if (isValidOpenUrl(openUrl)) {
          window.location.href = openUrl;
        } else {
          setWorkspaceStatus('error');
          setWorkspaceMessage('Invalid IDE navigation URL returned from server.');
        }
      } else if (res.status === 'dirty') {
        setWorkspaceStatus('dirty');
        setWorkspaceMessage(
          res.message ||
            'Workspace contains uncommitted changes. Commit or review your existing changes before switching branches.'
        );
      }
    } catch (err: any) {
      setWorkspaceStatus('error');
      setWorkspaceMessage(err.message || 'Failed to prepare workspace.');
    } finally {
      setIsPreparingWorkspace(false);
    }
  };

  const getLanguageBadgeClass = (lang?: string) => {
    switch (lang?.toLowerCase()) {
      case 'python':
        return 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20';
      case 'c':
      case 'c++':
        return 'text-blue-400 bg-blue-400/10 border-blue-400/20';
      case 'typescript':
      case 'javascript':
        return 'text-sky-400 bg-sky-400/10 border-sky-400/20';
      case 'html':
      case 'css':
        return 'text-orange-400 bg-orange-400/10 border-orange-400/20';
      default:
        return 'text-vscode-text-muted bg-vscode-badge/40 border-vscode-border';
    }
  };

  return (
    <div className="bg-vscode-sidebar border border-vscode-border hover:border-vscode-accent/50 rounded-lg p-5 flex flex-col justify-between transition-all duration-150 group">
      <div>
        {/* Card Header: Repo Name + Visibility + Language */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center space-x-2 min-w-0">
            {repository.private ? (
              <span title="Private repository" className="flex-shrink-0 text-amber-400">
                <Lock className="w-3.5 h-3.5" />
              </span>
            ) : (
              <span title="Public repository" className="flex-shrink-0 text-vscode-text-muted">
                <Globe className="w-3.5 h-3.5" />
              </span>
            )}
            <h3
              className="font-semibold text-white text-base truncate group-hover:text-vscode-accent transition-colors"
              title={repository.fullName || repository.name}
            >
              {repository.name}
            </h3>
          </div>

          {repository.language && (
            <span
              className={`text-xs px-2 py-0.5 rounded border font-mono flex-shrink-0 ${getLanguageBadgeClass(
                repository.language
              )}`}
            >
              {repository.language}
            </span>
          )}
        </div>

        {/* Repository Description */}
        <p className="text-sm text-vscode-text-muted mt-2 line-clamp-2 min-h-[2.5rem]">
          {repository.description || 'No description provided.'}
        </p>

        {/* Branch Selector with Lazy-Loading */}
        <div className="mt-4 flex items-center space-x-2 text-xs">
          <GitBranch className="w-3.5 h-3.5 text-vscode-accent flex-shrink-0" />
          <div className="relative inline-block flex-1">
            <select
              value={selectedBranch}
              onFocus={handleLoadBranches}
              onClick={handleLoadBranches}
              onChange={(e) => handleBranchChange(e.target.value)}
              disabled={isLoadingBranches || isPreparingWorkspace}
              className="w-full appearance-none bg-vscode-bg border border-vscode-border hover:border-vscode-accent/60 rounded px-2.5 py-1 text-xs text-vscode-text focus:outline-none focus:border-vscode-accent pr-7 cursor-pointer transition-colors"
            >
              {!branchesLoaded && (
                <option value={selectedBranch}>
                  {selectedBranch} {selectedBranch === repository.defaultBranch ? '(default)' : ''}
                </option>
              )}
              {branches.map((b: Branch) => (
                <option key={b.name} value={b.name}>
                  {b.name} {b.default ? '(default)' : ''}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-vscode-text-muted">
              {isLoadingBranches ? (
                <Loader2 className="w-3 h-3 animate-spin text-vscode-accent" />
              ) : (
                <ChevronDown className="w-3 h-3" />
              )}
            </div>
          </div>
        </div>

        {/* Latest Commit Details */}
        <div className="mt-3 pt-3 border-t border-vscode-border/50 text-xs text-vscode-text-muted min-h-[2rem] flex items-center">
          {isLoadingCommit ? (
            <div className="flex items-center space-x-2 text-vscode-text-muted">
              <Loader2 className="w-3 h-3 animate-spin text-vscode-accent" />
              <span>Loading commit...</span>
            </div>
          ) : commitError ? (
            <span className="text-vscode-text-muted italic truncate">{commitError}</span>
          ) : latestCommit ? (
            <div className="flex items-center space-x-2 truncate" title={latestCommit.message}>
              <GitCommit className="w-3.5 h-3.5 flex-shrink-0 text-vscode-accent/80" />
              <span className="font-mono text-white/80 mr-1 flex-shrink-0">
                {latestCommit.sha.substring(0, 7)}
              </span>
              <span className="truncate">{latestCommit.message}</span>
            </div>
          ) : (
            <span className="text-vscode-text-muted italic">No commit data</span>
          )}
        </div>

        {/* Workspace Status Message (Step 8) */}
        {workspaceStatus !== 'idle' && (
          <div className="mt-3 pt-2">
            {workspaceStatus === 'ready' && (
              <div className="flex items-center space-x-1.5 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-2 py-1">
                <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="font-medium">Workspace ready</span>
              </div>
            )}
            {workspaceStatus === 'dirty' && (
              <div className="flex items-center space-x-1.5 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded px-2 py-1">
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate" title={workspaceMessage || ''}>
                  Workspace has uncommitted changes.
                </span>
              </div>
            )}
            {workspaceStatus === 'error' && (
              <div className="flex items-center space-x-1.5 text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded px-2 py-1">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate" title={workspaceMessage || ''}>
                  {workspaceMessage || 'Failed to prepare workspace.'}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Deployment Status (Step 12) */}
        {(deployStatus !== 'idle' || isStartingDeploy || deployMessage) && (
          <div className="mt-3 pt-2">
            {isStartingDeploy && (
              <div className="flex items-center space-x-1.5 text-xs text-purple-400 bg-purple-500/10 border border-purple-500/20 rounded px-2.5 py-1.5">
                <Loader2 className="w-3.5 h-3.5 animate-spin flex-shrink-0" />
                <span className="font-medium">Starting deployment...</span>
              </div>
            )}
            {!isStartingDeploy && deployStatus === 'in_progress' && (
              <div className="flex items-center space-x-1.5 text-xs text-purple-400 bg-purple-500/10 border border-purple-500/20 rounded px-2.5 py-1.5">
                <Loader2 className="w-3.5 h-3.5 animate-spin flex-shrink-0" />
                <div className="truncate">
                  <span className="font-medium">Deployment in progress...</span>
                  {deployBranch && (
                    <span className="text-vscode-text-muted ml-1.5">
                      ({deployBranch} {deployCommit ? `@ ${deployCommit.substring(0, 7)}` : ''})
                    </span>
                  )}
                </div>
              </div>
            )}
            {!isStartingDeploy && deployStatus === 'live' && (
              <div className="flex items-center justify-between gap-2 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-2.5 py-1.5">
                <div className="flex items-center space-x-1.5 min-w-0 truncate">
                  <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                  <span className="font-medium truncate">
                    Deployment successful ({deployBranch} @ {deployCommit ? deployCommit.substring(0, 7) : ''})
                  </span>
                </div>
                {deployUrl && (
                  <a
                    href={deployUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center space-x-1 text-emerald-300 hover:text-white underline flex-shrink-0 font-medium ml-2"
                  >
                    <span>Open Live Site</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            )}
            {!isStartingDeploy && deployStatus === 'build_failed' && (
              <div className="flex items-center space-x-1.5 text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded px-2.5 py-1.5">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate">{deployMessage || 'Deployment failed'}</span>
              </div>
            )}
            {!isStartingDeploy && deployStatus === 'canceled' && (
              <div className="flex items-center space-x-1.5 text-xs text-vscode-text-muted bg-vscode-badge/40 border border-vscode-border rounded px-2.5 py-1.5">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate">Deployment canceled</span>
              </div>
            )}
            {!isStartingDeploy && deployStatus === 'idle' && deployMessage && (
              <div className="flex items-center space-x-1.5 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded px-2.5 py-1.5">
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate">{deployMessage}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action Buttons: Open in IDE, GitHub link, Deploy */}
      <div className="mt-5 pt-4 border-t border-vscode-border flex items-center justify-between gap-2">
        <button
          onClick={handleOpenIDE}
          disabled={isPreparingWorkspace}
          className={`flex-1 flex items-center justify-center space-x-1.5 text-xs font-medium py-2 px-3 rounded transition-colors ${
            workspaceStatus === 'ready'
              ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
              : workspaceStatus === 'dirty'
              ? 'bg-amber-600 hover:bg-amber-500 text-white'
              : 'bg-vscode-accent hover:bg-vscode-accent-hover text-white'
          } disabled:opacity-50`}
          title="Open in OpenVSCode IDE"
        >
          {isPreparingWorkspace ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>Preparing workspace...</span>
            </>
          ) : workspaceStatus === 'ready' ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>Opening IDE...</span>
            </>
          ) : workspaceStatus === 'dirty' ? (
            <>
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Uncommitted changes</span>
            </>
          ) : workspaceStatus === 'error' ? (
            <>
              <AlertCircle className="w-3.5 h-3.5" />
              <span>Failed to open</span>
            </>
          ) : (
            <>
              <FolderOpen className="w-3.5 h-3.5" />
              <span>Open in IDE</span>
            </>
          )}
        </button>

        {repository.htmlUrl ? (
          <a
            href={repository.htmlUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center p-2 text-vscode-text-muted hover:text-white bg-vscode-bg border border-vscode-border rounded hover:bg-vscode-border/50 transition-colors"
            title="View on GitHub"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        ) : null}

        <button
          onClick={handleDeploy}
          disabled={isStartingDeploy || deployStatus === 'in_progress'}
          className={`flex items-center justify-center space-x-1 px-3 py-2 border rounded transition-colors text-xs font-medium disabled:opacity-50 ${
            deployStatus === 'live'
              ? 'text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/10'
              : deployStatus === 'in_progress' || isStartingDeploy
              ? 'text-purple-300 border-purple-500/30 bg-purple-500/10'
              : 'text-vscode-text-muted hover:text-white bg-vscode-bg border-vscode-border hover:bg-vscode-border/50'
          }`}
          title="Deploy to Render"
        >
          {isStartingDeploy ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin text-purple-400" />
              <span>Starting deployment...</span>
            </>
          ) : deployStatus === 'in_progress' ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin text-purple-400" />
              <span>Deploying...</span>
            </>
          ) : (
            <>
              <Rocket className="w-3.5 h-3.5 text-purple-400" />
              <span>{deployStatus === 'live' ? 'Redeploy' : 'Deploy'}</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};
