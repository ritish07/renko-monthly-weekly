'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net');
test('standalone demo, owner controls, public protection and persisted paper state',async t=>{
 const probe=net.createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));const port=probe.address().port;await new Promise(r=>probe.close(r));
 const data=fs.mkdtempSync(path.join(os.tmpdir(),'renko-local-test-'));
 const child=spawn(process.execPath,['server.js','--local','--demo'],{cwd:__dirname,env:{...process.env,PORT:String(port),RENKO_DATA:data},stdio:['ignore','pipe','pipe']});let logs='';child.stdout.on('data',b=>logs+=b);child.stderr.on('data',b=>logs+=b);
 t.after(async()=>{if(child.exitCode===null){child.kill('SIGTERM');await new Promise(r=>child.once('exit',r));}fs.rmSync(data,{recursive:true,force:true});});
 const base='http://127.0.0.1:'+port;let state;
 for(let i=0;i<100;i++){try{const r=await fetch(base+'/api/state');state=await r.json();if(state.spot)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 assert.ok(state?.spot,logs);assert.equal(state.broker,'DEMO');assert.equal(state.execution,'PAPER');assert.equal(state.bricks.length,3);
 assert.equal((await fetch(base+'/manage/')).status,200);
 assert.equal((await fetch(base+'/manage/app.js')).status,200);
 const post=(route,origin=base)=>fetch(base+route,{method:'POST',headers:{Origin:origin,'X-Renko-Control':'1','Content-Type':'application/json'},body:'{}'});
 assert.equal((await post('/api/stop')).status,403);
 assert.equal((await post('/manage/api/stop','https://untrusted.example')).status,403);
 assert.equal((await post('/manage/api/stop')).status,200);
 assert.equal((await (await fetch(base+'/api/state')).json()).running,false);
 assert.equal((await post('/manage/api/start')).status,200);
 assert.ok(fs.existsSync(path.join(data,'paper.json')));
});
