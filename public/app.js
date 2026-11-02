'use strict';
const $=id=>document.getElementById(id),esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>'₹'+Number(v).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2}),tm=t=>new Date(t).toLocaleTimeString('en-GB',{timeZone:'Asia/Kolkata',hour12:false});
const botName=i=>i===0?'SELL · 1m':i===2?'BUY · 1m':'BUY · FAST';
const fillPrice=v=>typeof v==='number'&&Number.isFinite(v)?money(v):'—';
const legPrices=(p,field)=>p.legs.map(l=>`${l.side===1?'Buy':'Sell'} ${esc(l.strike)}${esc(l.type)} · ${fillPrice(l[field])}`).join('<br>');
const owner=location.pathname.includes('/manage/');let state=null,selected=0,fetching=false,offline=false;
$('run').hidden=!owner;$('stop').hidden=!owner;$('save').hidden=!owner;
$('brokerLogin').href='https://web.dhan.co/';
$('manage').href=owner?'../':'manage/';$('manage').textContent=owner?'Public view ↗':'Owner controls ↗';
function amount(items){return items.some(p=>p.mtm===null)?'Quote unavailable':money(items.reduce((s,p)=>s+p.mtm,0));}
function render(){if(!state)return;const s=state;$('brokerLogin').href=s.broker==='FYERS'?'https://myapi.fyers.in/':'https://web.dhan.co/';$('brokerLogin').textContent=s.broker==='DEMO'?'Demo · no broker login':s.broker+' connection';const ledger=s.ledger,closed=ledger.filter(p=>p.status==='CLOSED'),pending=s.pending.some(Boolean);$('clock').textContent=tm(Date.now())+' IST';$('mode').textContent=offline?'DASHBOARD OFFLINE':s.ready?(s.broker==='DEMO'?'SYNTHETIC DEMO · PAPER':s.broker+' LIVE · PAPER'):s.broker+' · WAITING';$('dataLabel').textContent='BROKER';
const age=s.spot?Math.max(0,(Date.now()/1000-s.spot.at)):null;
$('feedStatus').textContent=offline?'Server unreachable · displayed state may be outdated':s.ready?`${s.broker} authenticated · spot + ${s.freshOptionQuotes} fresh option quotes`:!s.authenticated?'Broker login unavailable · '+(s.error||'checking daily token'):!s.marketOpen?'Market closed · waiting for next session':`Waiting for fresh NIFTY spot${age===null?'':' · last quote '+Math.floor(age)+'s ago'}`;
$('notice').textContent=offline?'Dashboard connection lost. The server may still be running; reconnect to confirm its state.':pending?'Paper exit pending · waiting for fresh bid/ask depth on the locked contracts.':!s.ready?'Signals and entries paused until fresh broker data is available. No synthetic prices or invented fills.':(s.broker==='DEMO'?'SYNTHETIC DEMO prices · separate demo ledger · no broker connection.':`Real ${s.broker} market data · paper fills at quoted bid/ask · server continues when you close this page. Prices do not create a brick unless the Renko threshold is crossed.`);
$('pnl').textContent=amount(ledger);$('count').textContent=closed.length;$('win').textContent=closed.length?(100*closed.filter(p=>p.net>0).length/closed.length).toFixed(1)+'%':'—';$('spot').textContent=s.spot?s.spot.ltp.toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';$('updated').textContent=s.spot?tm(s.spot.at*1000)+' IST · '+(s.spot.timestampBasis==='received'?(s.spot.source==='FYERS REST snapshot'?'snapshot receipt time':'stream receipt time'):'broker timestamp')+(age>3?' · STALE':''):'Waiting for first broker tick';
$('interval').value=s.interval;$('run').disabled=s.running||offline;$('stop').disabled=(!s.running&&!ledger.some(p=>p.status==='OPEN'))||offline;
for(let i=0;i<3;i++){const p=ledger.find(p=>p.bot===i&&p.status==='OPEN'),bricks=s.bricks[i];$('state'+i).textContent=offline?'UNKNOWN':p?(p.exitPending?'EXIT PENDING':'PAPER POSITION'):!s.running?'STOPPED':!s.ready?'WAITING FOR FEED':bricks.at(-1)?.rsi==null?'WARMING UP':'MONITORING';$('position'+i).textContent=p?p.legs.map(l=>(l.side===1?'Buy ':'Sell ')+l.strike+l.type+' @ '+fillPrice(l.entry)).join(' / ')+` · ${p.qty} units`:'No open position · 1 broker lot';$('pnl'+i).textContent=amount(ledger.filter(p=>p.bot===i));}
$('ledgercount').textContent=' / '+ledger.length+' positions';$('ledger').innerHTML=ledger.length?ledger.map(p=>`<tr><td><b>${botName(p.bot)} BOT</b> · ${p.legs.map(l=>(l.side===1?'B ':'S ')+l.strike+l.type).join(' / ')}<br><small>${esc(p.expiry)} · ${esc(s.broker)} live / paper</small></td><td>${p.exitPending?'EXIT PENDING':esc(p.status)}</td><td>${tm(p.entry)}</td><td>${legPrices(p,'entry')}</td><td>${p.exit?tm(p.exit):'—'}</td><td>${p.exit?legPrices(p,'exit'):'—'}</td><td>${p.qty}</td><td class="${(p.mtm||0)<0?'negative':'positive'}">${p.mtm===null?'Quote unavailable':money(p.mtm)}</td><td>${esc(p.exitPending||p.reason)}</td></tr>`).join(''):'<tr><td colspan="9" class="empty">Waiting for real-market Renko signals.<br><small>RSI14 needs 15 confirmed bricks before entries are eligible. No demo trades are loaded.</small></td></tr>';
$('events').innerHTML=s.events.map(e=>`<div>${tm(e.time)} <span>· ${esc(e.msg)}</span></div>`).join('')||'Waiting for broker data.';draw();}
function chartTrades(bs){
 if(!bs.length)return [];
 const istDay=t=>new Date(t).toLocaleDateString('en-CA',{timeZone:'Asia/Kolkata'});
 const end=Math.max(bs.at(-1).time,state.spot?state.spot.at*1000:bs.at(-1).time);
 const events=[];
 for(const p of state.ledger.filter(p=>p.bot===selected))for(const field of ['entry','exit']){
  if(!p[field])continue;
  const time=Date.parse(p[field]);
  if(time<bs[0].time||time>end||istDay(time)!==istDay(bs.at(-1).time))continue;
  let index=bs.length-1;while(index>0&&bs[index].time>time)index--;
  events.push({p,field,time,index});
 }
 return events.sort((a,b)=>a.time-b.time);
}
function tradeMarkers(bs,x,y,w){
 const events=chartTrades(bs);
 $('chartSignals').innerHTML=events.length?'<p>Paper fills on the visible spot bricks · prices below are option premiums per unit. Hover or focus a marker for details.</p>'+events.map((e,n)=>{
  const signal=e.field==='entry'?(e.p.dir>0?'Bullish · EMA3 high / RSI14 > 50':'Bearish · EMA3 low / RSI14 < 50'):e.p.reason;
  return `<div class="chart-fill ${e.field}"><b>${e.field==='entry'?'E':'X'}${n+1} · ${e.field==='entry'?'ENTRY':'EXIT'} · ${tm(e.time)} IST</b><span>${esc(signal)}</span><span>${legPrices(e.p,e.field)}</span></div>`;
 }).join(''):'<p>No paper entries or exits in the visible brick range for this bot.</p>';
 return events.map((e,n)=>{
  const cx=x(e.index)+w/2,cy=y(bs[e.index].close),entry=e.field==='entry',color=entry?'#256d50':'#a14e32',label=(entry?'E':'X')+(n+1),ly=entry?18+(n%3)*22:280-(n%3)*22;
  const signal=entry?(e.p.dir>0?'Bullish: above EMA3 high, RSI14 > 50':'Bearish: below EMA3 low, RSI14 < 50'):e.p.reason;
  const details=`${label} · ${entry?'Entry':'Exit'} · ${tm(e.time)} IST · ${signal} · `+e.p.legs.map(l=>`${l.side===1?'Buy':'Sell'} ${l.strike}${l.type} @ ${fillPrice(l[e.field])}`).join(' / ');
  return `<g tabindex="0" role="img" aria-label="${esc(details)}"><title>${esc(details)}</title><line x1="${cx}" x2="${cx}" y1="${cy}" y2="${ly}" stroke="${color}" stroke-dasharray="3 3"/><circle cx="${cx}" cy="${cy}" r="5" fill="${color}" stroke="white" stroke-width="1.5"/><rect x="${cx-20}" y="${ly-14}" width="40" height="20" rx="4" fill="${color}"/><text x="${cx}" y="${ly+1}" text-anchor="middle" class="trade-marker-label">${label}</text></g>`;
 }).join('');
}
function draw(){const all=state.bricks[selected],bs=all.slice(-65),svg=$('chart');let html='';for(let y=20;y<280;y+=52)html+=`<line x1="0" x2="1050" y1="${y}" y2="${y}" stroke="#edf0e9" stroke-dasharray="3 5"/>`;if(!bs.length){tradeMarkers(bs,()=>0,()=>0,0);svg.innerHTML=html+'<text x="550" y="145" text-anchor="middle" fill="#98a493" font-size="13">Waiting for confirmed real-market bricks</text>';$('indicators').textContent=`${selected!==1?'16.7 pts · 1 minute':'8.6 pts · '+state.interval+' seconds'} · warming up`;return;}const min=Math.min(...bs.map(b=>b.low))-25,max=Math.max(...bs.map(b=>b.high))+25,y=v=>260-(v-min)/(max-min)*235,w=Math.min(15,970/bs.length),x=n=>25+n*w;for(let j=0;j<bs.length;j++){const b=bs[j];html+=`<rect x="${x(j)}" y="${y(b.high)}" width="${w-1}" height="${Math.max(1,y(b.low)-y(b.high))}" rx="1" fill="${b.close>b.open?'#4d876b':'#c88f76'}"><title>${tm(b.time)} IST · ${b.open.toFixed(2)} → ${b.close.toFixed(2)}</title></rect>`;}
for(const [field,color] of [['eh','#d8b65c'],['el','#8d9b74']])html+=`<polyline points="${bs.map((b,j)=>`${x(j)+w/2},${y(b[field])}`).join(' ')}" fill="none" stroke="${color}" stroke-width="1.4"/>`;for(let j=0;j<5;j++){const v=min+(max-min)*j/4;html+=`<text x="1055" y="${y(v)+3}" fill="#98a493" font-size="10">${v.toFixed(1)}</text>`;}html+=tradeMarkers(bs,x,y,w);svg.innerHTML=html;const b=bs.at(-1);$('indicators').textContent=`${selected!==1?'16.7 pts · 1m':'8.6 pts · '+state.interval+'s'} · RSI ${b.rsi===null?'warming up':b.rsi.toFixed(1)} · ${all.length} bricks`;}
async function poll(){if(fetching)return;fetching=true;try{const r=await fetch('api/state',{cache:'no-store',signal:AbortSignal.timeout(4500)});if(!r.ok)throw Error('HTTP '+r.status);state=await r.json();offline=false;render();}catch(e){offline=true;if(state)render();else{$('feedStatus').textContent='Server connection unavailable';$('notice').textContent='Waiting to reconnect to the paper engine.';}}finally{fetching=false;}}
async function command(name,data={}){try{const r=await fetch('api/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Renko-Control':'1'},body:JSON.stringify(data)}),v=await r.json();if(!r.ok)throw Error(v.error||'Control request failed');await poll();return true;}catch(e){alert(e.message);return false;}}
$('run').onclick=()=>command('start');$('stop').onclick=()=>command('stop');
function settings(){if(!state)return;$('settingInterval').value=state.interval;$('cost').value=state.cost;$('settingInterval').disabled=!owner;$('cost').disabled=!owner;$('dialog').showModal();}
$('settings').onclick=settings;$('settingsIcon').onclick=settings;$('save').onclick=async()=>{if(await command('settings',{interval:+$('settingInterval').value,cost:+$('cost').value}))$('dialog').close();};
for(const b of document.querySelectorAll('[data-bot]'))b.onclick=()=>{selected=+b.dataset.bot;document.querySelectorAll('[data-bot]').forEach(x=>x.classList.toggle('selected',x===b));if(state)draw();};
$('export').onclick=()=>{if(!state)return;const rows=[['bot','strategy','source','expiry','status','entry','exit','quantity','legs','net_after_estimated_costs','reason'],...state.ledger.map(p=>[p.bot+1,botName(p.bot),p.source,p.expiry,p.status,p.entry,p.exit||'',p.qty,JSON.stringify(p.legs),p.status==='CLOSED'?p.net:'',p.exitPending||p.reason])];const csv=rows.map(r=>r.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(new Blob([csv],{type:'text/csv'})),a=document.createElement('a');a.href=url;a.download='nifty-renko-'+state.broker.toLowerCase()+'-paper-trades.csv';a.click();URL.revokeObjectURL(url);};
poll();setInterval(poll,1000);
