/**
 * OpenVSCode URL validation utilities.
 *
 * Enforces strict same-origin internal path validation for OpenVSCode navigation.
 * Accepts only URLs matching: /vscode/?folder=...
 *
 * Rejects:
 * - absolute URLs
 * - http:// and https://
 * - //external-host (protocol-relative)
 * - arbitrary paths (e.g. /dashboard, /api/auth, /other)
 * - client-supplied redirect URLs
 * - backslashes, control characters, or invalid search parameters
 */

export function isValidOpenUrl(url: unknown): url is string {
  if (typeof url !== 'string') {
    return false;
  }

  // Reject empty string or strings with leading/trailing whitespace
  if (url.length === 0 || url.trim() !== url) {
    return false;
  }

  // 1. Must strictly start with internal path /vscode/?folder=
  if (!url.startsWith('/vscode/?folder=')) {
    return false;
  }

  // 2. Reject absolute URLs and protocols (http://, https://, javascript:, data:, etc.)
  if (url.includes('://') || /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(url)) {
    return false;
  }

  // 3. Reject protocol-relative hosts (//external-host) and backslashes
  if (url.startsWith('//') || url.includes('\\')) {
    return false;
  }

  // 4. Reject control characters or newlines
  if (/[\r\n\t\0]/.test(url)) {
    return false;
  }

  // 5. Verify URL structure strictly as a relative same-origin path
  try {
    const dummyOrigin = 'http://localhost';
    const parsed = new URL(url, dummyOrigin);

    // Origin must remain identical to dummy origin (no host override or protocol spoofing)
    if (parsed.origin !== dummyOrigin) {
      return false;
    }

    // Pathname must strictly be '/vscode/'
    if (parsed.pathname !== '/vscode/') {
      return false;
    }

    // 'folder' query parameter must exist and be non-empty
    const folder = parsed.searchParams.get('folder');
    if (!folder || folder.trim() === '') {
      return false;
    }

    // Reject arbitrary extra parameters (e.g. ?folder=...&redirect=evil.com)
    const paramKeys = Array.from(parsed.searchParams.keys());
    if (paramKeys.length !== 1 || paramKeys[0] !== 'folder') {
      return false;
    }

    return true;
  } catch {
    return false;
  }
}
