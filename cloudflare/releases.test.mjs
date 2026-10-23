import test from 'node:test';
import assert from 'node:assert/strict';
import {downloadLatest} from './releases.mjs';
import {artifactUrl} from './distribution.mjs';

test('website installer streams directly from R2 for GET and HEAD', async () => {
  const manifest = {version: '0.4.1', installer: {url: artifactUrl('launcher', '0.4.1', 'ScatterMacro.exe'), size: 2}};
  const env = {RELEASES: {
    get: async key => key.startsWith('manifests/') ? {json: async () => manifest}
      : {size: 2, body: 'MZ', customMetadata: {sha256: 'a'.repeat(64)}},
    head: async () => ({size: 2, customMetadata: {sha256: 'a'.repeat(64)}}),
  }};
  const original = globalThis.fetch;
  globalThis.fetch = () => {throw new Error('Website must not fetch its own public endpoint');};
  try {
    for (const method of ['GET', 'HEAD']) {
      const result = await downloadLatest(env, new Request('https://example.com/download/launcher/windows', {method}));
      assert.equal(result.status, 200);
      assert.equal(result.headers.get('content-disposition'), 'attachment; filename="ScatterMacro.exe"');
      assert.equal(await result.text(), method === 'GET' ? 'MZ' : '');
    }
  } finally {globalThis.fetch = original;}
});
