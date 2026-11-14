"""Explicit local-lab DEV execution; never authorizes protected Stage 5 or TEST.

Importing this module performs no model, database, credential or filesystem writes.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import getpass
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]


def terminal_password():
    if not sys.stdin.isatty():
        raise PermissionError('Interactive terminal required')
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        return getpass.getpass('Local lab PostgreSQL password: ')


def lab_path(root, value, category):
    root = Path(root).resolve()
    path = Path(value)
    candidate = path if path.is_absolute() else root / path
    base = root / 'data/local/lab_benchmark' / category
    if '..' in path.parts or not candidate.resolve().is_relative_to(base.resolve()) or candidate.resolve() == base.resolve():
        raise ValueError('Invalid local lab destination')
    for part in (candidate, *candidate.parents):
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Linked destination forbidden')
    if candidate.exists():
        raise FileExistsError('New destination required')
    return candidate


def dependencies():
    # The script directory, rather than the workspace, is sys.path[0] in CLI use.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from starter.src import dev_bootstrap, embeddings, evaluation_runner, store
    return dev_bootstrap, embeddings, evaluation_runner, store


def make_store(prepared, role, password_reader, store_module, boot):
    class LocalReadOnlyStore(store_module.PgVectorStore):
        def _connect(self, *, readonly=False):
            if readonly is not True:
                raise PermissionError('Writable connection forbidden')
            import psycopg
            password = password_reader()
            if not isinstance(password, str) or not password:
                raise PermissionError('Password required')
            try:
                connection = psycopg.connect(host='127.0.0.1', port=55433,
                    dbname='day6_lab', user=role, password=password,
                    connect_timeout=5, autocommit=True,
                    options='-c default_transaction_read_only=on')
            finally:
                password = None
            try:
                info = connection.info
                if (info.host, info.port, info.dbname, info.user) != ('127.0.0.1', 55433, 'day6_lab', role):
                    raise ValueError()
            except Exception:
                connection.close()
                raise PermissionError('Connection identity rejected') from None
            return connection

        @contextmanager
        def retrieval_session(self, **kwargs):
            approved_catalog = getattr(boot, 'APPROVED_CATALOG', None)
            if not isinstance(approved_catalog, str) or not re.fullmatch(r'[0-9a-f]{64}', approved_catalog):
                raise PermissionError('Approved catalog required')
            with super().retrieval_session(**kwargs) as session:
                # Observe identity inside the same read-only retrieval transaction.
                with session._connection.cursor() as cursor:
                    cursor.execute("SELECT current_database(),current_setting('server_version_num'),"
                        "(SELECT system_identifier::text FROM pg_catalog.pg_control_system()),"
                        "(SELECT extversion FROM pg_extension WHERE extname='vector'),"
                        "session_user,current_user,current_setting('transaction_read_only')")
                    if cursor.fetchone() != ('day6_lab', '160016', boot.CLUSTER, '0.8.7', role, role, 'on'):
                        raise PermissionError('Database identity rejected')
                    # Independent approval pin, not just database self-consistency.
                    # Use the owned retrieval connection before exposing searches.
                    try:
                        cursor.execute('SELECT catalog_sha256,day6_ingestion.catalog_fingerprint() '
                            'FROM day6_ingestion.schema_migrations WHERE version=1')
                        if cursor.fetchall() != [(approved_catalog, approved_catalog)]:
                            raise PermissionError('Catalog identity rejected')
                    except Exception:
                        raise PermissionError('Catalog verification failed') from None
                yield session

    return LocalReadOnlyStore('LOCAL_LAB_PRIVATE_CONNECTOR', 384,
        dataset_id=prepared.baseline.dataset_id, profile_id=prepared.profile.profile_id,
        profile=prepared.profile, context=prepared.context)


def execute(args, *, root=ROOT, password_reader=None):
    if args.split != 'dev' or args.top_k != 3 or args.deadline_seconds != 120:
        raise ValueError('DEV A/B/C top-3 deadline-120 only')
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_-]{0,62}', args.role):
        raise ValueError('Explicit login role required')
    output = lab_path(root, args.output, 'dev')
    cache = lab_path(root, args.query_cache, 'query_cache')
    boot, embedding, runner, store_module = dependencies()
    # prepare_dev validates both frozen file identities, but returns only DEV.
    prepared = boot.prepare_dev(root=root, split='dev')
    model = prepared.plan['model']
    snapshot = Path(root) / model['snapshot']
    expected = set(model['profile']['artifact_sha256'])
    allowed_dirs = {p.as_posix() for name in expected for p in Path(name).parents if str(p) != '.'} | {'2_Normalize'}
    for path in (snapshot, *snapshot.parents):
        if path == Path(root):
            break
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Linked model path forbidden')
    seen = set()
    for path in snapshot.rglob('*'):
        name = path.relative_to(snapshot).as_posix()
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Linked model entry forbidden')
        if path.is_file():
            seen.add(name)
        elif not path.is_dir() or name not in allowed_dirs:
            raise ValueError('Unexpected model directory')
    if seen != expected:
        raise ValueError('Model inventory mismatch')
    adapter = embedding.MyEmbedder(model['model_name'], revision=model['revision'],
        snapshot_path=snapshot, cache_dir=cache, batch_size=16)
    producer = runner.QueryProducer(adapter, prepared.profile, cache_root=cache)
    reader = password_reader or terminal_password
    store = make_store(prepared, args.role, reader, store_module, boot)
    identity = deepcopy(prepared.plan['code'])
    identity['local_lab_entrypoint_sha256'] = runner.file_sha(Path(__file__))
    result = runner.run_evaluation(prepared.bundle, store=store, producer=producer,
        baseline=prepared.baseline, config=deepcopy(runner.DEFAULT_CONFIG), identity=identity,
        backend_identity=dict(provenance='local_lab_dev', identity_check='same_retrieval_transaction'),
        output_directory=None)
    result['manifest'].update(provenance='local_lab_dev', protected_stage5_authorization=False)
    # Revalidate immediately before creation. Never overwrite earlier evidence.
    output = lab_path(root, args.output, 'dev')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    descriptor = os.open(output / 'raw_run.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    runner.write_artifacts(result, output / 'exported')
    return 0 if result['status'] == 'COMPLETE' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['dev'], default='dev')
    parser.add_argument('--top-k', type=int, choices=[3], default=3)
    parser.add_argument('--deadline-seconds', type=int, choices=[120], default=120)
    parser.add_argument('--role', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--query-cache', required=True)
    args = parser.parse_args(argv)
    try:
        return execute(args)
    except Exception:
        # Backend/native errors can contain passwords, SQL or private paths.
        print('LOCAL_LAB_DEV_FAILED_NO_RETRY', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
