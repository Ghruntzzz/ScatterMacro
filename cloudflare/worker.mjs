import {syncCommands} from './commands.mjs';
import {distribution} from './distribution.mjs';
import {licenseSessions,authorizeMacro} from './license-sessions.mjs';
import {downloadLatest} from './releases.mjs';
import {fixedCheckout,refreshPurchases} from './purchases.mjs';
import {logoResponse} from './brand.mjs';
import {updatesPage,downloadsPage,publishUpdate,publishDownload,removeUpdate} from './content.mjs';
import legacy,{verifyDiscordRequest,isLicenseCommandAdmin,decryptRecoverableLicenseKey,formatLicenseKey} from './legacy.mjs';
import {HttpError,json,base,session,requireSession,sameOrigin,body,oauth,cookie,cookieValue,digest,limit,config} from './core.mjs';
import {webhook,manage,setupBilling,configureWebhooks,syncStripe,syncPaypal,stripe,reconcile} from './billing.mjs';
import {home,dashboard,page,escape,appScript,navigationScript,motionScript} from './views.mjs';
import {purchasePanel,updatePanels,postStandalonePanel} from './discord.mjs';
async function readiness(env){return {stripe:!!env.STRIPE_SECRET_KEY,paypal:!!(env.PAYPAL_CLIENT_ID&&env.PAYPAL_CLIENT_SECRET)};}
export default {
 async fetch(request,env,ctx){const url=new URL(request.url);try{
 const access=await licenseSessions(request,env,legacy);if(access)return access;
 const release=await distribution(request,env,authorizeMacro);if(release)return release;
 if(request.method==='GET'&&['/auth/discord','/auth/discord/callback'].includes(url.pathname))return await oauth(request,env);
 if(request.method==='GET'&&url.pathname==='/assets/scatter-logo.jpeg')return logoResponse();
 if(['GET','HEAD'].includes(request.method)&&url.pathname==='/download/launcher/windows')return await downloadLatest(env,request);
 if(request.method==='GET'&&url.pathname==='/updates')return await updatesPage(request,env,await session(request,env));
 if(request.method==='GET'&&url.pathname==='/downloads')return await downloadsPage(env,await session(request,env));
 if(request.method==='GET'&&url.pathname==='/health')return json({ok:true,service:'scatter-macro',version:'2.0.0',...(env.DISCORD_PRESENCE?{presence:await env.DISCORD_PRESENCE.getByName('scatter-macro').start()}:{} )});
 if(request.method==='GET'&&url.pathname==='/motion.js')return new Response(motionScript,{headers:{'content-type':'application/javascript; charset=utf-8','cache-control':'no-cache'}});
 if(request.method==='GET'&&url.pathname==='/navigation.js')return new Response(navigationScript,{headers:{'content-type':'application/javascript; charset=utf-8','cache-control':'no-cache'}});
 if(request.method==='GET'&&url.pathname==='/app.js')return new Response(appScript,{headers:{'content-type':'application/javascript; charset=utf-8','cache-control':'no-cache'}});
 if(request.method==='GET'&&url.pathname==='/')return home(await session(request,env),await readiness(env));
 if(request.method==='GET'&&url.pathname==='/dashboard'){const u=await session(request,env);if(!u)return new Response(null,{status:303,headers:{location:'/auth/discord','cache-control':'no-store'}});return dashboard(u,await readiness(env),u.discord_user_id===env.DISCORD_OWNER_ID);}
 if(request.method==='POST'&&url.pathname==='/discord/interactions'){
 const text=await request.clone().text();if(!await verifyDiscordRequest(request,text,env.DISCORD_PUBLIC_KEY))return json({error:'Invalid signature'},401);const i=JSON.parse(text);
 if(i.type===2&&['purchase-panel','license-panel','ticket-panel'].includes(i.data?.name)){if(!isLicenseCommandAdmin(i,env))return json({type:4,data:{content:'This command is restricted to server administrators.',flags:64}});if(!i.channel_id)return json({type:4,data:{content:'Run this command in a server text channel.',flags:64}});const post=async()=>{try{await postStandalonePanel(i,env);await fetch(`https://discord.com/api/v10/webhooks/${i.application_id}/${i.token}/messages/@original`,{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({content:'Panel posted as a standalone bot message.'}),signal:AbortSignal.timeout(15000)});}catch(e){await fetch(`https://discord.com/api/v10/webhooks/${i.application_id}/${i.token}/messages/@original`,{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({content:e.message}),signal:AbortSignal.timeout(15000)});}};if(ctx?.waitUntil){ctx.waitUntil(post());return json({type:5,data:{flags:64}});}await postStandalonePanel(i,env);return json({type:4,data:{content:'Panel posted as a standalone bot message.',flags:64}});} 
 // Defer ticket operations so Discord's three-second acknowledgement does not time out.
 if([3,5].includes(i.type)&&(/^(support-panel:|support-ticket:|ticket:)/.test(i.data?.custom_id||'')||['robux-ticket-modal','license-transfer-modal'].includes(i.data?.custom_id))){
 if(i.data?.custom_id==='support-panel:select'&&i.data?.values?.[0]==='robux_purchase')return legacy.fetch(request,env);
 if(!ctx?.waitUntil)return legacy.fetch(request,env);
 ctx.waitUntil((async()=>{const r=await legacy.fetch(request,env);const result=await r.json();if(result.type===4){const response=await fetch(`https://discord.com/api/v10/webhooks/${i.application_id}/${i.token}/messages/@original`,{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify(result.data),signal:AbortSignal.timeout(15000)});if(!response.ok)console.error('discord_deferred_reply_failed',response.status);}})().catch(e=>console.error('discord_ticket_failed',e.message)));
 return json({type:5,data:{flags:64}});
 }
 return legacy.fetch(request,env);
 }
 if(request.method==='POST'&&url.pathname==='/v1/stripe/webhook')return json(await webhook(request,env,'stripe'));
 if(request.method==='POST'&&url.pathname==='/v1/paypal/webhook')return json(await webhook(request,env,'paypal'));
 // No new purchases may assign another person's Discord ID or use legacy one-time checkout.
 if(['/v1/checkout','/v1/paypal/order'].includes(url.pathname))return json({error:'Please sign in and subscribe from your dashboard.'},410);
 if(url.pathname==='/purchase-success'||url.pathname==='/purchase-cancelled')return new Response(null,{status:303,headers:{location:'/dashboard','cache-control':'no-store'}});
 if(url.pathname.startsWith('/api/')||url.pathname==='/auth/logout'){
 const u=await requireSession(request,env);
 if(request.method==='GET'&&url.pathname==='/api/me'){
 const licenses=await env.DB.prepare('SELECT id,plan,status,device_label,expires_at,created_at FROM licenses WHERE discord_user_id=?1 ORDER BY id DESC').bind(u.discord_user_id).all();const subs=await env.DB.prepare('SELECT b.*,e.customer_id,e.cancel_at_period_end,e.paid_until FROM billing_subscriptions b LEFT JOIN subscription_entitlements e ON e.subscription_id=b.id WHERE b.discord_user_id=?1 AND NOT(b.status IN (\'approval_pending\',\'unavailable\') AND EXISTS(SELECT 1 FROM dismissed_billing_requests d WHERE d.subscription_id=b.id AND d.discord_user_id=b.discord_user_id)) ORDER BY b.created_at DESC').bind(u.discord_user_id).all();return json({user:u,licenses:licenses.results.map(l=>({...l,status:l.status==='active'&&l.expires_at&&Date.parse(l.expires_at)<=Date.now()?'expired':l.status})),subscriptions:subs.results});}
 if(request.method!=='POST')throw new HttpError(405,'Method not allowed.');sameOrigin(request,env);await limit(request,env,'api:'+u.discord_user_id,40);const data=await body(request);
 if(url.pathname==='/auth/logout'){await env.DB.prepare('UPDATE web_sessions SET revoked_at=?1 WHERE session_hash=?2').bind(new Date().toISOString(),await digest(cookie(request,'__Host-scatter_session'))).run();const response=json({ok:true});response.headers.set('set-cookie',cookieValue('__Host-scatter_session','',0));return response;}
 if(url.pathname==='/api/checkout')return json(await fixedCheckout(env,u,data.provider,data.plan));
 if(url.pathname==='/api/subscriptions/manage')return json(await manage(env,u,data.id,data.action));
 if(url.pathname==='/api/licenses/reveal'){
 await limit(request,env,'reveal:'+u.discord_user_id,10);const l=await env.DB.prepare("SELECT s.encrypted_key FROM licenses l JOIN license_secrets s ON s.license_id=l.id WHERE l.id=?1 AND l.discord_user_id=?2 AND l.status='active' AND (l.expires_at IS NULL OR l.expires_at>?3)").bind(Number(data.id)||0,u.discord_user_id,new Date().toISOString()).first();if(!l)throw new HttpError(404,'Active license not found.');return json({key:formatLicenseKey(await decryptRecoverableLicenseKey(l.encrypted_key,env.LICENSE_PEPPER))});}
 if(url.pathname==='/api/refresh'){
 await limit(request,env,'refresh:'+u.discord_user_id,8);
 return json(await refreshPurchases(env,u));}
 if(url.pathname.startsWith('/api/admin/')){if(u.discord_user_id!==env.DISCORD_OWNER_ID)throw new HttpError(403,'Owner access required.');if(url.pathname==='/api/admin/commands')return json(await syncCommands(env));if(url.pathname==='/api/admin/updates/delete')return json(await removeUpdate(env,data));if(url.pathname==='/api/admin/updates')return json(await publishUpdate(env,u,data),201);if(url.pathname==='/api/admin/downloads')return json(await publishDownload(env,data),201);if(url.pathname==='/api/admin/setup')return json({billing:await setupBilling(env),webhooks:await configureWebhooks(env)});if(url.pathname==='/api/admin/panels')return json(await updatePanels(env));}
 throw new HttpError(404,'Not found.');
 }
 if(['/v1/licenses/activate','/v1/licenses/verify'].includes(url.pathname)||url.pathname.startsWith('/v1/admin/'))return legacy.fetch(request,env);
 throw new HttpError(404,'Page not found.');
 }catch(e){if(!(e instanceof HttpError))console.error('scatter_request_failed',url.pathname,e.message);const status=e.status||500,message=e.status?e.message:'Something went wrong. Please try again.';if(url.pathname.startsWith('/auth/')&&request.method==='GET')return page(`<h1 style="font-size:40px">Sign-in needs another try.</h1><p>${escape(message)}</p><a class="button" href="/auth/discord">Try Discord again</a>`,null,'Sign in · Scatter Macro');return json({error:message},status);}},
 async scheduled(event,env,ctx){ctx.waitUntil(reconcile(env));if(env.DISCORD_PRESENCE)ctx.waitUntil(env.DISCORD_PRESENCE.getByName('scatter-macro').start());}
};

