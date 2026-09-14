/**
 * Deployment API client for Render integration (STEP 12).
 * Strictly server-side authentication: RENDER_API_KEY is never handled here.
 */

import { apiFetch } from './api';
import {
  DeploymentTriggerResponse,
  DeploymentStatusResponse,
  TriggerDeployRequest,
} from '../types';

export async function triggerDeployment(
  owner: string,
  repo: string,
  data: TriggerDeployRequest = {}
): Promise<DeploymentTriggerResponse> {
  return apiFetch<DeploymentTriggerResponse>(
    `/api/deployments/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  );
}

export async function getDeploymentStatus(
  owner: string,
  repo: string,
  deployId?: string
): Promise<DeploymentStatusResponse> {
  const path = deployId
    ? `/api/deployments/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/${encodeURIComponent(deployId)}`
    : `/api/deployments/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;

  return apiFetch<DeploymentStatusResponse>(path);
}
