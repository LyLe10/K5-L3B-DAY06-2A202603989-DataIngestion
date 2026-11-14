"""Offline only: synthetic DEV/TEST files, numerical fixtures, no live backends."""
import ast
from contextlib import contextmanager
from copy import deepcopy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from starter.scripts import run_local_lab_dev as dev
from starter.scripts import run_local_lab_test as lab
from starter.src import evaluation, evaluation_runner as runner
from starter.tests.test_evaluation_runner import setup, Adapter, IDENTITY
from starter.tests.test_benchmark import sample, bundle, frozen_bundle
from starter.tests.test_store import profile

ROOT = Path(__file__).resolve().parents[2]


def arguments():
    return SimpleNamespace(role='day6', selection='results/selection_freeze.json',
        dev_run='data/local/lab_benchmark/dev/synthetic/raw_run.json',
        output='data/local/lab_benchmark/test/synthetic',
        query_cache='data/local/lab_benchmark/query_cache/test-synthetic')


@pytest.fixture
def ready(setup, monkeypatch):
    s = setup
    identity = deepcopy(IDENTITY)
    identity['local_lab_entrypoint_sha256'] = lab.sha(dev.__file__)
    result = runner.run_evaluation(s.loaded, store=s.store, producer=s.producer, baseline=s.baseline,
        config=s.config, identity=identity, backend_identity={'verification': 'SYNTHETIC_FIXTURE'})
    result['manifest'].update(provenance='local_lab_dev', protected_stage5_authorization=False)
    path = s.root / arguments().dev_run
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(result))
    (s.root / 'results').mkdir()
    (s.root / 'results/benchmark_config.json').write_bytes((ROOT / 'results/benchmark_config.json').read_bytes())
    prepared = SimpleNamespace(bundle=s.loaded, baseline=s.baseline, profile=s.adapter.profile,
        context=None, plan=dict(code=deepcopy(IDENTITY), config=deepcopy(runner.DEFAULT_CONFIG)))
    def prepare(**kw):
        assert kw == dict(root=s.root, split='dev')
        # Actual frozen-file validator; no actual corpus/model/database is involved.
        runner.load_benchmark(s.folder, 'dev', config=s.config, identity=IDENTITY, root=s.root, corpus=s.corpus)
        return prepared
    boot = SimpleNamespace(prepare_dev=Mock(side_effect=prepare))
    embedding = SimpleNamespace(MyEmbedder=Mock(side_effect=AssertionError('no real model')))
    deps = (dev, evaluation, (boot, embedding, runner, None))
    monkeypatch.setattr(lab, 'dependencies', lambda: deps)
    real_runtime = lab.make_runtime
    runtime = Mock(side_effect=AssertionError('runtime not configured in fixture'))
    monkeypatch.setattr(lab, 'make_runtime', runtime)
    return SimpleNamespace(s=s, prepared=prepared, path=path, result=result, runtime=runtime, real_runtime=real_runtime,
                           deps=deps, config=lab.benchmark_config(s.root))


def save_dev(r):
    r.path.write_text(json.dumps(r.result))


def freeze(r):
    assert lab.freeze(arguments(), root=r.s.root) == 0
    return lab.read_json(r.s.root / arguments().selection)


def test_freeze_recomputes_choice_and_never_calls_runtime(ready):
    selection = freeze(ready)
    assert selection['selected_strategy'] == 'A'  # Equal synthetic metrics, fewer chunks.
    assert selection['dev_run_sha256'] == lab.sha(ready.path)
    assert selection['freeze_sha256'] == ready.s.loaded['freeze_sha256']
    assert selection['test_entrypoint_sha256'] == lab.sha(lab.__file__)
    assert lab.timestamp(selection['frozen_at']).tzinfo is not None
    ready.runtime.assert_not_called()
    ready.deps[2][1].MyEmbedder.assert_not_called()
    before = (ready.s.root / arguments().selection).read_bytes()
    with pytest.raises(FileExistsError): lab.freeze(arguments(), root=ready.s.root)
    assert (ready.s.root / arguments().selection).read_bytes() == before


@pytest.mark.parametrize('mutation', ['incomplete', 'missing', 'duplicate', 'split', 'summary',
    'filter', 'gold_metric', 'receipt', 'source', 'profile', 'config', 'code', 'invalid_time'])
def test_bad_dev_rejected_before_runtime_or_selection(ready, mutation):
    r = ready.result
    if mutation == 'incomplete': r['status'] = 'INCOMPLETE'
    elif mutation == 'missing': r['traces'].pop()
    elif mutation == 'duplicate': r['traces'][1] = deepcopy(r['traces'][0])
    elif mutation == 'split': r['traces'][0]['split'] = 'test'
    elif mutation == 'summary': r['summary']['groups'][0]['exact_hit_at_1']['numerator'] = 0
    elif mutation == 'filter': r['traces'][0]['applied_filter'] = {'section': 'Data Definition'}
    elif mutation == 'gold_metric': r['traces'][0]['evaluation']['exact_hit_at_1'] = 0
    elif mutation == 'receipt': r['receipts'][0]['input_sha256'] = '0' * 64
    elif mutation == 'source': r['traces'][0]['hits'][0]['text'] = 'fabricated fixture text'
    elif mutation == 'profile': r['manifest']['profile_id'] = '0' * 64
    elif mutation == 'config': r['manifest']['configuration']['top_k'] = 4
    elif mutation == 'code': r['manifest']['code']['source_hashes'] = {}
    elif mutation == 'invalid_time': r['manifest']['finished_at'] = 'not-a-timestamp'
    save_dev(ready)
    with pytest.raises((ValueError, KeyError)): lab.freeze(arguments(), root=ready.s.root)
    assert not (ready.s.root / arguments().selection).exists()
    ready.runtime.assert_not_called()


@pytest.mark.parametrize('name', ['dev.jsonl', 'test.jsonl', 'freeze_manifest.json'])
def test_benchmark_tamper_rejected_before_runtime(ready, name):
    freeze(ready)
    p = ready.s.folder / name
    p.write_bytes(p.read_bytes() + b' ')
    with pytest.raises(ValueError): lab.execute(arguments(), root=ready.s.root)
    ready.runtime.assert_not_called()


@pytest.mark.parametrize('field,value', [('selected_strategy', 'C'), ('dev_run_sha256', '0' * 64),
    ('freeze_sha256', '0' * 64), ('benchmark_config_sha256', '0' * 64),
    ('test_entrypoint_sha256', '0' * 64), ('frozen_at', 'not-a-timestamp'),
    ('frozen_at', '2026-11-15T00:00:00')])
def test_invalid_selection_blocks_runtime(ready, field, value):
    selection = freeze(ready)
    selection[field] = value
    (ready.s.root / arguments().selection).write_text(json.dumps(selection))
    with pytest.raises(ValueError): lab.execute(arguments(), root=ready.s.root)
    ready.runtime.assert_not_called()


def test_missing_selection_and_changed_dev_block_runtime(ready):
    with pytest.raises(FileNotFoundError): lab.execute(arguments(), root=ready.s.root)
    freeze(ready)
    ready.path.write_bytes(ready.path.read_bytes() + b' ')
    with pytest.raises(ValueError): lab.execute(arguments(), root=ready.s.root)
    ready.runtime.assert_not_called()


def test_predeclared_policy_is_checked(ready):
    config = ready.config
    config['selection_order'].reverse()
    (ready.s.root / 'results/benchmark_config.json').write_text(json.dumps(config))
    with pytest.raises(ValueError): lab.freeze(arguments(), root=ready.s.root)


def test_wall_clock_step_does_not_replace_dev_artifact_order(ready):
    # Timestamps are logs, not an approval/clock-custody infrastructure.
    ready.result['manifest']['started_at'] = '2026-11-15T02:00:01+00:00'
    ready.result['manifest']['finished_at'] = '2026-11-15T02:00:00+00:00'
    save_dev(ready)
    freeze(ready)
    _, _, _ = wire_test_runtime(ready, empty=True)
    assert lab.execute(arguments(), root=ready.s.root) == 0


def test_selection_order_all_tiebreaks(ready):
    summary = deepcopy(ready.result['summary'])
    groups = {g['strategy']: g for g in summary['groups']}
    assert lab.choice(summary, ready.config) == 'A'
    groups['A']['exact_evidence_hit_at_3']['numerator'] = 14
    groups['B']['exact_hit_at_1']['numerator'] = 14
    groups['C']['exact_hit_at_1']['numerator'] = 14
    assert lab.choice(summary, ready.config) == 'B'
    groups['C']['exact_hit_at_1']['numerator'] = 15
    assert lab.choice(summary, ready.config) == 'C'
    groups['B']['exact_evidence_hit_at_3']['numerator'] = 14
    groups['C']['exact_hit_at_1']['numerator'] = 0
    assert lab.choice(summary, ready.config) == 'C'


def wire_test_runtime(r, *, fail_at=None, empty=False, bad_text=False, embedding_error=False):
    questions = [json.loads(line) for line in (r.s.folder / 'test.jsonl').read_text().splitlines()]
    adapter = Adapter(r.prepared.profile, r.s.root / arguments().query_cache)
    producer = runner.QueryProducer(adapter, r.prepared.profile, adapter._cache_dir)
    original = producer.prepare
    def query_inputs(rows):
        assert len(rows) == 5
        assert [q['id'] for q in rows] == [q['id'] for q in questions]
        assert all(set(q) == {'id', 'question', 'filter'} for q in rows)
        if embedding_error: raise ValueError('password=DO_NOT_EXPORT')
        return original(rows)
    producer.prepare = query_inputs
    state = SimpleNamespace(searches=[], active=False, opens=0, closes=0)
    pages = {(p.document_id, p.page): p for p in r.s.corpus.pages}
    class Session:
        integrity = ('STRUCTURAL_INTEGRITY_VERIFIED', 'VECTOR_INTEGRITY_NOT_REVERIFIED')
        snapshots = r.prepared.baseline.snapshots
        def search(self, strategy, vector, top_k, filters):
            assert state.active and len(adapter.calls) == 5 and top_k == 3
            state.searches.append((strategy, id(vector), filters))
            if len(state.searches) == fail_at: raise RuntimeError('password=DO_NOT_EXPORT')
            if empty: return []
            index = vector.index(1.0)
            q = questions[index]
            p = pages[(q['gold_source_id'], q['gold_page'])]
            text = 'altered fixture' if bad_text else p.text
            return [dict(rank=1, chunk_id=f'{strategy}:{index}', document_id=p.document_id,
                physical_page=p.page, source=p.source, section=p.metadata['section'],
                start_char=0, end_char=len(text), text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                source_sha256=q['source_sha256'], page_text_sha256=p.metadata['text_sha256'],
                metadata=dict(source_id=p.document_id, physical_page=p.page, section=p.metadata['section']),
                snapshot_id=self.snapshots[0 if strategy == 'A' else 1].snapshot_id,
                dataset_id=r.prepared.baseline.dataset_id, profile_id=r.prepared.profile.profile_id,
                stored_strategy='B' if strategy == 'C' else strategy, requested_strategy=strategy,
                score=1.0, cosine_distance=0.0)]
    class Store:
        dataset_id = r.prepared.baseline.dataset_id
        profile_id = r.prepared.profile.profile_id
        @contextmanager
        def retrieval_session(self, **kwargs):
            assert len(adapter.calls) == 5 and kwargs['baseline'] is r.prepared.baseline
            assert kwargs['deadline_seconds'] == 120
            state.active = True
            state.opens += 1
            try: yield Session()
            finally:
                state.active = False
                state.closes += 1
    r.runtime.side_effect = None
    r.runtime.return_value = (producer, Store())
    return questions, adapter, state


def test_test_only_five_queries_filter_behavior_and_artifacts(ready):
    freeze(ready)
    questions, adapter, state = wire_test_runtime(ready)
    assert lab.execute(arguments(), root=ready.s.root) == 0
    result = lab.read_json(ready.s.root / arguments().output / 'raw_run.json')
    assert result['status'] == 'COMPLETE' and len(result['traces']) == 15
    assert result['manifest']['provenance'] == 'local_lab_test'
    assert result['manifest']['configuration']['selected_strategy'] == 'A'
    assert len(adapter.calls) == 5 and state.opens == state.closes == 1 and not state.active
    for index, q in enumerate(questions):
        calls = state.searches[index * 3:index * 3 + 3]
        assert [c[0] for c in calls] == ['A', 'B', 'C']
        assert len({c[1] for c in calls}) == 1
        assert [c[2] for c in calls] == [None, None, q.get('filter')]
    assert all(t['split'] == 'test' for t in result['traces'])
    assert {g['exact_hit_at_1']['denominator'] for g in result['summary']['groups']} == {5}
    assert len(result['manual_review']['grounding']) == 15
    assert len(result['manual_review']['metadata']) == 45
    exported = lab.read_json(ready.s.root / arguments().output / 'exported/run.json')
    assert all(runner.verify_exported_trace(t) for t in exported['traces'])
    # The protected gate still rejects TEST; local execution never changes it.
    with pytest.raises(PermissionError, match='TEST_EXECUTION_BLOCKED'):
        runner.authorize_test_execution('test')


@pytest.mark.parametrize('case', [1, 8, 15, 'embedding', 'source'])
def test_partial_artifacts_no_retry_no_secret(ready, case):
    freeze(ready)
    _, _, state = wire_test_runtime(ready, fail_at=case if isinstance(case, int) else None,
        embedding_error=case == 'embedding', bad_text=case == 'source')
    assert lab.execute(arguments(), root=ready.s.root) == 1
    raw = (ready.s.root / arguments().output / 'raw_run.json').read_text()
    result = json.loads(raw)
    assert result['status'] == 'INCOMPLETE' and result['summary'] is None
    assert 'DO_NOT_EXPORT' not in raw
    assert state.opens == state.closes == (0 if case == 'embedding' else 1)
    if isinstance(case, int): assert len(state.searches) == len(result['traces']) == case
    assert (ready.s.root / arguments().output / 'exported/run.json').exists()


def test_empty_results_are_misses_with_no_fabricated_manual_labels(ready):
    freeze(ready)
    wire_test_runtime(ready, empty=True)
    assert lab.execute(arguments(), root=ready.s.root) == 0
    result = lab.read_json(ready.s.root / arguments().output / 'raw_run.json')
    assert all(g['exact_evidence_hit_at_3']['numerator'] == 0 for g in result['summary']['groups'])
    assert all(row['label'] is None for row in result['manual_review']['grounding'])


@pytest.mark.parametrize('category', ['output', 'query_cache'])
def test_no_overwrite_before_runtime(ready, category):
    freeze(ready)
    path = ready.s.root / getattr(arguments(), category)
    path.mkdir(parents=True)
    marker = path / 'keep.txt'
    marker.write_text('existing evidence')
    with pytest.raises(FileExistsError): lab.execute(arguments(), root=ready.s.root)
    assert marker.read_text() == 'existing evidence'
    ready.runtime.assert_not_called()


def test_completed_run_cannot_be_overwritten(ready):
    freeze(ready)
    wire_test_runtime(ready)
    assert lab.execute(arguments(), root=ready.s.root) == 0
    path = ready.s.root / arguments().output / 'raw_run.json'
    before = path.read_bytes()
    with pytest.raises(FileExistsError): lab.execute(arguments(), root=ready.s.root)
    assert before == path.read_bytes()
    assert ready.runtime.call_count == 1


def test_wrong_test_split_before_runtime(ready, monkeypatch):
    freeze(ready)
    path = ready.s.folder / 'test.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['split'] = 'dev'
    path.write_text('\n'.join(json.dumps(q) for q in rows))
    # Isolate the entrypoint's additional split check; do not alter authorization.
    monkeypatch.setattr(ready.deps[2][0], 'prepare_dev', Mock(return_value=ready.prepared))
    with pytest.raises(ValueError): lab.execute(arguments(), root=ready.s.root)
    ready.runtime.assert_not_called()


@pytest.mark.parametrize('mutation', ['split', 'count', 'duplicate'])
def test_local_loop_rejects_bad_split_without_query_or_database(ready, mutation):
    selection = freeze(ready)
    questions, _, _ = wire_test_runtime(ready)
    if mutation == 'split': questions[0]['split'] = 'dev'
    elif mutation == 'count': questions.pop()
    else: questions[1]['id'] = questions[0]['id']
    producer, store = ready.runtime.return_value
    producer.prepare = Mock(side_effect=AssertionError('must not encode'))
    with pytest.raises(ValueError, match='five TEST'):
        lab.run_test(ready.prepared, questions, selection, store, producer, runner, evaluation, IDENTITY)
    producer.prepare.assert_not_called()


def test_real_runtime_factory_uses_mock_adapter_and_interactive_day6(ready, monkeypatch):
    # Exercise actual factory wiring with fake model files and a fake constructor.
    # Neither getpass nor a driver connection is invoked by construction.
    prepared = ready.prepared
    snapshot = ready.s.root / 'synthetic-model'
    snapshot.mkdir()
    (snapshot / 'config.json').write_text('synthetic only')
    prepared.plan['model'] = dict(snapshot='synthetic-model', model_name='fixture', revision='fixture',
                                  profile={'artifact_sha256': {'config.json': 'fixture'}})
    cache = ready.s.root / arguments().query_cache
    adapter = Adapter(prepared.profile, cache)
    factory = ready.deps[2][1].MyEmbedder
    factory.side_effect = None
    factory.return_value = adapter
    password = Mock(side_effect=AssertionError('must not ask for password during construction'))
    monkeypatch.setattr(dev, 'terminal_password', password)
    connector = Mock(return_value='synthetic store')
    monkeypatch.setattr(dev, 'make_store', connector)
    producer, store = ready.real_runtime(prepared, arguments(), cache, ready.s.root, ready.deps)
    assert producer.profile.profile_id == prepared.profile.profile_id and store == 'synthetic store'
    factory.assert_called_once_with('fixture', revision='fixture', snapshot_path=snapshot,
                                     cache_dir=cache, batch_size=16)
    assert connector.call_args.args[1:3] == ('day6', password)
    password.assert_not_called()


def test_model_inventory_failure_precedes_adapter_construction(ready):
    ready.prepared.plan['model'] = dict(snapshot='missing-model',
        profile={'artifact_sha256': {'config.json': 'fixture'}})
    with pytest.raises(ValueError, match='inventory'):
        ready.real_runtime(ready.prepared, arguments(), ready.s.root / arguments().query_cache,
                         ready.s.root, ready.deps)
    ready.deps[2][1].MyEmbedder.assert_not_called()


def test_anchors_match_actual_normalized_corpus():
    manifest = lab.read_json(ROOT / 'data/manifest.json')
    pages = {(s['source_id'], p['physical_page']): p for s in manifest['sources'] for p in s['pages']}
    with (ROOT / 'results/coherence_anchors.csv').open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 10 and [int(r['physical_page']) for r in rows] == list(range(97, 107))
    for row in rows:
        p = pages[row['source_id'], int(row['physical_page'])]
        data = (ROOT / p['text_path']).read_bytes()
        text = data.decode('utf-8')
        assert hashlib.sha256(data).hexdigest() == p['text_sha256']
        assert len(text) == int(row['normalized_char_count']) == p['normalized_char_count']
        assert 0 <= int(row['offset_0based']) == len(text) // 2 < len(text)


def test_import_safe_and_cli_sanitizes_errors(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location('isolated_local_test', lab.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(lab, 'execute', Mock(side_effect=ValueError('password=DO_NOT_EXPORT')))
    assert lab.main(['run', '--role', 'day6', '--output', 'x', '--query-cache', 'y']) == 1
    assert capsys.readouterr().err == 'LOCAL_LAB_TEST_FAILED_NO_RETRY\n'
    tree = ast.parse(Path(lab.__file__).read_text())
    calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls.intersection({'upsert', 'sync_snapshot', 'embed_documents', 'consume', 'authorize_test_execution'})
