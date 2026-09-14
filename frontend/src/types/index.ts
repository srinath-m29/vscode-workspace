export interface User {
  id: string;
  username: string;
  avatar_url: string;
  name?: string;
}

export interface AuthMeResponse {
  authenticated: boolean;
  user: User;
}

export interface Branch {
  name: string;
  default: boolean;
}

export interface Commit {
  sha: string;
  message: string;
  author: string;
  timestamp: string;
}

export interface Repository {
  id: number;
  name: string;
  fullName: string;
  description?: string;
  private: boolean;
  defaultBranch: string;
  htmlUrl: string;
  language?: string;
  updatedAt?: string;
  owner: string;
}

export interface RepositoriesApiResponse {
  repositories: {
    id: number;
    name: string;
    full_name: string;
    description?: string;
    private: boolean;
    default_branch: string;
    html_url: string;
    language?: string;
    updated_at?: string;
    owner: string;
  }[];
  page: number;
  per_page: number;
  has_next_page: boolean;
}

export interface BranchesApiResponse {
  branches: Branch[];
}

export interface RepositoryCardProps {
  repository: Repository;
  onOpen?: () => void;
  onDeploy?: () => void;
}

export interface OpenProjectRequest {
  owner: string;
  repo: string;
  branch: string;
}

export interface OpenProjectResponse {
  status: 'ready' | 'dirty';
  owner: string;
  repo: string;
  branch: string;
  workspace: string;
  open_url?: string;
  message?: string;
}

export type DeploymentNormalizedStatus =
  | 'in_progress'
  | 'live'
  | 'build_failed'
  | 'canceled'
  | 'unknown';

export interface TriggerDeployRequest {
  branch?: string;
  clearCache?: 'clear' | 'do_not_clear';
}

export interface DeploymentTriggerResponse {
  id: string;
  status: DeploymentNormalizedStatus;
  service: string;
  commit?: string;
  created_at?: string;
  url?: string;
}

export interface DeploymentStatusResponse {
  status: DeploymentNormalizedStatus;
  id?: string;
  commit?: string;
  url?: string;
  created_at?: string;
}

