// Private package storage and repository-bound release publishing.
import {HttpError, json, body, limit} from './core.mjs';

export const ORIGIN = 'https://scatter-macro.shopscatter.workers.dev';
export const REPOSITORY = 'Ghruntzzz/ScatterMacro';
const ISSUER = 'https://token.actions.githubusercontent.com';
const AUDIENCE = 'scatter-macro-publish';
const CHANNELS = ['launcher', 'anime-expeditions'];
const VERSION = /^\d+\.\d+\.\d+$/;
const SHA256 = /^[a-f0-9]{64}$/;
const encoder = new TextEncoder();

function decode(value) {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new HttpError(401, 'Invalid publishing identity.');
  return Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
}

export function validateClaims(claims, now = Date.now() / 1000) {
  const workflows = CHANNELS.map(c => `${REPOSITORY}/.github/workflows/publish-${c}.yml@refs/heads/main`);
  if (claims.iss !== ISSUER || claims.aud !== AUDIENCE ||
      claims.repository_id !== '1431454277' || claims.repository_owner_id !== '347072376' ||
      claims.repository !== REPOSITORY || claims.ref !== 'refs/heads/main' ||
      claims.sub !== 'repo:Ghruntzzz@347072376/ScatterMacro@1431454277:ref:refs/heads/main' ||
      !workflows.includes(claims.workflow_ref) ||
      !['push', 'workflow_dispatch'].includes(claims.event_name) ||
      !Number.isFinite(claims.exp) || claims.exp <= now ||
      !Number.isFinite(claims.nbf) || claims.nbf > now + 30 ||
      !Number.isFinite(claims.iat) || claims.iat > now + 30 || now - claims.iat > 600) {
    throw new HttpError(403, 'Publishing identity is not authorized.');
  }
  return claims.workflow_ref.includes('/publish-launcher.yml@') ? 'launcher' : 'anime-expeditions';
}

async function publisher(request) {
  const authorization = request.headers.get('authorization') || '';
  if (!authorization.startsWith('Bearer ') || authorization.length > 20000) throw new HttpError(401, 'Publishing identity required.');
  const parts = authorization.slice(7).split('.');
  if (parts.length !== 3) throw new HttpError(401, 'Invalid publishing identity.');
  let header, claims;
  try {
    header = JSON.parse(new TextDecoder().decode(decode(parts[0])));
    claims = JSON.parse(new TextDecoder().decode(decode(parts[1])));
  } catch { throw new HttpError(401, 'Invalid publishing identity.'); }
  if (header.alg !== 'RS256' || typeof header.kid !== 'string') throw new HttpError(401, 'Invalid publishing signature.');
  const response = await fetch(ISSUER + '/.well-known/jwks', {signal: AbortSignal.timeout(10000)});
  if (!response.ok) throw new HttpError(503, 'Publishing identity service unavailable.');
  const jwk = (await response.json()).keys.find(k => k.kid === header.kid && k.kty === 'RSA' && k.alg === 'RS256');
  if (!jwk) throw new HttpError(401, 'Unknown publishing signature.');
  const key = await crypto.subtle.importKey('jwk', jwk, {name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256'}, false, ['verify']);
  if (!await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, decode(parts[2]), encoder.encode(parts[0] + '.' + parts[1]))) {
    throw new HttpError(401, 'Invalid publishing signature.');
  }
  return validateClaims(claims);
}

export function artifactKey(channel, version, filename) {
  if (!CHANNELS.includes(channel) || !VERSION.test(version)) throw new HttpError(400, 'Invalid release.');
  const names = channel === 'launcher'
    ? ['ScatterMacro.exe', `ScatterLauncher-${version}-windows.zip`]
    : [`AnimeExpeditions-${version}-windows.zip`];
  if (!names.includes(filename)) throw new HttpError(400, 'Invalid artifact.');
  return `packages/${channel}/${version}/${filename}`;
}

export function artifactUrl(channel, version, filename) {
  return ORIGIN + '/download/' + artifactKey(channel, version, filename);
}

async function releaseManifest(env, channel) {
  const object = await env.RELEASES.get(`manifests/${channel}.json`);
  return object ? object.json() : null;
}

export async function storedLauncher(env) {
  if (!env.RELEASES) return null;
  const manifest = await releaseManifest(env, 'launcher');
  if (!manifest || !await releaseManifest(env, 'anime-expeditions')) return null;
  return {
    version: manifest.version, platform: 'windows', download_url: manifest.installer.url,
    published_at: manifest.published_at, notes: 'ScatterMacro launcher for Windows.',
    file_name: 'ScatterMacro.exe', size: manifest.installer.size, release_url: ORIGIN + '/downloads', automatic: true,
  };
}

async function upload(request, env, channel, version, filename) {
  const key = artifactKey(channel, version, filename);
  const sha = request.headers.get('x-content-sha256') || '';
  const size = Number(request.headers.get('content-length'));
  if (!SHA256.test(sha) || !Number.isSafeInteger(size) || size <= 0 || size > 95 * 1024 * 1024) {
    throw new HttpError(400, 'Valid checksum and artifact size required (maximum 95 MiB).');
  }
  const existing = await env.RELEASES.head(key);
  if (existing) {
    if (existing.customMetadata?.sha256 !== sha || existing.size !== size) throw new HttpError(409, 'Release versions are immutable.');
    return json({ok: true, sha256: sha, size});
  }
  const result = await env.RELEASES.put(key, request.body, {
    onlyIf: {etagDoesNotMatch: '*'}, sha256: sha,
    httpMetadata: {contentType: 'application/octet-stream'}, customMetadata: {sha256: sha},
  });
  if (!result) throw new HttpError(409, 'Another upload created this artifact. Retry to verify it.');
  return json({ok: true, sha256: sha, size: result.size});
}

async function multipart(request, env, channel, version, filename) {
  const key = artifactKey(channel, version, filename);
  const query = new URL(request.url).searchParams;
  if (request.method === 'POST' && query.get('action') === 'start') {
    const data = await body(request);
    if (!SHA256.test(data.sha256 || '') || !Number.isSafeInteger(data.size) || data.size < 1 || data.size > 512 * 1024 * 1024) throw new HttpError(400, 'Invalid upload metadata.');
    const existing = await env.RELEASES.head(key);
    if (existing) {
      if (existing.customMetadata?.sha256 !== data.sha256 || existing.size !== data.size) throw new HttpError(409, 'Release versions are immutable.');
      return json({ok: true, existing: true});
    }
    const upload = await env.RELEASES.createMultipartUpload(key, {customMetadata: {sha256: data.sha256}, httpMetadata: {contentType: 'application/octet-stream'}});
    return json({ok: true, uploadId: upload.uploadId});
  }
  const uploadId = query.get('uploadId');
  if (!uploadId || uploadId.length > 2048) throw new HttpError(400, 'Upload ID required.');
  const upload = env.RELEASES.resumeMultipartUpload(key, uploadId);
  if (request.method === 'PUT') {
    const part = Number(query.get('partNumber')), size = Number(request.headers.get('content-length'));
    if (!Number.isInteger(part) || part < 1 || part > 16 || !Number.isInteger(size) || size < 1 || size > 64 * 1024 * 1024) throw new HttpError(400, 'Invalid upload part.');
    return json(await upload.uploadPart(part, request.body));
  }
  if (request.method === 'DELETE') {
    await upload.abort();
    return json({ok: true});
  }
  if (request.method === 'POST' && query.get('action') === 'complete') {
    const data = await body(request);
    if (!Array.isArray(data.parts) || data.parts.length < 1 || data.parts.length > 16 ||
        data.parts.some((p, i) => p.partNumber !== i + 1 || typeof p.etag !== 'string' || p.etag.length > 256)) throw new HttpError(400, 'Invalid upload parts.');
    if (await env.RELEASES.head(key)) throw new HttpError(409, 'Artifact already exists.');
    const result = await upload.complete(data.parts);
    return json({ok: true, size: result.size});
  }
  throw new HttpError(405, 'Method not allowed.');
}

export function retainedVersions(version, previous) {
  return [...new Set([version, previous?.version, ...(previous?.retained_versions || [])])]
    .filter(v => typeof v === 'string' && VERSION.test(v) && compareVersion(v, version) <= 0)
    .sort((a, b) => compareVersion(b, a)).slice(0, 2);
}

export async function cleanupReleases(env, channel) {
  if (!CHANNELS.includes(channel)) throw new HttpError(400, 'Invalid release channel.');
  const manifest = await releaseManifest(env, channel);
  // Never prune storage before a verified release has been published.
  if (!manifest || !VERSION.test(manifest.version) || !Array.isArray(manifest.retained_versions)) return 0;
  const keep = new Set(retainedVersions(manifest.version, manifest));
  const prefix = `packages/${channel}/`;
  let cursor, deleted = 0;
  do {
    const page = await env.RELEASES.list({prefix, limit: 100, ...(cursor ? {cursor} : {})});
    const obsolete = page.objects.filter(object => {
      const parts = object.key.split('/');
      if (parts.length !== 4 || parts[0] !== 'packages' || parts[1] !== channel) return false;
      const version = parts[2];
      // Leave newer in-progress uploads and unrelated objects alone.
      if (!VERSION.test(version) || keep.has(version) || compareVersion(version, manifest.version) >= 0) return false;
      try { return artifactKey(channel, version, parts[3]) === object.key; } catch { return false; }
    }).map(object => object.key);
    if (obsolete.length) await env.RELEASES.delete(obsolete);
    deleted += obsolete.length;
    cursor = page.truncated ? page.cursor : undefined;
    if (page.truncated && !cursor) throw new Error('Release listing cursor missing.');
  } while (cursor);
  return deleted;
}

export async function publishManifest(request, env, channel) {
  const data = await body(request);
  if (!VERSION.test(data.version || '')) throw new HttpError(400, 'Invalid version.');
  const filename = channel === 'launcher' ? `ScatterLauncher-${data.version}-windows.zip` : `AnimeExpeditions-${data.version}-windows.zip`;
  const packageObject = await env.RELEASES.head(artifactKey(channel, data.version, filename));
  if (!SHA256.test(data.sha256 || '') || packageObject?.customMetadata?.sha256 !== data.sha256) throw new HttpError(409, 'Verified package must be uploaded first.');
  const previous = await releaseManifest(env, channel);
  if (previous && compareVersion(data.version, previous.version) < 0) throw new HttpError(409, 'Release rollback is not allowed.');
  const manifest = {version: data.version, url: artifactUrl(channel, data.version, filename), sha256: data.sha256,
    published_at: new Date().toISOString(), retained_versions: retainedVersions(data.version, previous)};
  if (channel === 'launcher') {
    const installer = await env.RELEASES.head(artifactKey(channel, data.version, 'ScatterMacro.exe'));
    if (!SHA256.test(data.installer_sha256 || '') || installer?.customMetadata?.sha256 !== data.installer_sha256) throw new HttpError(409, 'Verified standalone installer must be uploaded first.');
    manifest.installer = {url: artifactUrl(channel, data.version, 'ScatterMacro.exe'), sha256: data.installer_sha256, size: installer.size};
  } else {
    Object.assign(manifest, {id: channel, name: 'Anime Expeditions', setup_only: false, entrypoint: 'AnimeExpeditions.exe',
      description: 'Licensed Anime Expeditions macro with Cloudflare updates.'});
  }
  await env.RELEASES.put(`manifests/${channel}.json`, JSON.stringify(manifest), {httpMetadata: {contentType: 'application/json'}});
  await cleanupReleases(env, channel);
  return json({ok: true, version: manifest.version});
}

export function compareVersion(a, b) {
  const aa = a.split('.').map(Number), bb = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) if (aa[i] !== bb[i]) return aa[i] - bb[i];
  return 0;
}

export async function distribution(request, env, authorizeMacro) {
  const path = new URL(request.url).pathname;
  if (!path.startsWith('/v2/publish/') && path !== '/v2/catalog' && !path.startsWith('/download/packages/')) return null;
  if (!env.RELEASES) throw new HttpError(503, 'Release storage is not configured.');
  if (path.startsWith('/v2/publish/')) {
    await limit(request, env, 'publish', 30);
    const channel = await publisher(request);
    const parts = path.split('/');
    if (parts.length === 7 && parts[3] === 'artifact' && parts[4] === channel) {
      if (request.method === 'GET') {
        const object = await env.RELEASES.get(artifactKey(channel, parts[5], parts[6]));
        if (!object) throw new HttpError(404, 'Artifact not found.');
        return new Response(object.body, {headers: {'content-type': 'application/octet-stream', 'cache-control': 'no-store'}});
      }
      if (new URL(request.url).search) return multipart(request, env, channel, parts[5], parts[6]);
      if (request.method === 'PUT') return upload(request, env, channel, parts[5], parts[6]);
    }
    if (request.method === 'POST' && path === '/v2/publish/manifest/' + channel) return publishManifest(request, env, channel);
    throw new HttpError(403, 'Publishing channel or method is not authorized.');
  }
  if (!['GET', 'HEAD'].includes(request.method)) throw new HttpError(405, 'Method not allowed.');
  if (path === '/v2/catalog') {
    const launcher = await releaseManifest(env, 'launcher');
    const macro = await releaseManifest(env, 'anime-expeditions');
    if (!launcher || !macro) throw new HttpError(503, 'Release migration is in progress.');
    return json({launcher, macros: [macro]});
  }
  const parts = path.split('/');
  if (parts.length !== 6) throw new HttpError(404, 'Package not found.');
  const [, , , channel, version, filename] = parts;
  const key = artifactKey(channel, version, filename);
  if (channel !== 'launcher') await authorizeMacro(request, env);
  const object = request.method === 'HEAD' ? await env.RELEASES.head(key) : await env.RELEASES.get(key);
  if (!object) throw new HttpError(404, 'Package not found.');
  return new Response(request.method === 'HEAD' ? null : object.body, {headers: {
    'content-type': 'application/octet-stream', 'content-length': String(object.size),
    'content-disposition': `attachment; filename="${filename}"`, 'cache-control': 'no-store',
    'x-content-type-options': 'nosniff', 'x-content-sha256': object.customMetadata.sha256,
  }});
}
