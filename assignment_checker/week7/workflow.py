"""Use bounded session data while retaining the existing host tool checks."""
import json

from ..week4.contracts import FlowError
from ..week4.mcp_client import read_over_mcp
from ..week4.provider import FixtureProvider, ToolProvider
from ..week4.store import event
from ..week4.workflow import Workflow


class SessionWorkflow(Workflow):
    def __init__(self, store, memory, owner_id, session_id, provider=None,
                 reader=read_over_mcp, source_version=None):
        super().__init__(store, provider=provider, reader=reader)
        self.memory, self.owner_id, self.session_id = memory, owner_id, session_id
        self.source_version = source_version
        self._memory_trace = None

    def create_run(self, request):
        self.memory.require_active(self.session_id, self.owner_id)
        run = super().create_run(request)
        self.memory.bind_run(run['run_id'], self.session_id, self.owner_id)
        run.update(engine='session_memory', session_id=self.session_id, owner_id=self.owner_id,
                   memory_persisted=False)
        self.store.save(run)
        return run

    def build_history(self, request, preflight, trace):
        version = self.source_version or preflight['source'] + ':' + preflight['evidence_hash']
        context = self.memory.context(self.session_id, self.owner_id, version)
        self._memory_trace = context['trace']
        value = request.model_dump() if hasattr(request, 'model_dump') else request
        return [{'role': 'user', 'content': json.dumps({
            'request': value, 'session_context': context,
        }, ensure_ascii=False)}]

    async def model(self, run, phase):
        self.memory.authorize_run(run['run_id'], self.session_id, self.owner_id)
        if self._memory_trace and 'memory_trace' not in run:
            run['memory_trace'] = self._memory_trace
            event(run, 'memory_context_selected', **self._memory_trace)
            self.store.save(run)
        if self.provider is None:
            if run['request']['mode'] == 'fixture':
                self.provider = FixtureProvider()
            else:
                self.provider = ToolProvider()
        result = await super().model(run, phase)
        # A reset during an in-flight call discards the result before any tool executes.
        self.memory.authorize_run(run['run_id'], self.session_id, self.owner_id)
        return result

    def persist_success(self, run):
        if run['state'] != 'completed' or run.get('error') or run.get('replayed'):
            return run
        try:
            run['memory_persisted'] = self.memory.remember(
                self.session_id, self.owner_id, run['memory_trace']['source_version'], run)
            event(run, 'memory_saved', scope='session', stored=run['memory_persisted'],
                  report_hash=run['report']['report_hash'])
            self.store.save(run)
        except FlowError as error:
            # A reset after a read completed may remove memory, but must not undo a receipt.
            event(run, 'memory_not_saved', **error.body())
            self.store.save(run)
        return run

    async def start(self, request):
        self._memory_trace = None
        self.memory.require_active(self.session_id, self.owner_id)
        return self.persist_success(await super().start(request))

    async def decide(self, run_id, accepted):
        with self.memory.session_lock(self.session_id):
            self.memory.authorize_run(run_id, self.session_id, self.owner_id)
            return self.persist_success(await super().decide(run_id, accepted))
