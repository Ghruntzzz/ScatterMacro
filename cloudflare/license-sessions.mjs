import {HttpError, json, body, limit, digest} from './core.mjs';

const encode = value => btoa(String.fromCharCode(...value)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
const decode = value => Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
const bytes = value => new TextEncoder().encode(value);

async function signingKey(env) {
  if (!env.LICENSE_PEPPER) throw new HttpError(503, 'Licensing is unavailable.');
  return crypto.subtle.importKey('raw', bytes('scatter-session-v1:' + env.LICENSE_PEPPER), {name: 'HMAC', hash: 'SHA-256'}, false, ['sign', 'verify']);
}

async function issue(env, licenseId, deviceHash) {
  const expires = Math.floor(Date.now() / 1000) + 900;
  const payload = encode(bytes(JSON.stringify({licenseId, deviceHash, exp: expires})));
  const signature = await crypto.subtle.sign('HMAC', await signingKey(env), bytes(payload));
  return {ok: true, session: payload + '.' + encode(new Uint8Array(signature)), expiresAt: expires};
}

export async function authorizeMacro(request, env) {
  const auth = request.headers.get('authorization') || '';
  const device = request.headers.get('x-scatter-device') || '';
  if (!auth.startsWith('Bearer ') || auth.length > 2048 || !/^[a-f0-9]{64}$/.test(device)) throw new HttpError(401, 'Activation required.');
  const parts = auth.slice(7).split('.');
  let data;
  try {
    if (parts.length !== 2 || !await crypto.subtle.verify('HMAC', await signingKey(env), decode(parts[1]), bytes(parts[0]))) throw new Error();
    data = JSON.parse(new TextDecoder().decode(decode(parts[0])));
  } catch { throw new HttpError(401, 'Invalid session. Please activate your key again.'); }
  if (!Number.isFinite(data.exp) || data.exp <= Date.now() / 1000 || !Number.isSafeInteger(data.licenseId)) throw new HttpError(401, 'Session expired.');
  const deviceHash = await digest(`device:${device}:${env.LICENSE_PEPPER}`);
  if (data.deviceHash !== deviceHash) throw new HttpError(403, 'This session belongs to another device.');
  const license = await env.DB.prepare("SELECT id FROM licenses WHERE id=?1 AND device_hash=?2 AND status='active' AND (expires_at IS NULL OR expires_at>?3)")
    .bind(data.licenseId, deviceHash, new Date().toISOString()).first();
  if (!license) throw new HttpError(403, 'Your license is expired, revoked, or transferred.');
  return data;
}

export async function licenseSessions(request, env, legacy) {
  const path = new URL(request.url).pathname;
  if (!['/v2/activate', '/v2/session'].includes(path)) return null;
  if (request.method !== 'POST') throw new HttpError(405, 'Method not allowed.');
  await limit(request, env, path, path === '/v2/activate' ? 8 : 30);
  if (path === '/v2/session') {
    const data = await authorizeMacro(request, env);
    return json(await issue(env, data.licenseId, data.deviceHash));
  }
  const data = await body(request);
  if (typeof data.key !== 'string' || data.key.length > 128 || !/^[a-f0-9]{64}$/.test(data.deviceId || '')) throw new HttpError(400, 'Invalid key or device.');
  // Reuse the existing atomic device binding, expiry checks, and support reset flow.
  const headers = new Headers(request.headers);
  headers.set('content-type', 'application/json');
  headers.delete('content-length');
  const response = await legacy.fetch(new Request(new URL('/v1/licenses/activate', request.url), {
    method: 'POST', headers, body: JSON.stringify({key: data.key, deviceId: data.deviceId, deviceLabel: 'Windows launcher'}),
  }), env);
  if (!response.ok) return response;
  const verified = await response.json();
  if (verified.ok !== true || verified.status !== 'active' || !Number.isSafeInteger(verified.licenseId)) throw new HttpError(503, 'License verification failed.');
  return json(await issue(env, verified.licenseId, await digest(`device:${data.deviceId}:${env.LICENSE_PEPPER}`)));
}
