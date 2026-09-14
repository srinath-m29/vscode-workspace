/**
 * Projects and workspace API client.
 * Calls POST /api/projects/open with only owner, repo, and branch.
 * Never passes user_id or workspace paths from the client.
 */

import { apiFetch } from './api';
import { OpenProjectRequest, OpenProjectResponse } from '../types';

export async function openProject(data: OpenProjectRequest): Promise<OpenProjectResponse> {
  return apiFetch<OpenProjectResponse>('/api/projects/open', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
