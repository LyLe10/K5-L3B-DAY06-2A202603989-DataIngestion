"""Explicit Docker-only synthetic migration probe; never connects to a host DB."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from starter.src.schema import EmbeddingProfile, Namespace, Snapshot, canonical_json, load_migrations

CONTAINER = 'day6-cp42-isolated-20261114'
MAIN = 'day6_student_starter-postgres-1'
GIT = ['git', '--no-optional-locks', '-c', 'safe.directory=' + ROOT.as_posix()]


class ProbeFailed(RuntimeError):
    pass


def literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def fixture_profile(tag='one'):
    # Synthetic configuration, never a claim about actual model artifacts.
    return EmbeddingProfile.from_config(dict(
        profile_schema_version=1, model_name='synthetic/' + tag, revision='a' * 40,
        dimensions=384, dtype='float32', pooling='mean', normalize_embeddings=True,
        document_prefix='passage: ', query_prefix='query: ', max_seq_length=512,
        device='cpu', backend='torch', trust_remote_code=False, pooling_include_prompt=True,
        tokenizer=dict(name='synthetic/' + tag, revision='a' * 40, use_fast=True,
                       model_max_length=512, **{'class': 'SyntheticTokenizerFast'}),
        artifact_sha256={'synthetic.fixture': 'b' * 64}, library_versions={'fixture': '1'}))


def profile_insert(profile):
    c = profile.config
    values = [profile.profile_id, c['model_name'], c['revision'], 384,
              profile.config_canonical, profile.config_canonical]
    return ('INSERT INTO day6_ingestion.embedding_profiles '
            '(profile_id,model_name,revision,dimensions,config_canonical,config) VALUES ('
            + ','.join(map(literal, values)) + ');')


def chunking(strategy):
    return dict(strategy=strategy, algorithm_version=1, unit='characters',
                parameters=dict(size=500, overlap=50) if strategy == 'A' else dict(max_size=500))


def synthetic_snapshot(dataset, profile, strategy, corpus='c' * 64):
    return Snapshot(Namespace(dataset, profile.profile_id, strategy), 'b' * 64,
                    corpus, ('d' if strategy == 'A' else 'e') * 64, 30, 30, 0, 'syncing')


def snapshot_insert(snapshot):
    n = snapshot.namespace
    values = [*n.parameters, snapshot.snapshot_id, snapshot.manifest_sha256,
              snapshot.corpus_sha256, snapshot.chunkset_sha256, canonical_json(chunking(n.strategy)),
              30, 30, 0, 'syncing']
    return ('INSERT INTO day6_ingestion.strategy_snapshots '
            '(dataset_id,profile_id,strategy,snapshot_id,manifest_sha256,corpus_sha256,'
            'chunkset_sha256,chunking_config,selected_page_count,expected_count,actual_count,status) VALUES ('
            + ','.join(map(literal, values)) + ');')


def chunk_values(snapshot, page=1):
    n = snapshot.namespace
    text = f'Synthetic constraint fixture page {page}.'
    digest = hashlib.sha256(text.encode()).hexdigest()
    section = 'synthetic-alpha' if page <= 15 else 'synthetic-beta'
    config = dict(chunking(n.strategy), start_char=0, end_char=len(text), split_sql_statement=False)
    metadata = dict(source_id='synthetic-document', page_id=f'synthetic:{page}', physical_page=page,
                    printed_page_label=None, section=section, section_evidence='Synthetic fixture heading',
                    version=None, normalized_char_count=len(text), text_sha256=digest,
                    extraction_status='ok', _chunking=config)
    return dict(dataset_id=n.dataset_id, profile_id=n.profile_id, strategy=n.strategy,
                chunk_id=n.strategy + ':' + hashlib.sha256(f'fixture:{page}'.encode()).hexdigest(),
                snapshot_id=snapshot.snapshot_id, manifest_sha256=snapshot.manifest_sha256,
                corpus_sha256=snapshot.corpus_sha256, document_id='synthetic-document',
                source='synthetic://constraint-fixture', source_sha256='f' * 64,
                physical_page=page, printed_page_label=None, page_id=f'synthetic:{page}', section=section,
                text=text, text_sha256=digest, page_text_sha256=digest,
                normalized_char_count=len(text), start_char=0, end_char=len(text),
                metadata=canonical_json(metadata), embedding='[' + ','.join(['1'] + ['0'] * 383) + ']')


def chunk_insert(values):
    return ('INSERT INTO day6_ingestion.chunks (' + ','.join(values) + ') VALUES ('
            + ','.join(map(literal, values.values())) + ');')


def namespace_where(snapshot):
    return ' AND '.join(k + '=' + literal(v) for k, v in
                        zip(['dataset_id', 'profile_id', 'strategy'], snapshot.namespace.parameters))


def snapshot_fixture(snapshot):
    return (snapshot_insert(snapshot) + '\n'
            + '\n'.join(chunk_insert(chunk_values(snapshot, page)) for page in range(1, 31))
            + "\nUPDATE day6_ingestion.strategy_snapshots SET actual_count=30,status='complete',"
            + 'completed_at=transaction_timestamp() WHERE ' + namespace_where(snapshot) + ';')


def run_suite(check, migration, evidence):
    check('empty_isolated_schema', "SELECT to_regnamespace('day6_ingestion') IS NULL;", expected_output='t')
    check('install_test_extension', 'CREATE EXTENSION vector;')
    check('isolated_versions', "SELECT current_setting('server_version_num'); SELECT extversion FROM pg_extension WHERE extname='vector';",
          expected_output='160016\n0.8.7')
    prefix = "BEGIN; SELECT set_config('day6_ingestion.migration_checksum','" + migration.checksum + "',true);\n"
    check('missing_checksum', 'BEGIN;\n' + migration.sql + '\nCOMMIT;', 'P0001')
    check('ddl_rollback_injected_error', prefix + migration.sql + '\nSELECT 1/0; COMMIT;', '22012')
    check('ddl_rollback_schema_absent', "SELECT to_regnamespace('day6_ingestion') IS NULL;", expected_output='t')
    check('first_apply', prefix + migration.sql + '\nCOMMIT;')
    check('catalog_objects', "SELECT count(*) FROM pg_tables WHERE schemaname='day6_ingestion'; SELECT count(*) FROM pg_views WHERE schemaname='day6_ingestion'; SELECT count(*) FROM pg_indexes WHERE schemaname='day6_ingestion' AND indexname IN ('chunks_section_idx','chunks_page_idx'); SELECT count(*) FROM day6_ingestion.schema_migrations WHERE checksum=" + literal(migration.checksum) + ';', expected_output='4\n1\n2\n1')
    check('catalog_fingerprint', "SELECT catalog_sha256=day6_ingestion.catalog_fingerprint() FROM day6_ingestion.schema_migrations;", expected_output='t')
    check('replay', prefix + migration.sql + '\nCOMMIT;')
    check('replay_history_unchanged', 'SELECT count(*) FROM day6_ingestion.schema_migrations;', expected_output='1')
    check('checksum_mismatch', prefix.replace(migration.checksum, '0' * 64) + migration.sql + '\nCOMMIT;', 'P0001')
    check('catalog_drift_rejected', prefix + 'CREATE INDEX synthetic_drift ON day6_ingestion.chunks (section);\n' + migration.sql + '\nCOMMIT;', 'P0001')
    check('catalog_drift_rolled_back', "SELECT to_regclass('day6_ingestion.synthetic_drift') IS NULL;", expected_output='t')
    p, other = fixture_profile(), fixture_profile('two')
    a, b = [synthetic_snapshot('fixture-main', p, strategy) for strategy in ('A', 'B')]
    isolated = synthetic_snapshot('fixture-other', p, 'A')
    other_profile = synthetic_snapshot('fixture-main', other, 'A')
    incompatible_a = synthetic_snapshot('fixture-incompatible', p, 'A')
    incompatible_b = synthetic_snapshot('fixture-incompatible', p, 'B', corpus='f' * 64)
    evidence['synthetic_fixture'] = dict(profiles=2, snapshots=6, chunks=180, pages_per_snapshot=30,
                                       vector='384-dimensional unit basis fixture; not an encoded embedding')
    check('profiles_insert', 'BEGIN;' + profile_insert(p) + profile_insert(other) + 'COMMIT;')
    check('profile_duplicate', 'BEGIN;' + profile_insert(p) + 'COMMIT;', '23505')
    for operation in ['UPDATE day6_ingestion.embedding_profiles SET model_name=model_name',
                      'DELETE FROM day6_ingestion.embedding_profiles',
                      'TRUNCATE day6_ingestion.embedding_profiles CASCADE']:
        check('profile_immutable_' + operation.split()[0].lower(), 'BEGIN;' + operation + ';COMMIT;', 'P0001')
    check('profile_invalid_config', 'BEGIN;' + profile_insert(fixture_profile('bad')).replace(',384,', ',383,') + 'COMMIT;', '23514')
    check('snapshot_syncing_cannot_commit', 'BEGIN;' + snapshot_insert(a) + 'COMMIT;', 'P0001')
    check('snapshot_completion_requires_chunks', 'BEGIN;' + snapshot_insert(a) + "UPDATE day6_ingestion.strategy_snapshots SET actual_count=30,status='complete',completed_at=now(); COMMIT;", 'P0001')
    check('snapshot_missing_profile', 'BEGIN;' + snapshot_insert(a).replace(p.profile_id, '9' * 64) + 'COMMIT;', '23503')
    check('snapshot_valid_atomic_fixture', 'BEGIN;' + '\n'.join(snapshot_fixture(s) for s in [a,b,isolated,other_profile,incompatible_a,incompatible_b]) + 'COMMIT;')
    check('namespace_isolation_counts', 'SELECT dataset_id,profile_id,strategy,count(*) FROM day6_ingestion.chunks GROUP BY 1,2,3 HAVING count(*)<>30;', expected_output='')
    check('namespace_shared_ids_allowed', 'SELECT count(*) FROM day6_ingestion.chunks;', expected_output='180')
    check('snapshot_compatible_view', "SELECT dataset_id FROM day6_ingestion.compatible_snapshots ORDER BY 1;", expected_output='fixture-main')
    check('section_filter_namespace', 'SELECT count(*) FROM day6_ingestion.chunks WHERE ' + namespace_where(a) + " AND section='synthetic-alpha';", expected_output='15')
    where = namespace_where(a)
    row = chunk_values(a)
    one = where + ' AND chunk_id=' + literal(row['chunk_id'])
    check('chunk_duplicate_same_namespace', 'BEGIN;' + chunk_insert(row) + 'COMMIT;', '23505')
    mutations = [
        ('chunk_checksum', "text_sha256='" + '0'*64 + "'", '23514'),
        ('chunk_page_zero', 'physical_page=0', '23514'),
        ('chunk_offsets', 'end_char=end_char-1', '23514'),
        ('chunk_empty_text', "text=''", '23514'),
        ('chunk_missing_metadata', "metadata=metadata-'section'", '23514'),
        ('chunk_wrong_metadata', "metadata=jsonb_set(metadata,'{physical_page}','999')", '23514'),
        ('chunk_zero_vector', "embedding=" + literal('[' + ','.join(['0']*384) + ']'), '23514'),
        ('chunk_wrong_dimension', "embedding='[1,0]'", '22000'),
        ('chunk_namespace_update', "dataset_id='fixture-other'", 'P0001'),
        ('chunk_identity_update', "chunk_id='A:" + '9'*64 + "'", 'P0001'),
        ('chunk_wrong_snapshot', "snapshot_id='" + '9'*64 + "'", '23503'),
        ('chunk_bad_chunking', "metadata=jsonb_set(metadata,'{_chunking,parameters,size}','499')", 'P0001'),
    ]
    for name, change, state in mutations:
        check(name, 'BEGIN;UPDATE day6_ingestion.chunks SET ' + change + ' WHERE ' + one + ';COMMIT;', state)
    check('chunk_delete_incomplete', 'BEGIN;DELETE FROM day6_ingestion.chunks WHERE ' + one + ';COMMIT;', 'P0001')
    check('snapshot_delete_blocked', 'BEGIN;DELETE FROM day6_ingestion.strategy_snapshots WHERE ' + where + ';COMMIT;', 'P0001')
    check('snapshot_namespace_update', "BEGIN;UPDATE day6_ingestion.strategy_snapshots SET dataset_id='other' WHERE " + where + ';COMMIT;', 'P0001')
    check('snapshot_wrong_count', 'BEGIN;UPDATE day6_ingestion.strategy_snapshots SET expected_count=31,actual_count=31 WHERE ' + where + ';COMMIT;', 'P0001')
    check('snapshot_strategy_c', "BEGIN;UPDATE day6_ingestion.strategy_snapshots SET strategy='C' WHERE " + where + ';COMMIT;', 'P0001')
    check('migration_history_immutable', "BEGIN;UPDATE day6_ingestion.schema_migrations SET name=name;COMMIT;", 'P0001')
    check('chunks_truncate_blocked', 'BEGIN;TRUNCATE day6_ingestion.chunks;COMMIT;', 'P0001')
    check('atomic_delete_reinsert', 'BEGIN;DELETE FROM day6_ingestion.chunks WHERE ' + one + ';' + chunk_insert(row) + 'COMMIT;')
    check('mutation_rollback', 'BEGIN;UPDATE day6_ingestion.chunks SET source=\'synthetic://changed\' WHERE ' + one + ';SELECT 1/0;COMMIT;', '22012')
    check('mutation_rollback_preserved', 'SELECT source FROM day6_ingestion.chunks WHERE ' + one + ';', expected_output='synthetic://constraint-fixture')
    check('namespace_lock_key', 'SELECT day6_ingestion.namespace_lock_key(' + ','.join(map(literal,a.namespace.parameters)) + ');', expected_output=str(a.namespace.lock_key))
    check('final_snapshot_counts', "SELECT count(*),sum(actual_count) FROM day6_ingestion.strategy_snapshots WHERE status='complete';", expected_output='6|180')
    check('final_replay_after_mutations', prefix + migration.sql + '\nCOMMIT;')


def command(args, data=None):
    return subprocess.run(args, input=data, capture_output=True, cwd=ROOT)


def docker(*args):
    result = command(['docker', *args])
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout


def sql(body, main=False):
    # Fixed container identity and user; no connection string/production fallback.
    target, user = (MAIN, 'day6') if main else (CONTAINER, 'tester')
    if main and not body.startswith('BEGIN READ ONLY;'):
        raise RuntimeError('Main database queries must be explicitly read only')
    result = command(['docker', 'exec', '-i', target, 'psql', '-X', '-q', '-A', '-t',
                      '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose',
                      '-U', user, '-d', 'day6_lab'], body.encode())
    out = result.stdout.decode(errors='replace').strip()
    err = result.stderr.decode(errors='replace').strip()
    state = re.search(r'ERROR:\s+([0-9A-Z]{5}):', err)
    return dict(returncode=result.returncode, sqlstate=state.group(1) if state else ('00000' if result.returncode == 0 else None), stdout=out, stderr=err)


def protected():
    files = command(GIT + ['ls-files', '-z', '--cached', '--others', '--exclude-standard']).stdout.split(b'\0')
    hashes = {}
    for raw in files:
        if raw:
            name = raw.decode()
            if name.startswith('results/schema_integration'):
                continue
            hashes[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    inventory = []
    for base, dirs, names in os.walk(ROOT / 'data/local'):
        dirs.sort()
        for name in sorted(names):
            path = Path(base) / name
            stat = path.lstat()
            inventory.append((path.relative_to(ROOT).as_posix(), stat.st_size, stat.st_mtime_ns))
    return dict(files=hashes, local_inventory_sha256=hashlib.sha256(json.dumps(inventory).encode()).hexdigest(),
                local_file_count=len(inventory), refs=command(GIT + ['show-ref', '--heads', '--tags']).stdout.decode(),
                origin_main=command(GIT + ['rev-parse', 'origin/main']).stdout.decode().strip())


def main():
    info = json.loads(docker('inspect', CONTAINER))[0]
    primary = json.loads(docker('inspect', MAIN))[0]
    assert info['Id'] != primary['Id']
    assert info['Config']['Labels']['day6.checkpoint'] == '4.2-isolated'
    assert info['HostConfig']['NetworkMode'] == 'none'
    assert not info['Mounts'] and not info['HostConfig']['PortBindings']
    assert info['HostConfig']['Tmpfs'] == {'/var/lib/postgresql/data': 'rw'}
    migration = load_migrations()[0]
    before = protected()
    fingerprint_sql = """BEGIN READ ONLY;
SELECT system_identifier FROM pg_control_system();
SELECT to_regnamespace('day6_ingestion');
SELECT c.oid,n.nspname,c.relname,c.relkind,c.relfilenode
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' ORDER BY c.oid;
ROLLBACK;"""
    primary_before = sql(fingerprint_sql, main=True)
    assert primary_before['returncode'] == 0
    dump_before = docker('exec', MAIN, 'pg_dump', '-U', 'day6', '-d', 'day6_lab', '--no-owner', '--no-privileges')
    # pg_dump 16 may emit random restrict keys; ignore only those control lines.
    def dump_hash(data):
        return hashlib.sha256(b'\n'.join(line for line in data.splitlines() if not line.startswith((b'\\restrict ', b'\\unrestrict ')))).hexdigest()
    evidence = dict(started_at=datetime.now(timezone.utc).isoformat(), container_id=info['Id'], image=info['Image'],
                    network='none', tmpfs=True, migration_sha256=migration.checksum, checks=[], protected_before=before,
                    main_before=primary_before, main_dump_sha256_before=dump_hash(dump_before))
    checks = evidence['checks']

    def check(name, body, state='00000', expected_output=None):
        result = sql(body)
        result.update(name=name, expected_sqlstate=state, expected_output=expected_output,
                      sql_sha256=hashlib.sha256(body.encode()).hexdigest())
        result['pass'] = (result['sqlstate'] == state
                          and ((result['returncode'] == 0) == (state == '00000'))
                          and (expected_output is None or result['stdout'] == expected_output))
        result['status'] = 'PASS' if result['pass'] else 'FAIL'
        checks.append(result)
        print(name, 'PASS' if result['pass'] else 'FAIL', result['sqlstate'], flush=True)
        if not result['pass']:
            raise ProbeFailed(name + ': ' + result['stderr'])
        return result

    try:
        check('isolated_cluster_identity', 'SELECT system_identifier FROM pg_control_system();')
        assert checks[-1]['stdout'] != primary_before['stdout'].splitlines()[0]
        run_suite(check, migration, evidence)
    except (ProbeFailed, AssertionError) as exc:
        evidence['stopped_on_failure'] = str(exc)
        evidence['blocked'] = ['All remaining integration cases after first unexpected failure; no migration repair attempted']
    evidence['protected_after'] = protected()
    evidence['protected_unchanged'] = before == evidence['protected_after']
    evidence['main_after'] = sql(fingerprint_sql, main=True)
    evidence['main_dump_sha256_after'] = dump_hash(docker('exec', MAIN, 'pg_dump', '-U', 'day6', '-d', 'day6_lab', '--no-owner', '--no-privileges'))
    evidence['main_unchanged'] = primary_before == evidence['main_after'] and evidence['main_dump_sha256_before'] == evidence['main_dump_sha256_after']
    evidence['finished_at'] = datetime.now(timezone.utc).isoformat()
    evidence['summary'] = dict(PASS=sum(c['pass'] for c in checks), FAIL=sum(not c['pass'] for c in checks),
                               BLOCKED=len(evidence.get('blocked', [])))
    (ROOT / 'results/schema_integration.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('protected_unchanged', evidence['protected_unchanged'], 'main_unchanged', evidence['main_unchanged'])
    return 0 if all(c['pass'] for c in checks) and not evidence.get('blocked') and evidence['protected_unchanged'] and evidence['main_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
