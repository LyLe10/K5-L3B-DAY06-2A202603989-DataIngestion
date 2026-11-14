"""One-shot approved CP4.3C-2 application. No encode, DDL, repair or retry."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from starter.src.corpus import load_manifest_pages
from starter.src.embeddings import CACHE, MODEL, REVISION, validate_vector
from starter.src.preparation import audit_chunks, build_strategies
from starter.src.schema import EmbeddingProfile, Namespace, canonical_json, require_compatible
from starter.src.store import PgVectorStore, SnapshotContext

PROFILE = '528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651'
CATALOG = '209b3597e6f2a6ff8cf13f4c12f5cfc45f3bb34c07f9ff363204902323a2da55'
OUTPUT = ROOT/'results/full_corpus_apply.json'
sha = lambda b: hashlib.sha256(b).hexdigest()


def readonly(url, expected, profile, *, require_empty=False, check_writers=False):
    import psycopg
    with psycopg.connect(url, connect_timeout=5,
                        options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(),current_setting('server_version_num'),"
                        "current_setting('transaction_read_only'),"
                        "(SELECT system_identifier::text FROM pg_control_system()),"
                        "(SELECT extversion FROM pg_extension WHERE extname='vector')")
            identity = cur.fetchone()
            assert identity == ('day6_lab', '160016', 'on', '7707847059457269799', '0.8.7')
            PgVectorStore._verify_schema(cur)
            cur.execute('SELECT version,checksum,catalog_sha256,day6_ingestion.catalog_fingerprint() '
                        'FROM day6_ingestion.schema_migrations')
            migration = cur.fetchone()
            assert migration[2] == migration[3] == CATALOG
            cur.execute('SELECT profile_id,config_canonical FROM day6_ingestion.embedding_profiles ORDER BY profile_id')
            profiles = cur.fetchall()
            assert profiles in ([], [(PROFILE, profile.config_canonical)])
            cur.execute('SELECT strategy,count(*) FROM day6_ingestion.chunks GROUP BY strategy ORDER BY strategy')
            counts = cur.fetchall()
            cur.execute('SELECT dataset_id,profile_id,strategy,snapshot_id,status,expected_count,actual_count,completed_at '
                        'FROM day6_ingestion.strategy_snapshots ORDER BY dataset_id,profile_id,strategy')
            ledgers = cur.fetchall()
            states = {}
            for name, (snapshot, rows, ledger) in expected.items():
                actual_ledger, actual_rows = PgVectorStore._read_sync_state(cur, snapshot.namespace)
                exact = PgVectorStore._same_materialization(actual_ledger, actual_rows, ledger, rows)
                states[name] = dict(verification='CONFIRMED_COMMITTED' if exact else
                    'CONFIRMED_NOT_COMMITTED' if actual_ledger is None and not actual_rows else 'UNKNOWN',
                    rows=len(actual_rows), full_rows_vectors_exact=exact)
            cur.execute('SELECT count(*) FROM day6_ingestion.chunks WHERE NOT '
                        "(dataset_id=%s AND profile_id=%s AND strategy IN ('A','B'))",
                        ('day06-postgresql', PROFILE))
            assert cur.fetchone()[0] == 0
            if require_empty:
                assert not profiles and not counts and not ledgers
                assert all(s['verification']=='CONFIRMED_NOT_COMMITTED' for s in states.values())
            writers = []
            if check_writers:
                cur.execute("SELECT pid,state,xact_start IS NOT NULL FROM pg_stat_activity "
                            "WHERE datname=current_database() AND pid<>pg_backend_pid() "
                            "AND backend_type='client backend' AND (state IS DISTINCT FROM 'idle' OR xact_start IS NOT NULL)")
                writers = cur.fetchall()
                assert not writers, 'Another active database client/transaction detected'
                cur.execute("SELECT count(*) FROM pg_locks WHERE locktype='advisory' "
                            "AND database=(SELECT oid FROM pg_database WHERE datname=current_database())")
                assert cur.fetchone()[0] == 0, 'Another advisory lock holder detected'
        conn.rollback()
    return dict(identity=identity, migration=migration, profile_count=len(profiles),
                counts=counts, ledgers=ledgers, namespaces=states, other_active_clients=writers,
                outside_namespace_rows=0)


def main():
    if OUTPUT.exists():
        raise RuntimeError('Application evidence exists: no automatic replay')
    report = dict(result='FAILED', started_at=datetime.now(timezone.utc).isoformat(),
                  transactions={}, errors=[], encoded_inputs=0)
    started = perf_counter()
    expected, vectors = {}, {}
    url = profile = None
    try:
        from dotenv import load_dotenv
        from psycopg.conninfo import conninfo_to_dict
        load_dotenv(ROOT/'starter/.env')
        url = os.environ['DATABASE_URL']
        info = conninfo_to_dict(url)
        assert (info['host'], info['port'], info['dbname']) == ('127.0.0.1', '55433', 'day6_lab')
        preflight = json.loads((ROOT/'results/full_corpus_embedding_preflight.json').read_text())
        assert preflight['passed'] and preflight['profile_id'] == PROFILE
        profile = EmbeddingProfile.from_config(preflight['profile'])
        assert profile.profile_id == PROFILE
        assert profile.config['model_name'] == MODEL and profile.config['revision'] == REVISION
        corpus = load_manifest_pages(ROOT/'data/manifest.json')
        context = SnapshotContext.from_ingestion_result(corpus)
        strategies = build_strategies(corpus.pages)
        assert len(corpus.pages) == 40 and strategies['C'] is strategies['B']
        assert corpus.manifest_sha256 == preflight['baseline']['manifest_sha256']
        store = PgVectorStore(url, 384, dataset_id='day06-postgresql', profile_id=PROFILE,
                              profile=profile, context=context)
        receipts = preflight['receipts']
        position = 0
        for name, count in [('A', 246), ('B', 264)]:
            chunks = strategies[name]
            assert len(chunks) == count
            saved = [json.loads(line) for line in (ROOT/f'data/local/stage3/chunks/{name}.jsonl').read_text().splitlines()]
            assert [asdict(c) for c in chunks] == saved
            audit = audit_chunks(corpus.pages, chunks, name)
            assert not audit['errors'] and audit['covered_characters'] == 103371
            vectors[name] = []
            for chunk in chunks:
                receipt = receipts[position]
                key = sha(('passage: '+chunk.text).encode())
                record = json.loads((CACHE/PROFILE/(key+'.json')).read_text())
                assert set(record) == {'cache_version','profile_id','input_sha256','vector','vector_sha256'}
                assert type(record['cache_version']) is int and record['cache_version'] == 1
                assert record['profile_id'] == PROFILE and record['input_sha256'] == key
                assert record['vector_sha256'] == sha(canonical_json(record['vector']).encode()) == receipt['vector_sha256']
                assert receipt['position'] == position and receipt['strategy'] == name
                assert receipt['chunk_id'] == chunk.chunk_id and receipt['input_sha256'] == key
                assert receipt['physical_page'] == chunk.page and receipt['section'] == chunk.metadata['section']
                for field in ('start_char','end_char'):
                    assert receipt[field] == chunk.metadata['_chunking'][field]
                vector = validate_vector(record['vector'])
                assert vector == record['vector']
                vectors[name].append(vector)
                position += 1
            pairs = store.validate_batch(name, chunks, vectors[name], vector_chunk_ids=[c.chunk_id for c in chunks],
                                         embedding_profile_id=PROFILE)
            expected[name] = store._prepare_snapshot(Namespace('day06-postgresql', PROFILE, name), context, pairs)
            assert expected[name][0].snapshot_id == preflight['planned_snapshots'][name]['snapshot_id']
        assert position == len(receipts) == 510
        require_compatible(expected['A'][0], expected['B'][0])
        # Fail closed if another local Python ingestion/application process is observed.
        other_processes = []
        for proc in Path('/proc').iterdir():
            if proc.name.isdigit() and int(proc.name) != os.getpid():
                try:
                    args = (proc/'cmdline').read_bytes().split(b'\0')
                    if args and b'python' in args[0] and any(
                        term in arg for arg in args[1:] for term in (b'apply_full_corpus', b'check_full_corpus_preflight', b'check_store_postgres')):
                        other_processes.append(int(proc.name))
                except (OSError, PermissionError):
                    pass
        assert not other_processes, 'Another local ingestion-related Python process detected'
        report['before'] = readonly(url, expected, profile, require_empty=True, check_writers=True)
        report['precheck'] = dict(passed=True, vectors=510, pages=40, coverage=103371,
                                  profile_id=PROFILE, planned_compatible=True, other_local_writer_pids=other_processes)
        print('PRE-APPLY PASS: empty target, verified cache/context/receipts; beginning A then B', flush=True)
        for name in ('A', 'B'):
            t = perf_counter()
            report['transactions'][name] = dict(outcome='IN_PROGRESS')
            try:
                result = store.sync_snapshot(name, strategies[name], vectors[name],
                    vector_chunk_ids=[c.chunk_id for c in strategies[name]], embedding_profile_id=PROFILE)
                report['transactions'][name] = dict(outcome='COMMITTED', seconds=perf_counter()-t, result=result)
                print(f'{name} COMMITTED: {result}', flush=True)
            except Exception as exc:
                report['transactions'][name] = dict(outcome='ERROR_STOPPED_NO_RETRY', seconds=perf_counter()-t,
                    error_type=type(exc).__name__, sqlstate=getattr(exc, 'sqlstate', None), error=str(exc))
                raise
        report['after'] = readonly(url, expected, profile)
        assert report['after']['profile_count'] == 1
        assert report['after']['counts'] == [('A', 246), ('B', 264)]
        assert len(report['after']['ledgers']) == 2
        assert all(s['verification']=='CONFIRMED_COMMITTED' for s in report['after']['namespaces'].values())
        assert report['after']['migration'] == report['before']['migration']
        persisted = store.require_compatible_snapshots()
        assert [s.snapshot_id for s in persisted] == [expected[n][0].snapshot_id for n in ('A','B')]
        report['postapply_compatibility'] = True
        report['result'] = 'SUCCESS'
    except Exception as exc:
        report['errors'].append(dict(type=type(exc).__name__, sqlstate=getattr(exc,'sqlstate',None), message=str(exc)))
        if url and profile and expected:
            try:
                report['after_error_readonly'] = readonly(url, expected, profile)
                statuses = [v['verification'] for v in report['after_error_readonly']['namespaces'].values()]
                report['result'] = 'UNKNOWN' if 'UNKNOWN' in statuses else 'PARTIAL' if 'CONFIRMED_COMMITTED' in statuses else 'FAILED'
            except Exception as diagnostic:
                report['result'] = 'UNKNOWN' if report['transactions'] else 'FAILED'
                report['diagnostic_error'] = type(diagnostic).__name__+': '+str(diagnostic)
        # Do not issue another write, repair, rollback-by-delete or sync retry.
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    report['total_seconds'] = perf_counter()-started
    OUTPUT.write_text(json.dumps(report, default=str, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, default=str, ensure_ascii=False, indent=2), flush=True)
    return 0 if report['result']=='SUCCESS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
