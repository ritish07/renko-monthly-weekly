"""Persistent, process-shared FYERS Standard data budget and response cache.

Only data GETs pass here. Account reconciliation and orders never wait on this
lock. Reserve capacity for the live service; never substitute stale candles.
"""
import json
import sqlite3
from contextlib import contextmanager
import time
from datetime import datetime
from pathlib import Path
from strategy import IST

class DataBudget:
    def __init__(self, directory):
        self.path=Path(directory)/'data-budget.sqlite3'
        self.live=Path.cwd().resolve()==Path(__file__).resolve().parent
        with self.connect() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS calls(at REAL NOT NULL,day TEXT NOT NULL); CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,expires REAL NOT NULL,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value REAL NOT NULL);')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=20)
        try:
            with db:yield db
        finally:db.close()
    def run(self,path,fetch):
        # Minute bars are fetched once per symbol per minute across all workers.
        # Snapshots are shared briefly; stream ticks still drive live entries.
        cacheable=path.startswith(('/history?','/quotes?'))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            now=time.time(); day=datetime.now(IST).date().isoformat()
            expiry=(int(now)//60+1)*60 if path.startswith('/history?') else now+2
            db.execute('DELETE FROM calls WHERE day<>?',(day,))
            if cacheable:
                row=db.execute('SELECT value FROM cache WHERE key=? AND expires>?',(path,now)).fetchone()
                if row:return json.loads(row[0])
            row=db.execute("SELECT value FROM state WHERE key='backoff'").fetchone()
            if row and row[0]>now:raise RuntimeError('Fyers data rate limit cooldown; awaiting next evaluation')
            second,minute,daily=db.execute('SELECT sum(at>?),sum(at>?),count(*) FROM calls',(now-1,now-60)).fetchone()
            # Conservative Standard limits, leaving headroom for external clients.
            # Background readers leave additional room for live history/entry data.
            plan=db.execute("SELECT value FROM state WHERE key='prime_activated'").fetchone()
            prime=bool(plan and plan[0]==1)
            limits=((8,450,450000) if self.live else (6,300,300000)) if prime else ((4,45,4500) if self.live else (3,25,3000))
            if any((n or 0)>=limit for n,limit in zip((second,minute,daily),limits)):
                raise RuntimeError('Fyers shared data budget reserved/exhausted; awaiting next evaluation')
            db.execute('INSERT INTO calls VALUES(?,?)',(now,day))
            try:result=fetch()
            except Exception as exc:
                if any(s in str(exc) for s in ('HTTP 429','code -429','code 429','code -360')):
                    db.execute("INSERT OR REPLACE INTO state VALUES('backoff',?)",(max(now+65,getattr(exc,'retry_at',0)),))
                db.commit()
                raise
            if path.startswith('/history?'):
                expected=(int(now)//60-1)*60
                cacheable=any(bar and bar[0]==expected for bar in result.get('candles',[]))
            if cacheable:
                db.execute('DELETE FROM cache WHERE expires<=?',(now,))
                db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(path,expiry,json.dumps(result)))
            return result
