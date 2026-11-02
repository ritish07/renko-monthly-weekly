'use strict';
const fs=require('fs'),http=require('http'),path=require('path'),{spawn}=require('child_process'),readline=require('readline');
const {Paper}=require('./paper');
const ROOT=__dirname,LOCAL=process.argv.includes('--local'),DEMO=process.argv.includes('--demo');
const BROKER=(process.env.BROKER||'dhan').toLowerCase();if(!['dhan','fyers'].includes(BROKER))throw Error('BROKER must be dhan or fyers');
const DATA=path.resolve(process.env.RENKO_DATA||path.join(ROOT,'.data',DEMO?'demo':BROKER));fs.mkdirSync(DATA,{recursive:true,mode:0o700});const stateFile=path.join(DATA,'paper.json');
let saved={};if(fs.existsSync(stateFile))saved=JSON.parse(fs.readFileSync(stateFile,'utf8'));
const engine=new Paper(saved);
engine.broker=DEMO?'DEMO':BROKER.toUpperCase();engine.error=DEMO?'Starting synthetic local demo':'Connecting to '+engine.broker;
function save(){const tmp=stateFile+'.tmp',fd=fs.openSync(tmp,'w',0o600);try{fs.writeFileSync(fd,JSON.stringify(engine.saved()));fs.fsyncSync(fd);}finally{fs.closeSync(fd);}fs.renameSync(tmp,stateFile);}
const venv=path.join(ROOT,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const python=process.env.PYTHON_BIN||(fs.existsSync(venv)?venv:process.platform==='win32'?'python':'python3');
const feed=DEMO?'demo_feed.py':BROKER==='dhan'?'dhan_datafeed.py':'datafeed.py';
const child=spawn(python,['-u',path.join(ROOT,feed)],{cwd:DATA,env:{...process.env,DATA_DIR:DATA,PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','inherit']});
child.on('error',e=>{console.error('Cannot start Python feed:',e.message);process.exit(1);});
readline.createInterface({input:child.stdout}).on('line',line=>{if(!line.startsWith('DATA '))return;try{engine.receive(JSON.parse(line.slice(5)));}catch(e){console.error('Data processing failure:',e.message);process.exit(1);}});
child.on('exit',()=>{console.error('Market-data process stopped');process.exit(1);});
setInterval(()=>{engine.clock();save();},1000);
setInterval(()=>{if(child.stdin.writable)child.stdin.write(JSON.stringify({symbols:engine.wanted(Date.now())})+'\n');},3000);
function send(res,value,status=200,type='application/json'){const body=Buffer.isBuffer(value)?value:Buffer.from(JSON.stringify(value));res.writeHead(status,{'Content-Type':type,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Length':body.length});res.end(body);}
http.createServer((req,res)=>{
 const requested=new URL(req.url,'http://localhost').pathname;
 if(LOCAL&&requested==='/manage'){res.writeHead(302,{Location:'/manage/'});return res.end();}
 const ownerRoute=LOCAL&&requested.startsWith('/manage/');
 const p=ownerRoute?requested.slice('/manage'.length):requested;
 if(req.method==='GET'&&p==='/api/state')return send(res,engine.snapshot());
 if(req.method==='POST'){
  const host=req.headers.host||'',hostname=host.replace(/:\d+$/,'');
  const localHost=['localhost','127.0.0.1','[::1]'].includes(hostname);
  const localOwner=LOCAL&&ownerRoute&&localHost&&['127.0.0.1','::1','::ffff:127.0.0.1'].includes(req.socket.remoteAddress);
  const expectedOrigin=LOCAL?'http://'+host:'https://trading.ritishlabs.com';
  if((!localOwner&&(LOCAL||req.headers['x-authenticated-user']!=='ritish'))||req.headers['x-renko-control']!=='1'||(req.headers.origin&&req.headers.origin!==expectedOrigin))return send(res,{error:'Owner authentication required'},403);
  if(!['/api/start','/api/stop','/api/settings'].includes(p))return send(res,{error:'Not found'},404);
  let body='';req.on('data',b=>{body+=b;if(body.length>2048)req.destroy();});req.on('end',()=>{try{
   if(p==='/api/settings'){if(engine.running||engine.positions.some(Boolean))return send(res,{error:'Stop and exit all three bots before changing settings'},409);const v=JSON.parse(body);if(![1,45].includes(v.interval)||!Number.isFinite(v.cost)||v.cost<0)return send(res,{error:'Invalid interval or cost'},400);engine.interval=v.interval;engine.cost=v.cost;engine.reset('Paper settings changed');}
   else{engine.running=p==='/api/start';engine.log(engine.running?'All three live-data paper bots started':'Stop requested · waiting for fresh exit depth');engine.clock();}
   save();send(res,{ok:true,running:engine.running});
  }catch(e){send(res,{error:'Invalid request'},400);}});return;
 }
 if(req.method!=='GET')return send(res,{error:'Method not allowed'},405);
 const files={'/':['index.html','text/html; charset=utf-8'],'/app.js':['app.js','application/javascript'],'/engine.js':['engine.js','application/javascript'],'/style.css':['style.css','text/css']};
 if(!files[p])return send(res,{error:'Not found'},404);const [file,type]=files[p];send(res,fs.readFileSync(path.join(ROOT,'public',file)),200,type);
}).listen(Number(process.env.PORT||8838),'127.0.0.1',()=>console.log(`Renko ${DEMO?'SYNTHETIC DEMO':BROKER.toUpperCase()+' market data / PAPER'}: http://127.0.0.1:${process.env.PORT||8838}/ · owner controls /manage/`));
for(const sig of ['SIGTERM','SIGINT'])process.on(sig,()=>{save();child.kill('SIGTERM');process.exit(0);});
