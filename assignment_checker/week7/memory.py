"""Private session summaries; ownership is resolved from server-side SQLite rows."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

from pydantic import ValidationError

from ..week4.contracts import FlowError, Summary


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def token(value, limit=160):
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        raise FlowError('INVALID_MEMORY_RECORD', 'memory')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+', value):
        raise FlowError('INVALID_MEMORY_RECORD', 'memory')
    return value


class SessionMemory:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                    active INTEGER NOT NULL, successor TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS memories (
                    session_id TEXT PRIMARY KEY, source_version TEXT NOT NULL,
                    body TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS run_bindings (
                    run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, owner_id TEXT NOT NULL);
            ''')

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def session_lock(self, session_id):
        # Nonblocking lock avoids holding an HTTP event loop while another request writes.
        directory = self.path.parent / 'session-locks'
        directory.mkdir(parents=True, exist_ok=True)
        filename = hashlib.sha256(session_id.encode()).hexdigest() + '.lock'
        with (directory / filename).open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise FlowError('SESSION_BUSY', 'memory', True) from None
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    @staticmethod
    def _session(db, session_id, owner_id, require_active=False):
        row = db.execute(
            'SELECT * FROM sessions WHERE session_id=? AND owner_id=?',
            (session_id, owner_id),
        ).fetchone()
        if row is None:
            raise FlowError('SESSION_NOT_FOUND', 'memory')
        if require_active and not row['active']:
            raise FlowError('SESSION_INACTIVE', 'memory')
        return {'session_id': row['session_id'], 'owner_id': row['owner_id'],
                'active': bool(row['active']), 'successor': row['successor'],
                'created_at': row['created_at']}

    @staticmethod
    def _new(db, owner_id):
        session_id = 'session-' + uuid.uuid4().hex
        db.execute('INSERT INTO sessions VALUES (?,?,1,NULL,?)',
                   (session_id, owner_id, timestamp()))
        return SessionMemory._session(db, session_id, owner_id)

    def new_session(self, owner_id):
        token(owner_id, 100)
        with self.db() as db:
            return self._new(db, owner_id)

    def get_session(self, session_id, owner_id):
        with self.db() as db:
            return self._session(db, session_id, owner_id)

    def require_active(self, session_id, owner_id):
        with self.db() as db:
            return self._session(db, session_id, owner_id, require_active=True)

    def clear_session(self, session_id, owner_id):
        # Repeating a reset against an old ID returns its existing successor, not
        # another session, so a retried HTTP reset never clears newly added context.
        with self.session_lock(session_id), self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._session(db, session_id, owner_id)
            if not current['active']:
                visited = set()
                while not current['active']:
                    if current['session_id'] in visited or not current['successor']:
                        raise FlowError('SESSION_INACTIVE', 'memory')
                    visited.add(current['session_id'])
                    current = self._session(db, current['successor'], owner_id)
                return current
            replacement = self._new(db, owner_id)
            db.execute('UPDATE sessions SET active=0,successor=? WHERE session_id=?',
                       (replacement['session_id'], session_id))
            db.execute('DELETE FROM memories WHERE session_id=?', (session_id,))
            return replacement

    def context(self, session_id, owner_id, source_version):
        token(source_version, 256)
        with self.db() as db:
            self._session(db, session_id, owner_id, require_active=True)
            row = db.execute('SELECT * FROM memories WHERE session_id=?', (session_id,)).fetchone()
        memory = json.loads(row['body']) if row else None
        included = bool(row and row['source_version'] == source_version)
        trace = {
            'scope': 'session', 'session_id': session_id, 'owner_id': owner_id,
            'source_version': source_version,
            'stored_source_version': row['source_version'] if row else None,
            'included': included,
            'reason': 'same_session_same_source' if included else
                      'source_version_changed' if row else 'empty_session',
            'report_hash': memory['report_hash'] if memory else None,
        }
        return {'kind': 'untrusted_prior_report_data',
                'memory': memory if included else None, 'trace': trace}

    def remember(self, session_id, owner_id, source_version, run):
        # Failures, pending approvals and partial writes cannot become memories.
        if run.get('state') != 'completed' or run.get('error') or not run.get('summary'):
            return False
        token(source_version, 256)
        try:
            summary = Summary.model_validate(run['summary']).model_dump()
            report = run['report']
            for key in ('submission_id', 'submission_version', 'needs_revision', 'needs_confirmation'):
                if summary[key] != report[key]:
                    raise FlowError('INVALID_MEMORY_RECORD', 'memory')
            for key in ('needs_revision', 'needs_confirmation'):
                if len(summary[key]) > 10:
                    raise FlowError('INVALID_MEMORY_RECORD', 'memory')
                summary[key] = [token(item, 100) for item in summary[key]]
            summary['submission_id'] = token(summary['submission_id'], 100)
            # A previous receipt is not authority for any future write.
            summary.pop('draft_id')
            memory = {
                'run_id': token(run['run_id'], 100),
                'assignment_id': token(report['assignment_id'], 100),
                'source': token(report['source']),
                'source_version': source_version,
                'report_hash': token(report['report_hash'], 128),
                'evidence_hash': token(report['evidence_hash'], 128),
                'summary': summary,
            }
            body = json.dumps(memory, ensure_ascii=False)
            if len(body.encode('utf-8')) > 4096:
                raise FlowError('INVALID_MEMORY_RECORD', 'memory')
        except (KeyError, TypeError, ValidationError):
            raise FlowError('INVALID_MEMORY_RECORD', 'memory') from None
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._session(db, session_id, owner_id, require_active=True)
            binding = db.execute('SELECT * FROM run_bindings WHERE run_id=?',
                                 (run['run_id'],)).fetchone()
            if binding is None or binding['session_id'] != session_id or binding['owner_id'] != owner_id:
                raise FlowError('RUN_NOT_FOUND', 'memory')
            db.execute('INSERT OR REPLACE INTO memories VALUES (?,?,?,?)',
                       (session_id, source_version, body, timestamp()))
        return True

    def bind_run(self, run_id, session_id, owner_id):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._session(db, session_id, owner_id, require_active=True)
            prior = db.execute('SELECT * FROM run_bindings WHERE run_id=?', (run_id,)).fetchone()
            if prior and (prior['session_id'] != session_id or prior['owner_id'] != owner_id):
                raise FlowError('RUN_NOT_FOUND', 'memory')
            db.execute('INSERT OR IGNORE INTO run_bindings VALUES (?,?,?)',
                       (run_id, session_id, owner_id))

    def authorize_run(self, run_id, session_id, owner_id, require_active=True):
        with self.db() as db:
            # A generic result hides whether another user's run/session exists.
            row = db.execute(
                'SELECT * FROM run_bindings WHERE run_id=? AND session_id=? AND owner_id=?',
                (run_id, session_id, owner_id),
            ).fetchone()
            if row is None:
                raise FlowError('RUN_NOT_FOUND', 'memory')
            self._session(db, session_id, owner_id, require_active=require_active)
        return dict(row)
