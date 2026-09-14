/**
 * GitHub service for Cloud IDE.
 * Communicates with backend /api/github endpoints.
 * All credentials remain strictly server-side using HttpOnly session cookies.
 */

import { apiFetch } from './api';
import {
  Repository,
  Branch,
  Commit,
  RepositoriesApiResponse,
  BranchesApiResponse,
} from '../types';

export interface GetRepositoriesParams {
  search?: string;
  page?: number;
  per_page?: number;
}

export interface GetRepositoriesResult {
  repositories: Repository[];
  page: number;
  per_page: number;
  hasNextPage: boolean;
}

/**
 * Retrieves the authenticated user's accessible GitHub repositories.
 */
export async function getRepositories(
  params: GetRepositoriesParams = {}
): Promise<GetRepositoriesResult> {
  const query = new URLSearchParams();
  if (params.search && params.search.trim()) {
    query.set('search', params.search.trim());
  }
  if (params.page && params.page > 0) {
    query.set('page', params.page.toString());
  }
  if (params.per_page && params.per_page > 0) {
    query.set('per_page', params.per_page.toString());
  }

  const queryString = query.toString();
  const endpoint = queryString
    ? `/api/github/repositories?${queryString}`
    : '/api/github/repositories';

  const res = await apiFetch<RepositoriesApiResponse>(endpoint);

  const normalized: Repository[] = (res.repositories || []).map((r) => ({
    id: r.id,
    name: r.name,
    fullName: r.full_name,
    description: r.description || '',
    private: r.private,
    defaultBranch: r.default_branch,
    htmlUrl: r.html_url,
    language: r.language || '',
    updatedAt: r.updated_at || '',
    owner: r.owner,
  }));

  return {
    repositories: normalized,
    page: res.page,
    per_page: res.per_page,
    hasNextPage: res.has_next_page,
  };
}

/**
 * Retrieves branches for a repository, identifying the default branch.
 */
export async function getBranches(owner: string, repo: string): Promise<Branch[]> {
  const encodedOwner = encodeURIComponent(owner);
  const encodedRepo = encodeURIComponent(repo);
  const res = await apiFetch<BranchesApiResponse>(
    `/api/github/repositories/${encodedOwner}/${encodedRepo}/branches`
  );
  return res.branches || [];
}

/**
 * Retrieves the latest commit for a specific branch.
 */
export async function getLatestCommit(
  owner: string,
  repo: string,
  branch: string
): Promise<Commit> {
  const encodedOwner = encodeURIComponent(owner);
  const encodedRepo = encodeURIComponent(repo);
  const encodedBranch = encodeURIComponent(branch);
  return apiFetch<Commit>(
    `/api/github/repositories/${encodedOwner}/${encodedRepo}/commits/latest?branch=${encodedBranch}`
  );
}
