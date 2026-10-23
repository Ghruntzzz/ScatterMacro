const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function updateCard(update,{preview=false,owner=false}={}) {
  const published=update.published_at||new Date().toISOString();
  const date=new Intl.DateTimeFormat('en-US',{month:'long',day:'numeric',year:'numeric',timeZone:'UTC'}).format(new Date(published));
  const changes=Array.isArray(update.changes)?update.changes:String(update.changes||'').split(/\r?\n/).map(c=>c.trim()).filter(Boolean).slice(0,40);
  return `<article class="update-card"><header class="update-head"><div><span class="tag">${escape(update.macro_name||update.macro||'Macro name')}</span><h2 class="update-title">${escape(update.title||'Your update title')}</h2><div class="update-meta">Scatter Macro team · <time datetime="${escape(published)}">${date}</time>${preview?' · Preview':''}</div></div><div><span class="update-version">v${escape(String(update.version||'0.0.0').replace(/^v/,''))}</span></div></header><div class="update-body">${update.summary?`<p>${escape(update.summary).replace(/\n/g,'<br>')}</p>`:''}<ul class="change-list">${changes.map(c=>`<li>${escape(c)}</li>`).join('')}</ul>${owner?`<div class="actions"><button class="small secondary" data-delete-update="${Number(update.id)}">Delete update</button></div>`:''}</div></article>`;
}
export const updateCardScript='const escape='+escape.toString()+';\nexport '+updateCard.toString();
