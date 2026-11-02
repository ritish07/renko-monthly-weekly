'use strict';
const test=require('node:test'),assert=require('node:assert/strict');const {Paper,day}=require('./paper');const {Renko}=require('./public/engine');
const now=Date.parse('2026-10-22T06:00:00Z');
function fixture(){const e=new Paper();e.masterDay=day(now);e.authenticated=e.transport=e.marketOpen=true;e.spot={symbol:'NSE:NIFTY50-INDEX',ltp:22500,at:now/1000};e.master=[];for(const type of ['CE','PE'])for(const strike of [22000,22300,22500,22700,23000]){const c={symbol:strike+type,strike,type,expiry:'2026-10-27',lotSize:65};e.master.push(c);e.quotes.set(c.symbol,{ltp:100,bid:99,ask:101,bid_qty:650,ask_qty:650,at:now/1000});}return e;}
test('Renko uses last quote within second and never emits on a timer alone',()=>{const r=new Renko(10,1);r.tick(100,now);r.tick(101,now+1000);r.tick(109,now+1000);assert.equal(r.candle,109);r.tick(109,now+2000);assert.equal(r.anchor,109);assert.equal(r.bricks.length,0);r.tick(119,now+3000);const bs=r.tick(119,now+4000);assert.equal(bs.length,1);assert.equal(bs[0].close,119);assert.equal(bs[0].time,now+4000);r.tick(119,now+5000);assert.equal(r.bricks.length,1);});
test('traditional Renko requires a two-brick reversal',()=>{const r=new Renko(10,1);r.complete(100,now);r.complete(120,now+1000);assert.equal(r.bricks.length,2);assert.equal(r.complete(110,now+2000).length,0);const b=r.complete(100,now+3000);assert.equal(b.length,1);assert.equal(b[0].open,110);assert.equal(b[0].close,100);});
test('spread fills correct sides, locks symbols and uses broker lot size',()=>{const e=fixture();assert(e.open(0,1,now));const p=e.positions[0];assert.equal(p.qty,65);assert.equal(p.legs[0].strike,22500);assert.equal(p.legs[0].entry,99);assert.equal(p.legs[1].strike,22000);assert.equal(p.legs[1].entry,101);e.spot.ltp=23000;assert(e.close(0,'test',now));assert.equal(p.net,-260);assert.equal(p.legs[0].symbol,'22500PE');assert.equal(p.legs[0].exit,101);assert.equal(p.legs[1].exit,99);});
test('buying bot selects ITM CE/PE and exits at bid',()=>{for(const [dir,strike,type] of [[1,22300,'CE'],[-1,22700,'PE']]){const e=fixture();assert(e.open(1,dir,now));assert.equal(e.positions[1].legs[0].symbol,strike+type);assert.equal(e.positions[1].legs[0].entry,101);assert(e.close(1,'test',now));assert.equal(e.ledger[0].net,-130);}});
test('stale or insufficient option depth prevents an atomic spread entry',()=>{const e=fixture();e.quotes.get('22000PE').at-=4;assert.equal(e.open(0,1,now),false);assert.equal(e.ledger.length,0);e.quotes.get('22000PE').at=now/1000;e.quotes.get('22000PE').ask_qty=64;assert.equal(e.open(0,1,now),false);assert.equal(e.ledger.length,0);});
test('stop preserves pending exit until fresh depth, including after restart',()=>{const e=fixture();e.open(1,1,now);e.running=false;e.clock(now+4000);assert(e.positions[1]);assert.equal(e.positions[1].exitPending,'Manual stop');assert.equal(e.mtm(e.positions[1],now+4000),null);const restored=new Paper(JSON.parse(JSON.stringify(e.saved())));assert(restored.positions[1]);restored.transport=restored.authenticated=true;restored.quotes.set('22300CE',{ltp:102,bid:102,ask:104,bid_qty:65,ask_qty:65,at:(now+5000)/1000});restored.clock(now+5000);assert.equal(restored.positions[1],null);assert.equal(restored.ledger[0].net,65);});
test('stale spot blocks entries but retains confirmed indicators',()=>{const e=fixture();e.healthy=true;e.engines[1].complete(100,now);e.engines[1].complete(130,now);assert(e.engines[1].bricks.length);e.clock(now+4000);assert.equal(e.healthy,false);assert.equal(e.engines[1].bricks.length,3);assert.equal(e.engines[1].bucket,null);assert.equal(e.open(1,1,now+4000),false);});
test('15:10 square-off is driven by wall clock without a new spot tick',()=>{const e=fixture();e.open(1,1,now);const closeTime=Date.parse('2026-10-22T09:40:00Z');e.quotes.get('22300CE').at=closeTime/1000;e.clock(closeTime);assert.equal(e.positions[1],null);assert.equal(e.ledger[0].reason,'15:10 square-off');});
test('no signals or bricks from stale replayed broker ticks',()=>{const e=fixture();e.receive({kind:'ticks',transport:true,authenticated:true,market_open:true,ticks:[{symbol:'NSE:NIFTY50-INDEX',ltp:24000,at:(now-10000)/1000}]},now);assert.equal(e.spot.ltp,22500);assert.equal(e.ledger.length,0);assert.equal(e.engines[1].bricks.length,0);});

test('recovery discards interrupted candles, retains bricks and does not trade a replay',()=>{
 const e=fixture();e.sessionDay=day(now);e.healthy=true;
 const r=e.engines[1];r.complete(22500,now);r.complete(22530,now+1000);
 const count=r.bricks.length;r.tick(24000,now+2000);
 e.clock(now+6000);assert.equal(r.bricks.length,count);
 const receive=(price,offset)=>e.receive({kind:'ticks',transport:true,authenticated:true,market_open:true,ticks:[{symbol:'NSE:NIFTY50-INDEX',ltp:price,at:(now+offset)/1000}]},now+offset);
 receive(22531,7000);receive(22532,8000);
 assert.equal(r.bricks.length,count);assert.equal(e.ledger.length,0);
 receive(22550,9000);receive(22551,10000);
 assert(r.bricks.length>count);assert.equal(e.ledger.length,0);
});

test('minute buyer follows sell signals and exits independently on the same EMA band',()=>{
 for(const [dir,strike,type] of [[1,22300,'CE'],[-1,22700,'PE']]){
  const e=fixture();e.sessionDay=day(now);e.healthy=true;
  assert.equal(e.engines[2].size,16.7);assert.equal(e.engines[2].interval,60);
  assert.equal(e.engines[1].size,8.6);assert.equal(e.engines[1].interval,1);
  const entry={close:dir>0?22520:22480,eh:22510,el:22490,rsi:dir>0?60:40};
  e.engines[0].tick=e.engines[2].tick=()=>[entry];e.engines[1].tick=()=>[];
  const tick=()=>e.receive({kind:'ticks',transport:true,authenticated:true,market_open:true,ticks:[e.spot]},now);
  tick();assert(e.positions[0]);assert(e.positions[2]);assert.equal(e.positions[1],null);
  const p=e.positions[2];assert.equal(p.legs.length,1);assert.equal(p.legs[0].symbol,strike+type);assert.equal(p.legs[0].side,1);assert.equal(p.legs[0].entry,101);
  const exit={...entry,close:dir>0?22480:22520};e.engines[0].tick=e.engines[2].tick=()=>[exit];tick();
  assert.equal(e.positions[0],null);assert.equal(e.positions[2],null);assert.equal(p.reason,'EMA band exit');assert.equal(p.legs[0].exit,99);
 }
});
test('minute buyer can fill when spread depth is missing, with separate freshness gates',()=>{
 const e=fixture();e.quotes.get('22000PE').ask_qty=0;
 assert.equal(e.open(0,1,now),false);assert(e.open(2,1,now));
 const other=fixture();other.quotes.get('22300CE').at-=4;assert.equal(other.open(2,1,now),false);assert.equal(other.ledger.length,0);
});
test('all three stable bot IDs restore positions and square off without altering historical records',()=>{
 const e=fixture();for(const i of [0,1,2])assert(e.open(i,1,now));
 const saved=JSON.parse(JSON.stringify(e.saved()));const r=new Paper(JSON.parse(JSON.stringify(saved)));assert.equal(r.positions.length,3);for(const i of [0,1,2])assert.equal(r.positions[i].id,e.positions[i].id);
 const t=Date.parse('2026-10-22T09:40:00Z');r.transport=r.authenticated=true;
 r.clock(t);assert(r.positions.every(p=>p.exitPending==='15:10 square-off'));
 for(const [symbol,q] of e.quotes)r.quotes.set(symbol,{...q,at:t/1000});r.clock(t);
 assert(r.positions.every(p=>p===null));assert.equal(r.ledger.length,3);assert(r.ledger.every(p=>p.status==='CLOSED'));
 const legacy=new Paper({...saved,ledger:saved.ledger.filter(p=>p.bot!==2)});assert(legacy.positions[0]);assert(legacy.positions[1]);assert.equal(legacy.positions[2],null);
});
