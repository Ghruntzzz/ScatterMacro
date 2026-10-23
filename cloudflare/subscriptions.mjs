import {PLANS, HttpError, base, random, config} from './core.mjs';

export async function recurringCheckout(env,user,provider,plan,services=null) {
  if(!PLANS[plan] || !['stripe','paypal'].includes(provider)) throw new HttpError(400,'Choose a valid plan and payment method.');
  const {stripe,paypal}=services || await import('./billing.mjs');
  const active=await env.DB.prepare("SELECT b.id FROM billing_subscriptions b JOIN subscription_entitlements e ON e.subscription_id=b.id WHERE b.discord_user_id=?1 AND e.cancel_at_period_end=0 AND b.status IN ('active','trialing','past_due') LIMIT 1").bind(user.discord_user_id).first();
  if(active) throw new HttpError(409,'You already have a renewing subscription. Manage it in Your access before starting another.');
  const now=new Date().toISOString();
  await env.DB.prepare('DELETE FROM checkout_attempts WHERE expires_at<?1').bind(now).run();
  const existing=await env.DB.prepare('SELECT checkout_url,provider,plan_code,provider_id FROM checkout_attempts WHERE discord_user_id=?1 AND expires_at>?2').bind(user.discord_user_id,now).first();
  if(existing && !existing.checkout_url) throw new HttpError(409,'A checkout is opening. Please try again shortly.');
  const fixed=existing?.provider_id ? await env.DB.prepare('SELECT id FROM purchase_orders WHERE id=?1').bind(existing.provider+':'+existing.provider_id).first() : null;
  if(existing?.checkout_url && !fixed && existing.provider===provider && existing.plan_code===plan) return {url:existing.checkout_url};
  if(existing) await env.DB.prepare('DELETE FROM checkout_attempts WHERE discord_user_id=?1').bind(user.discord_user_id).run();
  const id=random(),p=PLANS[plan];
  try {await env.DB.prepare('INSERT INTO checkout_attempts(id,discord_user_id,provider,plan_code,created_at,expires_at) VALUES(?1,?2,?3,?4,?5,?6)').bind(id,user.discord_user_id,provider,plan,now,new Date(Date.now()+1800000).toISOString()).run();}
  catch {throw new HttpError(409,'A checkout is already opening.');}
  try {
    let result;
    if(provider==='stripe') {
      const s=await stripe(env,'/checkout/sessions',{mode:'subscription',client_reference_id:user.discord_user_id,
        'subscription_data[metadata][scatter]':'v2','subscription_data[metadata][discord_user_id]':user.discord_user_id,
        'subscription_data[metadata][plan]':plan,'line_items[0][price_data][currency]':'usd',
        'line_items[0][price_data][unit_amount]':String(p.cents),'line_items[0][price_data][recurring][interval]':p.interval,
        'line_items[0][price_data][product_data][name]':'Scatter Macro '+p.label,'line_items[0][quantity]':'1',
        success_url:base(env)+'/dashboard?checkout=success&session_id={CHECKOUT_SESSION_ID}',
        cancel_url:base(env)+'/dashboard?checkout=cancelled',expires_at:String(Math.floor(Date.now()/1000)+1801)},'scatter-sub-'+id);
      result={id:s.id,url:s.url};
    } else {
      const planId=await config(env,'paypal_plan_'+plan);
      if(!planId) throw new HttpError(503,'PayPal subscriptions are not configured yet. Please use card checkout.');
      const configured=await paypal(env,'/v1/billing/plans/'+encodeURIComponent(planId));
      const cycles=configured.billing_cycles||[],cycle=cycles[0];
      if(configured.status!=='ACTIVE'||cycles.length!==1||cycle.tenure_type!=='REGULAR'||cycle.total_cycles!==0||
          cycle.frequency?.interval_unit!==p.interval.toUpperCase()||cycle.frequency.interval_count!==1||
          cycle.pricing_scheme?.fixed_price?.currency_code!=='USD'||Number(cycle.pricing_scheme.fixed_price.value)!==p.cents/100||
          Number(configured.payment_preferences?.setup_fee?.value||0)!==0) throw new HttpError(503,'PayPal billing plan needs review. Please use card checkout.');
      const s=await paypal(env,'/v1/billing/subscriptions',{plan_id:planId,custom_id:user.discord_user_id,
        application_context:{brand_name:'Scatter Macro',shipping_preference:'NO_SHIPPING',user_action:'SUBSCRIBE_NOW',
          return_url:base(env)+'/dashboard?checkout=success',cancel_url:base(env)+'/dashboard?checkout=cancelled'}},id);
      result={id:s.id,url:s.links?.find(l=>l.rel==='approve')?.href};
    }
    if(!result.id||!result.url) throw new HttpError(502,'Checkout could not be opened.');
    await env.DB.prepare('UPDATE checkout_attempts SET provider_id=?1,checkout_url=?2 WHERE id=?3').bind(result.id,result.url,id).run();
    return {url:result.url};
  } catch(error) {
    await env.DB.prepare('DELETE FROM checkout_attempts WHERE id=?1').bind(id).run();
    throw error;
  }
}

export async function licensePage(env,user,url) {
  const page=Math.max(1,Math.min(100000,parseInt(url.searchParams.get('page')||'1',10)||1));
  const filter=['active','history','all'].includes(url.searchParams.get('filter'))?url.searchParams.get('filter'):'active';
  const now=new Date().toISOString();
  const active="(status='active' AND (expires_at IS NULL OR expires_at>?2))";
  const condition=filter==='active'?active:filter==='history'?'NOT '+active:'(?2 IS NOT NULL)';
  const where='discord_user_id=?1 AND '+condition;
  const count=await env.DB.prepare('SELECT COUNT(*) AS total FROM licenses WHERE '+where).bind(user.discord_user_id,now).first();
  const pages=Math.max(1,Math.ceil(count.total/5)),current=Math.min(page,pages);
  const rows=await env.DB.prepare('SELECT id,plan,status,device_label,expires_at,created_at FROM licenses WHERE '+where+' ORDER BY id DESC LIMIT 5 OFFSET ?3').bind(user.discord_user_id,now,(current-1)*5).all();
  return {licenses:rows.results.map(l=>({...l,status:l.status==='active'&&l.expires_at&&l.expires_at<=now?'expired':l.status})),page:current,pages,total:count.total,filter};
}
