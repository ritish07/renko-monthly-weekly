'use strict';
const {Renko}=require('./public/engine.js');
const dayFormatter=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'});
const sessionFormatter=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',weekday:'short',hourCycle:'h23'});
const day=t=>dayFormatter.format(t);
function session(t){const p=Object.fromEntries(sessionFormatter.formatToParts(t).map(p=>[p.type,p.value]));return {minutes:+p.hour*60+(+p.minute),weekday:!['Sat','Sun'].includes(p.weekday)};}
class Paper {
 constructor(saved={}){this.running=saved.running??true;this.interval=saved.interval===45?45:1;this.ledger=saved.ledger||[];this.events=saved.events||[];this.positions=[0,1,2].map(i=>this.ledger.find(p=>p.bot===i&&p.status==='OPEN')||null);this.cost=Number.isFinite(saved.cost)?saved.cost:0;this.quotes=new Map();this.master=[];this.masterDay=null;this.holidays=[];this.transport=false;this.authenticated=false;this.marketOpen=false;this.broker='DHAN';this.error='Connecting to DHAN';this.spot=null;this.lastSeen=0;this.sessionDay=null;this.healthy=false;this.reset('Server started; waiting for observed live candles');}
 log(msg){if(this.events[0]?.msg===msg)return;this.events.unshift({time:Date.now(),msg});this.events=this.events.slice(0,150);}
 reset(reason){this.engines=[new Renko(16.7,60),new Renko(8.6,this.interval),new Renko(16.7,60)];this.lastSeen=0;this.log(reason);}
 pause(reason){for(const e of this.engines){e.bucket=null;e.fullBucket=false;}this.lastSeen=0;this.healthy=false;this.log(reason);}
 fresh(q,now){return !!q&&Number.isFinite(q.at)&&now/1000-q.at>=0&&now/1000-q.at<=3&&Number.isFinite(q.ltp)&&q.ltp>0;}
 ready(now){return this.transport&&this.authenticated&&this.fresh(this.spot,now)&&this.masterDay===day(now);}
 wanted(now){if(!this.spot||this.masterDay!==day(now))return this.positions.filter(Boolean).flatMap(p=>p.legs.map(l=>l.symbol));const atm=Math.round(this.spot.ltp/50)*50,expiry=this.master.filter(c=>c.expiry>=day(now)).map(c=>c.expiry).sort()[0];const strikes=new Set([-550,-500,-450,-250,-200,-150,-50,0,50,150,200,250,450,500,550].map(n=>atm+n));return [...new Set([...this.master.filter(c=>c.expiry===expiry&&strikes.has(c.strike)).map(c=>c.symbol),...this.positions.filter(Boolean).flatMap(p=>p.legs.map(l=>l.symbol))])];}
 executable(l,qty,side,now){const q=this.quotes.get(l.symbol);if(!this.fresh(q,now)||!Number.isFinite(q.bid)||!Number.isFinite(q.ask)||q.bid<=0||q.ask<q.bid)return null;const depth=side===1?q.ask_qty:q.bid_qty;if(!Number.isFinite(depth)||depth<qty)return null;return side===1?q.ask:q.bid;}
 open(i,dir,now){if(!this.running||!this.ready(now)||this.positions[i])return false;const atm=Math.round(this.spot.ltp/50)*50,ex=this.master.filter(c=>c.expiry>=day(now)).map(c=>c.expiry).sort()[0];const type=i===0?(dir>0?'PE':'CE'):(dir>0?'CE':'PE');const strikes=i===0?[atm,atm+(type==='CE'?500:-500)]:[atm+(type==='CE'?-200:200)];const cs=strikes.map(strike=>this.master.find(c=>c.expiry===ex&&c.strike===strike&&c.type===type));if(cs.some(c=>!c)||cs.some(c=>!Number.isInteger(c.lotSize)||c.lotSize<1||c.lotSize!==cs[0].lotSize)){this.log(`Bot ${i+1}: entry waiting for broker contracts`);return false;}
 const qty=cs[0].lotSize,legs=cs.map((c,n)=>({...c,side:i===0&&n===0?-1:1}));const fills=legs.map(l=>this.executable(l,qty,l.side,now));if(fills.some(p=>p===null)){this.log(`Bot ${i+1}: signal skipped · fresh bid/ask depth unavailable`);return false;}
 const p={id:require('crypto').randomUUID(),bot:i,dir,expiry:ex,entry:new Date(now).toISOString(),status:'OPEN',qty,cost:this.cost,source:this.broker==='DEMO'?'SYNTHETIC DEMO · PAPER':this.broker+' LIVE · PAPER',reason:'EMA3 / RSI14 signal',legs:legs.map((l,n)=>({...l,entry:fills[n],quoteAt:this.quotes.get(l.symbol).at}))};this.positions[i]=p;this.ledger.unshift(p);this.log(`Bot ${i+1}: paper ${dir>0?'bullish':'bearish'} entry · ${qty} units · ${ex}`);return true;
 }
 close(i,reason,now){const p=this.positions[i];if(!p)return true;p.exitPending=reason;if(!this.transport||!this.authenticated)return false;const fills=p.legs.map(l=>this.executable(l,p.qty,-l.side,now));if(fills.some(p=>p===null))return false;let gross=0;p.legs.forEach((l,n)=>{l.exit=fills[n];l.exitQuoteAt=this.quotes.get(l.symbol).at;gross+=(l.exit-l.entry)*l.side*p.qty;});p.exit=new Date(now).toISOString();p.gross=gross;p.net=gross-p.legs.length*2*p.cost;p.status='CLOSED';p.reason=reason;delete p.exitPending;this.positions[i]=null;this.log(`Bot ${i+1}: paper exit · ${reason}`);return true;}
 receive(data,now=Date.now()){
  if(data.broker)this.broker=data.broker;
  if(data.kind==='master'){this.master=data.contracts;this.masterDay=data.day;this.holidays=data.holidays||[];return;}
  if(data.kind==='error'){this.error=data.error;this.log(data.error);return;}
  this.transport=!!data.transport;this.authenticated=!!data.authenticated;this.marketOpen=!!data.market_open;this.error=data.error||null;
  if(data.lost)this.pause('Dropped feed events · confirmed bricks retained; incomplete candles discarded');
  for(const q of data.ticks||[]){if(!this.fresh(q,now))continue;const prev=this.quotes.get(q.symbol);if(prev&&q.at<prev.at)continue;this.quotes.set(q.symbol,q);if(q.symbol!=='NSE:NIFTY50-INDEX')continue;this.spot=q;
   if(!this.ready(now))continue;
   if(this.sessionDay!==day(now)){this.sessionDay=day(now);this.reset('New market session · warming up from real spot closes');}
   if(!this.healthy){this.pause('Fresh broker spot received · observing new candles; confirmed bricks retained');this.healthy=true;}
   if(this.lastSeen&&now-this.lastSeen>5000){this.pause('Spot feed gap · confirmed bricks retained; incomplete candles discarded');this.healthy=true;}this.lastSeen=now;
   const t=q.at*1000,ss=session(now),entry=ss.weekday&&!this.holidays.includes(day(now))&&ss.minutes>=560&&ss.minutes<909&&this.marketOpen;
   for(let i=0;i<3;i++){
    const bs=this.engines[i].tick(q.ltp,t);const p=this.positions[i];
    if(p&&(p.exitPending||!this.running||ss.minutes>=910||day(Date.parse(p.entry))<day(now))){this.close(i,p.exitPending||(!this.running?'Manual stop':ss.minutes>=910?'15:10 square-off':'Overdue square-off'),now);continue;}
    // A gap can produce several bricks; evaluate its last confirmed state once.
    const b=bs.at(-1);if(!b)continue;
    if(p&&((p.dir>0&&b.close<b.el)||(p.dir<0&&b.close>b.eh))){this.close(i,'EMA band exit',now);continue;}
    if(!p&&this.running&&entry&&b.rsi!==null){const d=b.close>b.eh&&b.rsi>50?1:b.close<b.el&&b.rsi<50?-1:0;if(d)this.open(i,d,now);}
   }
  }
  this.clock(now);
 }
 clock(now=Date.now()){
  if(!this.ready(now)&&this.healthy)this.pause('Feed stale or disconnected · signals paused; confirmed bricks retained');
  const ss=session(now);
  for(let i=0;i<3;i++){const p=this.positions[i];if(p&&(p.exitPending||!this.running||ss.minutes>=910||day(Date.parse(p.entry))<day(now)))this.close(i,p.exitPending||(!this.running?'Manual stop':ss.minutes>=910?'15:10 square-off':'Overdue square-off'),now);}
 }
 mtm(p,now){if(p.status==='CLOSED')return p.net;if(!this.transport||!this.authenticated)return null;let n=-p.legs.length*p.cost;for(const l of p.legs){const price=this.executable(l,p.qty,-l.side,now);if(price===null)return null;n+=(price-l.entry)*l.side*p.qty;}return n;}
 snapshot(now=Date.now()){const desired=new Set(this.wanted(now));const optionQuotes=[...this.quotes].filter(([symbol])=>desired.has(symbol)).map(([symbol,q])=>({symbol,...q,fresh:this.fresh(q,now)}));return {optionQuotes,freshOptionQuotes:optionQuotes.filter(q=>q.fresh&&q.bid>0&&q.ask>=q.bid).length,at:now,running:this.running,interval:this.interval,cost:this.cost,broker:this.broker,execution:'PAPER',transport:this.transport,authenticated:this.authenticated,ready:this.ready(now),marketOpen:this.marketOpen,error:this.error,masterDay:this.masterDay,contracts:this.master.length,spot:this.spot,events:this.events,ledger:this.ledger.map(p=>({...p,mtm:this.mtm(p,now)})),bricks:this.engines.map(e=>e.bricks),pending:this.positions.map(p=>p?.exitPending||null),session:session(now)};}
 saved(){return {running:this.running,interval:this.interval,cost:this.cost,ledger:this.ledger,events:this.events};}
}
module.exports={Paper,day,session};
