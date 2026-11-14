"""Local lab TEST and DEV selection record; protected Stage 5 remains unchanged.

Import and `freeze` are offline. Only the explicit `run` command loads the local
model and asks the operator for a password. No approval infrastructure is used.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]


def dependencies():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from starter.scripts import run_local_lab_dev as dev
    from starter.src import evaluation
    return dev, evaluation, dev.dependencies()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    def invalid(value):
        raise ValueError('Non-finite JSON number')
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=invalid)


def local_file(root, value, base):
    root = Path(root).resolve()
    path = Path(value)
    candidate = path if path.is_absolute() else root / path
    if '..' in path.parts or not candidate.resolve().is_relative_to((root / base).resolve()):
        raise ValueError('Invalid local artifact path')
    for part in (candidate, *candidate.parents):
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Linked artifact path')
    return candidate


def benchmark_config(root):
    config = read_json(Path(root) / 'results/benchmark_config.json')
    strategies = {
        'A': dict(chunking='fixed_size', size=500, overlap=50, stored_strategy='A', chunk_count=246, filter=None),
        'B': dict(chunking='by_paragraph', max_size=500, stored_strategy='B', chunk_count=264, filter=None),
        'C': dict(chunking='by_paragraph', max_size=500, stored_strategy='B', chunk_count=264,
                  filter='question-supplied section equality only'),
    }
    # This policy is predeclared; the choice itself is made only from real DEV.
    if (config['config_version'] != 1 or config['top_k'] != 3
            or config['deadline_seconds'] != 120 or config['metric_version'] != 'exact-evidence-v1'
            or config['selection_order'] != ['max dev Evidence Hit@3', 'max dev Hit@1',
                                            'min stored chunk count', 'A', 'B', 'C']
            or config['strategies'] != strategies or config['dimensions'] != 384
            or config['model'] != 'intfloat/multilingual-e5-small'
            or config['revision'] != 'fd1525a9fd15316a2d503bf26ab031a61d056e98'
            or config['metric'] != 'cosine' or config['query_prefix'] != 'query: '
            or config['document_prefix'] != 'passage: '
            or config['dev_queries'] != 15 or config['test_queries'] != 5):
        raise ValueError('Unexpected benchmark policy')
    return config


def check_hits(trace, store, baseline, evaluation, corpus):
    hits = trace['hits']
    strategy = trace['strategy']
    snapshot = baseline.snapshots[0 if strategy == 'A' else 1].snapshot_id
    if trace['snapshot_id'] != snapshot:
        raise ValueError('Trace snapshot mismatch')
    for hit in hits:
        if (hit['dataset_id'] != store.dataset_id or hit['profile_id'] != store.profile_id
                or hit['snapshot_id'] != snapshot or hit['requested_strategy'] != strategy
                or hit['stored_strategy'] != ('B' if strategy == 'C' else strategy)
                or not math.isfinite(hit['score']) or not math.isfinite(hit['cosine_distance'])
                or abs(hit['score'] - (1 - hit['cosine_distance'])) > 1e-7):
            raise ValueError('Hit identity/score mismatch')
    order = [(h['cosine_distance'], h['chunk_id']) for h in hits]
    if order != sorted(order):
        raise ValueError('Hit order mismatch')
    evaluation.validate_hits(hits, {(p.document_id, p.page): p for p in corpus.pages},
                             {s['source_id']: s for s in corpus.sources})


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result


def validate_dev(path, prepared, root, dev, evaluation, runner):
    """Recheck real DEV coverage/metrics against frozen gold, without inference."""
    path = local_file(root, path, 'data/local/lab_benchmark/dev')
    if path.name != 'raw_run.json':
        raise ValueError('Supply the original DEV raw_run.json')
    result = read_json(path)
    manifest = result['manifest']
    bundle = prepared.bundle
    questions = bundle['questions']
    identity = deepcopy(prepared.plan['code'])
    identity['local_lab_entrypoint_sha256'] = sha(dev.__file__)
    expected = dict(split='dev', provenance='local_lab_dev', protected_stage5_authorization=False,
        status='COMPLETE', question_ids=[q['id'] for q in questions],
        freeze_sha256=bundle['freeze_sha256'], benchmark_manifest_sha256=bundle['benchmark_manifest_sha256'],
        frozen_files=bundle['frozen_files'], source_checksums=bundle['source_checksums'],
        profile_id=prepared.profile.profile_id, embedding_config=prepared.profile.config,
        profile_config_sha256=evaluation.digest(prepared.profile.config),
        model_revision=prepared.profile.config['revision'], dataset_id=prepared.baseline.dataset_id,
        snapshot_ids=[s.snapshot_id for s in prepared.baseline.snapshots],
        manifest_sha256=prepared.baseline.snapshots[0].manifest_sha256,
        corpus_sha256=prepared.baseline.snapshots[0].corpus_sha256,
        descriptor_hashes=list(prepared.baseline.descriptor_hashes),
        configuration=runner.DEFAULT_CONFIG, configuration_sha256=evaluation.digest(runner.DEFAULT_CONFIG),
        attempted=45, succeeded=45, retrieved=45, failed=0)
    if (result['status'] != 'COMPLETE' or result['error'] is not None
            or any(manifest.get(k) != v for k, v in expected.items())
            or manifest['code']['source_hashes'] != identity['source_hashes']
            or manifest['code']['evaluator_sha256'] != identity['evaluator_sha256']
            or manifest['code']['local_lab_entrypoint_sha256'] != identity['local_lab_entrypoint_sha256']
            or len(questions) != 15 or any(q['split'] != 'dev' for q in questions)):
        raise ValueError('DEV incomplete or identity/configuration changed')
    # Wall clocks can step backwards (including in WSL). Ordering is established
    # by COMPLETE artifacts and their hashes, not by a new trusted-clock policy.
    timestamp(manifest['started_at'])
    timestamp(manifest['finished_at'])
    traces, receipts = result['traces'], result['receipts']
    if (len(traces) != 45 or len(receipts) != 15
            or [(t['question_id'], t['strategy']) for t in traces]
               != [(q['id'], s) for q in questions for s in ('A', 'B', 'C')]):
        raise ValueError('DEV needs exactly 45 ordered unique traces')
    store_identity = type('Identity', (), dict(dataset_id=prepared.baseline.dataset_id,
                                               profile_id=prepared.profile.profile_id))()
    for q, receipt in zip(questions, receipts, strict=True):
        if (receipt['question_id'] != q['id'] or receipt['producer_profile_id'] != prepared.profile.profile_id
                or receipt['input_sha256'] != hashlib.sha256(('query: ' + q['question']).encode()).hexdigest()
                or not re.fullmatch('[0-9a-f]{64}', receipt['vector_sha256'])
                or type(receipt['token_count']) is not int or not 1 <= receipt['token_count'] <= 512):
            raise ValueError('DEV query receipt mismatch')
    by_id = {q['id']: (q, r) for q, r in zip(questions, receipts, strict=True)}
    for trace in traces:
        question, receipt = by_id[trace['question_id']]
        scope = question.get('filter') if trace['strategy'] == 'C' else None
        if (trace['status'] != 'SUCCESS' or trace['split'] != 'dev'
                or trace['question'] != question['question'] or trace['query_receipt'] != receipt
                or trace['applied_filter'] != scope
                or trace.get('raw_trace_sha256') != evaluation.trace_identity(trace)
                or trace.get('trace_sha256') != evaluation.trace_identity(trace)):
            raise ValueError('DEV trace mismatch')
        check_hits(trace, store_identity, prepared.baseline, evaluation, bundle['corpus'])
        q = dict(question)
        if trace['strategy'] != 'C':
            q.pop('filter', None)
        if trace['evaluation'] != evaluation.evaluate_query(q, trace['hits']):
            raise ValueError('DEV metric differs from evidence')
    summary = evaluation.summarize(traces)
    if summary != result['summary']:
        raise ValueError('DEV summary mismatch')
    return result, path, summary


def choice(summary, config):
    groups = {g['strategy']: g for g in summary['groups']}
    if set(groups) != {'A', 'B', 'C'} or any(g['split'] != 'dev' or g['questions'] != 15 for g in groups.values()):
        raise ValueError('Expected three complete DEV groups')
    return min(('A', 'B', 'C'), key=lambda s: (
        -groups[s]['exact_evidence_hit_at_3']['numerator'],
        -groups[s]['exact_hit_at_1']['numerator'], config['strategies'][s]['chunk_count'], s))


def selection_payload(prepared, result, dev_path, summary, config, root):
    return dict(selection_version=1, dev_run=dev_path.relative_to(Path(root).resolve()).as_posix(),
        dev_run_sha256=sha(dev_path), dev_run_id=result['manifest']['run_id'],
        dev_finished_at=result['manifest']['finished_at'], freeze_sha256=prepared.bundle['freeze_sha256'],
        benchmark_manifest_sha256=prepared.bundle['benchmark_manifest_sha256'],
        benchmark_config_sha256=sha(Path(root) / 'results/benchmark_config.json'),
        test_entrypoint_sha256=sha(__file__), profile_id=prepared.profile.profile_id,
        manifest_sha256=prepared.baseline.snapshots[0].manifest_sha256,
        snapshot_ids=[s.snapshot_id for s in prepared.baseline.snapshots],
        configuration=deepcopy(prepared.plan['config']), selection_order=config['selection_order'],
        selected_strategy=choice(summary, config), dev_summary=summary,
        rationale='Selected from complete DEV only using the predeclared ordering; TEST not consulted.')


def prepare(root, deps):
    _, _, (boot, _, _, _) = deps
    config = benchmark_config(root)
    prepared = boot.prepare_dev(root=root, split='dev')
    return prepared, config


def freeze(args, *, root=ROOT):
    deps = dependencies()
    dev, evaluation, (_, _, runner, _) = deps
    destination = local_file(root, args.selection, 'results')
    if destination.exists():
        raise FileExistsError('Selection already exists')
    prepared, config = prepare(root, deps)
    result, path, summary = validate_dev(args.dev_run, prepared, root, dev, evaluation, runner)
    payload = selection_payload(prepared, result, path, summary, config, root)
    payload['frozen_at'] = datetime.now(timezone.utc).isoformat()
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return 0


def validate_selection(args, prepared, config, root, dev, evaluation, runner):
    path = local_file(root, args.selection, 'results')
    selection = read_json(path)
    result, dev_path, summary = validate_dev(selection['dev_run'], prepared, root, dev, evaluation, runner)
    expected = selection_payload(prepared, result, dev_path, summary, config, root)
    if {k: v for k, v in selection.items() if k != 'frozen_at'} != expected:
        raise ValueError('Selection freeze mismatch')
    timestamp(selection['frozen_at'])
    return selection


def make_runtime(prepared, args, cache, root, deps):
    dev, _, (boot, embedding, runner, store_module) = deps
    model = prepared.plan['model']
    snapshot = Path(root) / model['snapshot']
    expected = set(model['profile']['artifact_sha256'])
    for path in (snapshot, *snapshot.parents):
        if path == Path(root):
            break
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Linked model path')
    seen = set()
    for path in snapshot.rglob('*'):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Linked model entry')
        if path.is_file():
            seen.add(path.relative_to(snapshot).as_posix())
    if seen != expected:
        raise ValueError('Model inventory mismatch')
    adapter = embedding.MyEmbedder(model['model_name'], revision=model['revision'],
        snapshot_path=snapshot, cache_dir=cache, batch_size=16)
    return (runner.QueryProducer(adapter, prepared.profile, cache_root=cache),
            dev.make_store(prepared, args.role, dev.terminal_password, store_module, boot))


def run_test(prepared, questions, selection, store, producer, runner, evaluation, identity):
    """Independent local loop; reuses retrieval/scoring, never protected gates."""
    if (len(questions) != 5 or len({q['id'] for q in questions}) != 5
            or any(q['split'] != 'test' for q in questions)):
        raise ValueError('Exactly five TEST questions required')
    if (producer.profile.profile_id != store.profile_id or store.profile_id != prepared.profile.profile_id
            or store.dataset_id != prepared.baseline.dataset_id):
        raise ValueError('Query/store profile mismatch')
    config = dict(runner.DEFAULT_CONFIG, selected_strategy=selection['selected_strategy'])
    prepared.baseline.validate_approved_identity()
    manifest = dict(run_version=1, run_id=uuid.uuid4().hex, split='test', provenance='local_lab_test',
        protected_stage5_authorization=False, started_at=datetime.now(timezone.utc).isoformat(),
        question_ids=[q['id'] for q in questions], freeze_sha256=prepared.bundle['freeze_sha256'],
        benchmark_manifest_sha256=prepared.bundle['benchmark_manifest_sha256'],
        frozen_files=prepared.bundle['frozen_files'], source_checksums=prepared.bundle['source_checksums'],
        dataset_id=store.dataset_id, profile_id=store.profile_id, embedding_config=prepared.profile.config,
        profile_config_sha256=evaluation.digest(prepared.profile.config),
        manifest_sha256=prepared.baseline.snapshots[0].manifest_sha256,
        corpus_sha256=prepared.baseline.snapshots[0].corpus_sha256,
        descriptor_hashes=list(prepared.baseline.descriptor_hashes),
        model_revision=prepared.profile.config['revision'],
        snapshot_ids=[s.snapshot_id for s in prepared.baseline.snapshots],
        configuration=config, selection_freeze=selection, code=identity, library_versions=runner.dependency_versions())
    result = dict(status='INCOMPLETE', manifest=manifest, receipts=[], traces=[], summary=None,
                  manual_review=None, error=None)
    started = time.perf_counter()
    stage = 'QUERY_EMBEDDING'
    try:
        inputs = [dict(id=q['id'], question=q['question'], filter=q.get('filter')) for q in questions]
        vectors, receipts = producer.prepare(inputs)
        if len(vectors) != 5 or len(receipts) != 5:
            raise ValueError('Query count mismatch')
        for q, vector, receipt in zip(questions, vectors, receipts, strict=True):
            from starter.src.embeddings import validate_vector
            validate_vector(vector)
            if (receipt['question_id'] != q['id'] or receipt['producer_profile_id'] != store.profile_id
                    or receipt['input_sha256'] != hashlib.sha256(('query: ' + q['question']).encode()).hexdigest()
                    or receipt['vector_sha256'] != evaluation.digest(vector)
                    or not 1 <= receipt['token_count'] <= 512):
                raise ValueError('Query receipt mismatch')
        result['receipts'] = receipts
        stage = 'RETRIEVAL'
        retrieval_started = time.perf_counter()
        with store.retrieval_session(baseline=prepared.baseline, deadline_seconds=120) as session:
            manifest['integrity_labels'] = list(session.integrity)
            if tuple(s.snapshot_id for s in session.snapshots) != tuple(s.snapshot_id for s in prepared.baseline.snapshots):
                raise ValueError('Session snapshots changed')
            for q, vector, receipt in zip(questions, vectors, receipts, strict=True):
                for strategy in ('A', 'B', 'C'):
                    if time.perf_counter() - retrieval_started >= 120:
                        raise TimeoutError('Retrieval deadline')
                    trace = dict(question_id=q['id'], split='test', strategy=strategy, question=q['question'],
                        query_receipt=receipt, status='STARTED', hits=[],
                        applied_filter=q.get('filter') if strategy == 'C' else None,
                        snapshot_id=prepared.baseline.snapshots[0 if strategy == 'A' else 1].snapshot_id,
                        integrity_labels=list(session.integrity))
                    result['traces'].append(trace)
                    call = time.perf_counter()
                    hits = session.search(strategy, vector, top_k=3, filters=trace['applied_filter'])
                    trace.update(status='RETRIEVED', hits=[runner.safe_hit(h) for h in hits],
                                 retrieval_seconds=time.perf_counter() - call)
        manifest['retrieval_seconds'] = time.perf_counter() - retrieval_started
        stage = 'EVALUATION'
        by_id = {q['id']: q for q in questions}
        for trace in result['traces']:
            check_hits(trace, store, prepared.baseline, evaluation, prepared.bundle['corpus'])
            q = dict(by_id[trace['question_id']])
            if trace['strategy'] != 'C':
                q.pop('filter', None)
            trace.update(status='SUCCESS', evaluation=evaluation.evaluate_query(q, trace['hits']))
            trace['raw_trace_sha256'] = evaluation.trace_identity(trace)
            trace['trace_sha256'] = trace['raw_trace_sha256']
        result.update(status='COMPLETE', summary=evaluation.summarize(result['traces']),
                      manual_review=evaluation.manual_review_template([q['id'] for q in questions]))
    except Exception as exc:
        result['error'] = dict(type=type(exc).__name__, stage=stage, message='RUN_FAILED_NO_RETRY')
        if result['traces'] and result['traces'][-1]['status'] == 'STARTED':
            result['traces'][-1]['status'] = 'FAILED'
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=time.perf_counter() - started, status=result['status'],
        attempted=len(result['traces']), succeeded=sum(t['status'] == 'SUCCESS' for t in result['traces']))
    return result


def execute(args, *, root=ROOT):
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_-]{0,62}', args.role):
        raise ValueError('Explicit login role required')
    deps = dependencies()
    dev, evaluation, (_, _, runner, _) = deps
    output = dev.lab_path(root, args.output, 'test')
    cache = dev.lab_path(root, args.query_cache, 'query_cache')
    prepared, config = prepare(root, deps)
    selection = validate_selection(args, prepared, config, root, dev, evaluation, runner)
    # prepare_dev has validated BOTH frozen files/source spans. Never relabel DEV.
    questions = [json.loads(line) for line in (Path(root) / 'benchmark/test.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    if (sha(Path(root) / 'benchmark/test.jsonl') != prepared.bundle['frozen_files']['test.jsonl']['sha256']
            or len(questions) != 5 or len({q['id'] for q in questions}) != 5
            or any(q['split'] != 'test' for q in questions)):
        raise ValueError('Frozen TEST split mismatch')
    # All DEV/freeze/split checks precede model construction and credential access.
    producer, store = make_runtime(prepared, args, cache, root, deps)
    identity = deepcopy(prepared.plan['code'])
    identity['local_lab_test_entrypoint_sha256'] = sha(__file__)
    result = run_test(prepared, questions, selection, store, producer, runner, evaluation, identity)
    output = dev.lab_path(root, args.output, 'test')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    with (output / 'raw_run.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    runner.write_artifacts(result, output / 'exported')
    return 0 if result['status'] == 'COMPLETE' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    select = sub.add_parser('freeze', help='Offline: choose from a completed DEV run')
    select.add_argument('--dev-run', required=True)
    select.add_argument('--selection', default='results/selection_freeze.json')
    run = sub.add_parser('run', help='Operator-only: run five TEST queries after DEV selection')
    run.add_argument('--selection', default='results/selection_freeze.json')
    run.add_argument('--role', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--query-cache', required=True)
    args = parser.parse_args(argv)
    try:
        return freeze(args) if args.command == 'freeze' else execute(args)
    except Exception:
        print('LOCAL_LAB_TEST_FAILED_NO_RETRY', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
