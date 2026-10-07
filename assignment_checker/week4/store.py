"""Atomic local proposal decision, audit and idempotent draft write."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid
from .contracts import FlowError


def now():
    return datetime.now(timezone.utc).isoformat()


def event(run, kind, **fields):
    run['audit'].append({'at':now(),'event':kind,**fields})


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS drafts (request_id TEXT PRIMARY KEY, draft_id TEXT UNIQUE NOT NULL, body TEXT NOT NULL);''')

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path,timeout=5)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def save(self, run):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO runs VALUES (?,?)',(run['run_id'],json.dumps(run,ensure_ascii=False)))

    def get(self, run_id):
        with self.db() as db:
            row = db.execute('SELECT body FROM runs WHERE id=?',(run_id,)).fetchone()
        if row is None:
            raise FlowError('RUN_NOT_FOUND','state')
        return json.loads(row[0])

    def draft_count(self):
        with self.db() as db:
            return db.execute('SELECT COUNT(*) FROM drafts').fetchone()[0]

    def decide(self, run_id, accepted, current_report_hash):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT body FROM runs WHERE id=?',(run_id,)).fetchone()
            if row is None:
                raise FlowError('RUN_NOT_FOUND','state')
            run = json.loads(row[0])
            if run['state'] != 'awaiting_confirmation':
                return run, False
            if not accepted:
                run['state']='declined'
                if run['request']['mode']=='live':run['live_status']='LIVE_STOPPED_BY_USER'
                event(run,'user_decision',accepted=False,executed=False)
            elif current_report_hash != run['report']['report_hash']:
                run['state']='stopped'
                if run['request']['mode']=='live':run['live_status']='LIVE_FAIL'
                run['error']={'code':'STALE_REPORT','layer':'readiness','retryable':False}
                event(run,'write_blocked',accepted=True,executed=False,code='STALE_REPORT')
            else:
                draft={'draft_id':'draft-'+uuid.uuid4().hex,'request_id':run_id,'status':'draft_created',
                       'assignment_id':run['report']['assignment_id'],
                       'submission_id':run['report']['submission_id'],
                       'submission_version':run['report']['submission_version'],
                       'report_hash':run['report']['report_hash'],
                       'needs_revision':run['report']['needs_revision'],
                       'needs_confirmation':run['report']['needs_confirmation'],
                       'items':[r for r in run['report']['items'] if r['value']!='met'],
                       'created_at':now(),'delivery':'local_only_not_sent'}
                db.execute('INSERT INTO drafts VALUES (?,?,?)',(run_id,draft['draft_id'],json.dumps(draft,ensure_ascii=False)))
                run.update(state='written',receipt=draft)
                event(run,'user_decision',accepted=True,executed=True,request_id=run_id)
                event(run,'write_committed',draft_id=draft['draft_id'],request_id=run_id,executed=True)
            db.execute('UPDATE runs SET body=? WHERE id=?',(json.dumps(run,ensure_ascii=False),run_id))
            return run, run['state']=='written'
