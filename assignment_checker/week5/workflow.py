"""Replace only confirmation wait/resume; the Week 4 domain store stays authoritative."""
from contextlib import asynccontextmanager, contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
from typing import TypedDict

import aiosqlite
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langsmith import tracing_context
from pydantic import ValidationError

from ..week4.contracts import Decision, FlowError
from ..week4.mcp_client import read_over_mcp
from ..week4.store import event
from ..week4.workflow import Workflow


class ApprovalState(TypedDict, total=False):
    run_id: str
    proposal: dict
    seal: str
    accepted: bool


def proposal_payload(run):
    return {key: run[key] for key in
            ('run_id', 'proposal', 'proposal_created_at', 'pending_call')} | {
                'report_hash': run['report']['report_hash']}


def seal(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class GraphWorkflow(Workflow):
    def __init__(self, store, checkpoint_path=None, provider=None, reader=read_over_mcp, fault=None):
        super().__init__(store, provider, reader, fault)
        self.checkpoint_path = Path(checkpoint_path or store.path.with_name('checkpoints.sqlite3'))
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def run_lock(self, run_id):
        # A filesystem lock survives separate workers and releases on process exit.
        # The lock filename is a digest, never an unchecked path from HTTP input.
        directory = self.store.path.parent / 'resume-locks'
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / (hashlib.sha256(run_id.encode()).hexdigest() + '.lock')).open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise FlowError('RUN_BUSY', 'orchestration', True) from None
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    @staticmethod
    def config(run_id):
        return {'configurable': {'thread_id': run_id}, 'recursion_limit': 5}

    def approval(self, state: ApprovalState):
        # Resume restarts this node. No model call, audit mutation or write precedes interrupt.
        value = interrupt(state['proposal'])
        try:
            decision = Decision.model_validate(value)
        except ValidationError:
            raise FlowError('INVALID_DECISION', 'orchestration') from None
        return {'accepted': decision.accepted}

    async def apply(self, state: ApprovalState):
        current = self.store.get(state['run_id'])
        if current['state'] != 'awaiting_confirmation':
            return {}  # A committed domain receipt wins over an older checkpoint.
        if seal(proposal_payload(current)) != state['seal']:
            self.fail(current, FlowError('PROPOSAL_CHANGED', 'readiness'))
            return {}
        event(current, 'framework_resumed', framework='langgraph', thread_id=state['run_id'],
              accepted=state['accepted'])
        self.store.save(current)
        # Keep the original expiry, source revalidation, transaction, idempotency and summary.
        await super().decide(state['run_id'], state['accepted'])
        return {}

    @asynccontextmanager
    async def graph(self):
        async with aiosqlite.connect(str(self.checkpoint_path), timeout=5) as connection:
            saver = AsyncSqliteSaver(connection, serde=JsonPlusSerializer(
                pickle_fallback=False, allowed_msgpack_modules=[]))
            builder = StateGraph(ApprovalState)
            builder.add_node('approval', self.approval)
            builder.add_node('apply', self.apply)
            builder.add_edge(START, 'approval')
            builder.add_edge('approval', 'apply')
            builder.add_edge('apply', END)
            # No LangSmith upload, even if the caller has global tracing enabled.
            with tracing_context(enabled=False):
                yield builder.compile(checkpointer=saver)

    @staticmethod
    def metadata(snapshot, run_id):
        return {
            'engine': 'langgraph', 'thread_id': run_id,
            'checkpoint_id': (snapshot.config or {}).get('configurable', {}).get('checkpoint_id'),
            'next': list(snapshot.next),
            'interrupts': [{'id': item.id, 'value': item.value}
                           for task in snapshot.tasks for item in task.interrupts],
        }

    async def inspect(self, run_id):
        current = self.store.get(run_id)
        # Reads never restore a checkpoint over a committed business result.
        try:
            async with self.graph() as graph:
                snapshot = await graph.aget_state(self.config(run_id))
                info = self.metadata(snapshot, run_id)
        except Exception:
            info = {'engine': 'langgraph', 'thread_id': run_id,
                    'checkpoint_id': None, 'next': [], 'interrupts': [],
                    'error': 'CHECKPOINT_INVALID'}
        return {**current, 'orchestration': info}

    async def start(self, request):
        run = await super().start(request)
        run['engine'] = 'langgraph'
        self.store.save(run)
        if run['state'] != 'awaiting_confirmation':
            return run
        payload = proposal_payload(run)
        try:
            async with self.graph() as graph:
                await graph.ainvoke({'run_id': run['run_id'], 'proposal': payload,
                                     'seal': seal(payload)}, self.config(run['run_id']))
            event(run, 'framework_interrupted', framework='langgraph', thread_id=run['run_id'],
                  executed=False)
            self.store.save(run)
        except Exception:
            self.fail(self.store.get(run['run_id']), FlowError('CHECKPOINT_INVALID', 'orchestration'))
        return await self.inspect(run['run_id'])

    async def decide(self, run_id, accepted):
        # This entry point is reached from the strict host decision endpoint, never a model tool.
        Decision.model_validate({'accepted': accepted})
        with self.run_lock(run_id):
            run = self.store.get(run_id)
            if run['state'] != 'awaiting_confirmation':
                return {**await self.inspect(run_id), 'replayed': True}
            try:
                async with self.graph() as graph:
                    snapshot = await graph.aget_state(self.config(run_id))
                    if not snapshot.values:
                        raise FlowError('CHECKPOINT_MISSING', 'orchestration')
                    if snapshot.values.get('seal') != seal(proposal_payload(run)):
                        raise FlowError('PROPOSAL_CHANGED', 'readiness')
                    # Only a still-pending interrupt accepts a fresh UI decision.
                    if not any(task.interrupts for task in snapshot.tasks):
                        raise FlowError('CHECKPOINT_INVALID', 'orchestration')
                    await graph.ainvoke(Command(resume={'accepted': accepted}), self.config(run_id))
            except Exception as caught:
                error = caught if isinstance(caught, FlowError) else FlowError('CHECKPOINT_INVALID', 'orchestration')
                fresh = self.store.get(run_id)
                # Never save a stale pending snapshot after a transaction or terminal decision.
                if fresh['state'] == 'awaiting_confirmation':
                    self.fail(fresh, error)
                elif fresh.get('receipt'):
                    event(fresh, 'checkpoint_error_after_commit', **error.body(), executed=True)
                    self.store.save(fresh)
            return await self.inspect(run_id)
