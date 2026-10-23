import test from 'node:test';
import assert from 'node:assert/strict';
import {artifactKey, artifactUrl, compareVersion, distribution, storedLauncher, validateClaims} from './distribution.mjs';

const claims = {
  iss: 'https://token.actions.githubusercontent.com', aud: 'scatter-macro-publish',
  repository: 'Ghruntz/ScatterMacro', repository_id: '1422708794', repository_owner_id: '200452395',
  ref: 'refs/heads/main', sub: 'repo:Ghruntz/ScatterMacro:ref:refs/heads/main',
  workflow_ref: 'Ghruntz/ScatterMacro/.github/workflows/publish-launcher.yml@refs/heads/main',
  event_name: 'push', iat: 1000, nbf: 1000, exp: 1300,
};

test('only the designated repository, branch and release workflows may publish', () => {
  assert.equal(validateClaims(claims, 1100), 'launcher');
  for (const [field, value] of Object.entries({aud: 'other', repository_id: '1', repository_owner_id: '2',
    repository: 'attacker/ScatterMacro', ref: 'refs/heads/dev', sub: 'repo:Ghruntz/ScatterMacro:pull_request',
    workflow_ref: 'Ghruntz/ScatterMacro/.github/workflows/other.yml@refs/heads/main', event_name: 'pull_request',
    exp: 1099, nbf: 2000, iat: 0})) {
    assert.throws(() => validateClaims({...claims, [field]: value}, 1100), undefined, field);
  }
});

test('artifact paths cannot escape the designated version/channel', () => {
  assert.equal(artifactKey('launcher', '0.3.3', 'ScatterMacro.exe'), 'packages/launcher/0.3.3/ScatterMacro.exe');
  assert.match(artifactUrl('launcher', '0.3.3', 'ScatterMacro.exe'), /^https:\/\/scatter-macro.shopscatter.workers.dev\/download\/packages\//);
  for (const values of [['launcher', '../', 'ScatterMacro.exe'], ['other', '1.0.0', 'ScatterMacro.exe'],
    ['launcher', '1.0.0', '../catalog.json'], ['anime-expeditions', '1.0.0', 'ScatterMacro.exe']]) {
    assert.throws(() => artifactKey(...values));
  }
  assert.ok(compareVersion('1.10.0', '1.9.9') > 0);
});

test('unconfigured storage fails closed', async () => {
  await assert.rejects(distribution(new Request('https://example.com/v2/catalog'), {}, () => {}), {status: 503});
});

test('catalog never returns a half-published release', async () => {
  const env = {RELEASES: {get: async () => null}};
  await assert.rejects(distribution(new Request('https://example.com/v2/catalog'), env, () => {}), {status: 503});
});

test('macro package reads require authorization before storage access', async () => {
  let read = false;
  const env = {RELEASES: {get: async () => { read = true; }}};
  const request = new Request('https://example.com/download/packages/anime-expeditions/1.0.0/AnimeExpeditions-1.0.0-windows.zip');
  await assert.rejects(distribution(request, env, async () => {throw new Error('denied');}), /denied/);
  assert.equal(read, false);
});

test('launcher download remains public without exposing bucket listing', async () => {
  const env = {RELEASES: {get: async key => {
    assert.equal(key, 'packages/launcher/1.0.0/ScatterMacro.exe');
    return {size: 2, body: 'MZ', customMetadata: {sha256: 'a'.repeat(64)}};
  }}};
  const response = await distribution(new Request('https://example.com/download/packages/launcher/1.0.0/ScatterMacro.exe'), env, () => {throw new Error('not needed');});
  assert.equal(await response.text(), 'MZ');
  assert.equal(response.headers.get('cache-control'), 'no-store');
  await assert.rejects(distribution(new Request('https://example.com/download/packages/'), env, () => {}), {status: 404});
});

test('stored launcher metadata no longer depends on GitHub', async () => {
  const env = {RELEASES: {get: async () => ({json: async () => ({version: '1.0.0', installer: {url: artifactUrl('launcher', '1.0.0', 'ScatterMacro.exe'), size: 2}})})}};
  const result = await storedLauncher(env);
  assert.equal(result.file_name, 'ScatterMacro.exe');
  assert.equal(new URL(result.download_url).hostname, 'scatter-macro.shopscatter.workers.dev');
});
