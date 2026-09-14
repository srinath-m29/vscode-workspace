import assert from 'node:assert';
import { isValidOpenUrl } from '../src/utils/urlValidation.ts';

console.log('Running URL validation test suite...');

// 1. Valid URLs from backend
assert.strictEqual(
  isValidOpenUrl('/vscode/?folder=%2Fhome%2Fworkspace%2F123456%2Fowner%2FQPapers'),
  true,
  'Standard encoded workspace path should be valid'
);

assert.strictEqual(
  isValidOpenUrl('/vscode/?folder=%2Fhome%2Fworkspace%2F99999%2Fmy-org%2Fmy-repo'),
  true,
  'Alphanumeric, dashes, and encoded slashes should be valid'
);

// 2. Reject absolute URLs
assert.strictEqual(
  isValidOpenUrl('http://example.com/vscode/?folder=%2Fhome%2Fworkspace%2F123456%2Fowner%2FQPapers'),
  false,
  'http:// URL should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('https://example.com/vscode/?folder=%2Fhome%2Fworkspace%2F123456%2Fowner%2FQPapers'),
  false,
  'https:// URL should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('ftp://example.com/vscode/?folder=%2Fhome%2Fworkspace%2F123456%2Fowner%2FQPapers'),
  false,
  'ftp:// URL should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('javascript:alert(1)//vscode/?folder=%2Fhome%2Fworkspace'),
  false,
  'javascript: URL should be rejected'
);

// 3. Reject protocol-relative //external-host
assert.strictEqual(
  isValidOpenUrl('//external-host/vscode/?folder=%2Fhome%2Fworkspace%2F123456%2Fowner%2FQPapers'),
  false,
  '//external-host should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('//evil.com'),
  false,
  '//evil.com should be rejected'
);

// 4. Reject arbitrary paths
assert.strictEqual(
  isValidOpenUrl('/dashboard'),
  false,
  '/dashboard should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('/api/health'),
  false,
  '/api/health should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('/vscode'),
  false,
  '/vscode without trailing slash and folder query should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('/vscode/'),
  false,
  '/vscode/ without folder query should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('/vscode/?other=123'),
  false,
  'Query other than folder should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('/vscode/?folder='),
  false,
  'Empty folder parameter should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('/vscode/?folder=%20%20'),
  false,
  'Whitespace folder parameter should be rejected'
);

// 5. Reject client-supplied redirect URLs and parameter injection
assert.strictEqual(
  isValidOpenUrl('/vscode/?folder=%2Fhome%2Fworkspace%2F123456&redirect=http://evil.com'),
  false,
  'Injected redirect parameter should be rejected'
);

// 6. Reject backslashes and control characters
assert.strictEqual(
  isValidOpenUrl('/vscode/?folder=%2Fhome\\evil.com'),
  false,
  'Backslash should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('\\vscode\\?folder=123'),
  false,
  'Leading backslash should be rejected'
);

assert.strictEqual(
  isValidOpenUrl('/vscode/?folder=%2Fhome\n/test'),
  false,
  'Newline character should be rejected'
);

// 7. Non-string inputs
assert.strictEqual(isValidOpenUrl(null), false, 'null should be rejected');
assert.strictEqual(isValidOpenUrl(undefined), false, 'undefined should be rejected');
assert.strictEqual(isValidOpenUrl(123), false, 'number should be rejected');
assert.strictEqual(isValidOpenUrl({}), false, 'object should be rejected');

console.log('All URL validation tests passed successfully!');
