import {HttpError} from './core.mjs';
import {storedLauncher, distribution, ORIGIN} from './distribution.mjs';
export function selectLauncher(releases, repo) {
  const rows = releases.filter(r => !r.draft && !r.prerelease && /^launcher[-_]v?\d/i.test(r.tag_name))
    .sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at));
  for (const release of rows) {
    // The runtime ZIP is for the updater, never the website download button.
    const asset = (release.assets || []).find(a => a.state === 'uploaded' && a.name === 'ScatterMacro.exe');
    if (!asset) continue;
    let url;
    try { url = new URL(asset.browser_download_url); } catch { continue; }
    if (url.origin !== 'https://github.com' || !url.pathname.startsWith('/' + repo + '/releases/download/')) continue;
    return {
      version: release.tag_name.replace(/^launcher[-_]v?/i, ''), platform: 'windows',
      download_url: asset.browser_download_url, published_at: release.published_at,
      notes: 'Standalone launcher. Runtime files are installed in LocalAppData.',
      file_name: asset.name, size: asset.size, release_url: release.html_url, automatic: true,
    };
  }
  return null;
}
export async function latestLauncher(env,{fresh=false}={}){const stored=await storedLauncher(env);if(stored)return stored;const repo=env.LAUNCHER_RELEASE_REPO;if(!repo)return null;if(!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo))throw new HttpError(503,'Launcher releases are not configured.');const r=await fetch('https://api.github.com/repos/'+repo+'/releases?per_page=100',{headers:{Accept:'application/vnd.github+json','User-Agent':'ScatterMacroStore','Cache-Control':fresh?'no-cache':'max-age=60'},cf:{cacheTtl:fresh?0:60,cacheEverything:!fresh},signal:AbortSignal.timeout(8000)});if(!r.ok)throw new HttpError(503,'The latest launcher release could not be checked. Please try again shortly.');const release=selectLauncher(await r.json(),repo);if(!release)throw new HttpError(503,'No stable launcher installer has been published yet.');return release;}
export async function downloadLatest(env,request){const release=await latestLauncher(env,{fresh:true});if(!release)throw new HttpError(503,'Launcher downloads are not configured.');if(release.download_url.startsWith(ORIGIN+'/download/packages/launcher/'))return distribution(new Request(release.download_url,{method:request?.method==='HEAD'?'HEAD':'GET'}),env,()=>{throw new HttpError(403,'Launcher download only.');});const headers={'User-Agent':'ScatterMacroStore'};const range=request?.headers.get('range');if(range)headers.Range=range;const upstream=await fetch(release.download_url,{method:request?.method==='HEAD'?'HEAD':'GET',headers,redirect:'follow'});if(!upstream.ok&&upstream.status!==416){await upstream.body?.cancel();throw new HttpError(503,'The launcher file is temporarily unavailable. Please try again shortly.');}const output=new Headers({'content-type':'application/octet-stream','content-disposition':'attachment; filename="'+release.file_name.replace(/[^A-Za-z0-9_.-]/g,'_')+'"','cache-control':'no-store, max-age=0','x-content-type-options':'nosniff'});for(const h of ['content-length','content-range','accept-ranges'])if(upstream.headers.has(h))output.set(h,upstream.headers.get(h));return new Response(upstream.body,{status:upstream.status,headers:output});}

