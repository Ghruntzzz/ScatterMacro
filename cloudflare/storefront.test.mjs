import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {accountMenu,accountScript} from './account-ui.mjs';
import {updateCard,updateCardScript} from './update-card.mjs';
import {planCards,dashboard,appScript,navigationScript,motionScript} from './views.mjs';
import {licensePage,recurringCheckout} from './subscriptions.mjs';

const user={discord_user_id:'123456789012345678',username:'Tester'};
function environment(first=()=>null){
  const calls=[];
  return {PUBLIC_BASE_URL:'https://example.com',calls,DB:{prepare(sql){return {bind(...args){calls.push({sql,args});return {first:async()=>first(sql,args),all:async()=>({results:[]}),run:async()=>({success:true})};}};}}};
}
test('account menu escapes names and uses validated avatars',()=>{
  assert.match(accountMenu(null),/>Sign in</);
  const html=accountMenu({...user,username:'<script>',avatar_hash:'a'.repeat(32)});
  assert.match(html,/&lt;script&gt;/);assert.match(html,/cdn.discordapp.com/);
  assert.match(html,/>My dashboard</);assert.match(html,/>Sign out</);
  assert.doesNotMatch(accountMenu({...user,avatar_hash:'bad" onerror="alert(1)'}),/<img/);
});
test('checkout defaults to renewal with clear unchanged prices',()=>{
  const html=planCards(user);
  assert.equal((html.match(/data-renew checked/g)||[]).length,2);
  assert.match(html,/Automatically renew \$4.99 every 7 days/);
  assert.match(html,/Automatically renew \$9.99 every month/);
});
test('update preview shares escaped public card rendering',()=>{
  const data={macro:'Example',title:'<img onerror=x>',changes:'One\nTwo',version:'v1.0',published_at:'2026-10-23T12:00:00Z'};
  assert.match(updateCard(data,{preview:true}),/Preview/);
  assert.match(updateCard(data),/&lt;img onerror=x&gt;/);
  assert.doesNotMatch(updateCard(data),/<img|data-delete-update/);
  const ctx=vm.createContext({});new vm.Script(updateCardScript.replace('export function','function')+';globalThis.render=updateCard;').runInContext(ctx);
  assert.equal(ctx.render(data),updateCard(data));
});
test('browser scripts parse and dashboard has adjacent preview',async()=>{
  for(const source of [appScript,accountScript,updateCardScript,navigationScript,motionScript])new vm.Script(source.replace(/^import .*;$/gm,'').replace(/export /g,''));
  const html=await dashboard(user,{stripe:true,paypal:true},true).text();
  assert.match(html,/id="publish-update"/);assert.match(html,/id="update-preview"/);assert.match(html,/id="license-filter"/);
});
test('license list paginates and scopes every query to current account',async()=>{
  const env=environment(sql=>sql.includes('COUNT')?{total:12}:null);
  const result=await licensePage(env,user,new URL('https://example.com/api/licenses?page=999&filter=all'));
  assert.equal(result.page,3);assert.equal(result.pages,3);
  for(const call of env.calls){assert.match(call.sql,/discord_user_id=\?1/);assert.equal(call.args[0],user.discord_user_id);assert.doesNotMatch(call.sql,/encrypted_key/);}
  assert.match(env.calls[1].sql,/LIMIT 5 OFFSET \?3/);assert.equal(env.calls[1].args[2],10);
});
test('license titles hide identifiers but preserve reveal-key identifiers',async()=>{
  const elements=Object.fromEntries(['licenses','license-filter','license-count','license-prev','license-next'].map(id=>[id,{value:'active'}]));
  const ctx=vm.createContext({document:{querySelector:s=>elements[s.slice(1)]},Date,URLSearchParams});
  new vm.Script(accountScript.replace(/^import .*;$/gm,'').replace(/export /g,'')+';globalThis.load=loadLicenses;').runInContext(ctx);
  await ctx.load(async()=>({page:1,pages:1,total:1,licenses:[{id:16,plan:'owner',status:'active'}]}));
  assert.match(elements.licenses.innerHTML,/owner license/);assert.doesNotMatch(elements.licenses.innerHTML,/#16/);assert.match(elements.licenses.innerHTML,/data-key="16"/);
  assert.equal(elements['license-next'].disabled,true);
  assert.match(elements.licenses.innerHTML,/<article class="license">/);
  assert.doesNotMatch(elements.licenses.innerHTML,/<details|<summary/);
});
test('Stripe recurring checkout uses subscription mode and grants no access',async()=>{
  const env=environment();let params;
  const result=await recurringCheckout(env,user,'stripe','weekly',{stripe:async(e,path,p)=>{params=p;return {id:'cs_test',url:'https://checkout.stripe.com/test'};}});
  assert.equal(params.mode,'subscription');assert.equal(params['line_items[0][price_data][unit_amount]'],'499');assert.equal(params['line_items[0][price_data][recurring][interval]'],'week');
  assert.equal(params['subscription_data[metadata][discord_user_id]'],user.discord_user_id);
  assert.match(result.url,/checkout.stripe.com/);
  assert.ok(env.calls.every(c=>!c.sql.includes('INSERT INTO licenses')));
});
test('existing renewing subscriptions block duplicate checkout',async()=>{
  const env=environment(sql=>sql.includes('SELECT b.id')?{id:'existing'}:null);
  await assert.rejects(recurringCheckout(env,user,'stripe','monthly',{}),{status:409});
});
test('PayPal recurring checkout rejects mismatched price without creating subscription',async()=>{
  const env=environment(sql=>sql.includes('billing_config')?{config_value:'P-PLAN'}:null);let calls=0;
  await assert.rejects(recurringCheckout(env,user,'paypal','monthly',{paypal:async()=>{calls++;return {status:'ACTIVE',billing_cycles:[{tenure_type:'REGULAR',total_cycles:0,frequency:{interval_unit:'MONTH',interval_count:1},pricing_scheme:{fixed_price:{currency_code:'USD',value:'100'}}}]};}}),{status:503});
  assert.equal(calls,1);assert.match(env.calls.at(-1).sql,/DELETE FROM checkout_attempts/);
});
