import test from 'node:test';
import assert from 'node:assert/strict';
import {authorizeMacro, licenseSessions} from './license-sessions.mjs';
import {digest} from './core.mjs';

const device = 'a'.repeat(64);
function environment(active = true) {
  return {LICENSE_PEPPER: 'test-only-not-a-production-secret', DB: {
    prepare: sql => ({bind: (...args) => ({first: async () => sql.includes('rate_limits') ? {request_count: 1} : active ? {id: 7} : null})}),
  }};
}
async function session(env) {
  const request = new Request('https://example.com/v2/activate', {method: 'POST', body: JSON.stringify({key: 'TESTONLY1234', deviceId: device})});
  const legacy = {fetch: async () => new Response(JSON.stringify({ok: true, status: 'active', licenseId: 7}))};
  return (await licenseSessions(request, env, legacy)).json();
}
function authenticated(token, targetDevice = device) {
  return new Request('https://example.com/v2/session', {method: 'POST', headers: {authorization: 'Bearer ' + token, 'x-scatter-device': targetDevice}});
}

test('activation issues expiring device-bound sessions', async () => {
  const env = environment(), result = await session(env);
  assert.ok(result.expiresAt > Date.now() / 1000);
  assert.ok(result.expiresAt <= Date.now() / 1000 + 900);
  const data = await authorizeMacro(authenticated(result.session), env);
  assert.equal(data.licenseId, 7);
  assert.equal(data.deviceHash, await digest(`device:${device}:${env.LICENSE_PEPPER}`));
});
test('revoked or transferred licenses cannot refresh or download', async () => {
  const result = await session(environment());
  await assert.rejects(authorizeMacro(authenticated(result.session), environment(false)), {status: 403});
  await assert.rejects(authorizeMacro(authenticated(result.session, 'b'.repeat(64)), environment()), {status: 403});
});
test('tampered and missing tokens fail closed', async () => {
  const result = await session(environment());
  await assert.rejects(authorizeMacro(authenticated('x.' + result.session.split('.')[1]), environment()), {status: 401});
  await assert.rejects(authorizeMacro(new Request('https://example.com'), environment()), {status: 401});
});
test('expired signed sessions are rejected', async () => {
  const env = environment();
  const payload = Buffer.from(JSON.stringify({licenseId: 7, deviceHash: await digest(`device:${device}:${env.LICENSE_PEPPER}`), exp: 1})).toString('base64url');
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode('scatter-session-v1:' + env.LICENSE_PEPPER), {name: 'HMAC', hash: 'SHA-256'}, false, ['sign']);
  const signature = Buffer.from(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload))).toString('base64url');
  await assert.rejects(authorizeMacro(authenticated(payload + '.' + signature), env), {status: 401});
});
test('failed activation never grants a session', async () => {
  const request = new Request('https://example.com/v2/activate', {method: 'POST', body: JSON.stringify({key: 'TESTONLY1234', deviceId: device})});
  const response = await licenseSessions(request, environment(), {fetch: async () => new Response('{"error":"invalid_license"}', {status: 403})});
  assert.equal(response.status, 403);
  assert.equal((await response.json()).session, undefined);
});
