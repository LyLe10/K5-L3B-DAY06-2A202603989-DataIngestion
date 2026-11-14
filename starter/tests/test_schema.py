"""Offline contracts only: no connection, DDL, model encoding or corpus writes."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from starter.src.schema import (
    MIGRATIONS, EmbeddingProfile, Namespace, SchemaError, Snapshot, canonical_json,
    load_migrations, plan_migrations, require_compatible, retrieval_namespace, section_filter,
)


@pytest.fixture
def config():
    # Unit configuration only; not model provenance, corpus or embedding evidence.
    return dict(profile_schema_version=1, model_name='unit/model', revision='a' * 40,
                dimensions=384, dtype='float32', pooling='mean', normalize_embeddings=True,
                document_prefix='passage: ', query_prefix='query: ', max_seq_length=512,
                device='cpu', backend='torch', trust_remote_code=False, pooling_include_prompt=True,
                tokenizer=dict(name='unit/model', revision='a' * 40, use_fast=True,
                               model_max_length=512, **{'class': 'UnitTokenizerFast'}),
                artifact_sha256={'unit.safetensors': 'b' * 64},
                library_versions={'unit-library': '1.0'})


def test_profile_deterministic_detached_and_immutable(config):
    profile = EmbeddingProfile.from_config(config)
    reordered = dict(reversed(list(config.items())))
    assert EmbeddingProfile.from_config(reordered).profile_id == profile.profile_id
    assert profile.profile_id == hashlib.sha256(profile.config_canonical.encode()).hexdigest()
    config['tokenizer']['name'] = 'changed'
    detached = profile.config
    detached['tokenizer']['name'] = 'changed again'
    assert profile.config['tokenizer']['name'] == 'unit/model'
    with pytest.raises(FrozenInstanceError):
        profile.config_canonical = '{}'


@pytest.mark.parametrize('field,value', [
    ('dimensions', 768), ('dimensions', True), ('normalize_embeddings', 1),
    ('document_prefix', 'query: '), ('max_seq_length', 514), ('revision', 'main'),
    ('pooling', 'cls'), ('dtype', 'float16'), ('device', 'cuda'),
    ('trust_remote_code', True), ('pooling_include_prompt', False),
    ('artifact_sha256', {}), ('library_versions', {}),
])
def test_profile_rejects_incompatible_configuration(config, field, value):
    config[field] = value
    with pytest.raises(SchemaError):
        EmbeddingProfile.from_config(config)


@pytest.mark.parametrize('mutate', [
    lambda c: c.pop('tokenizer'),
    lambda c: c.update(extra='unexpected'),
    lambda c: c['tokenizer'].update(revision='c' * 40),
    lambda c: c['tokenizer'].update(use_fast=False),
    lambda c: c['tokenizer'].update(model_max_length=512.0),
    lambda c: c['artifact_sha256'].update(bad='invalid'),
    lambda c: c['library_versions'].update(bad=''),
])
def test_profile_missing_or_corrupt_provenance(config, mutate):
    mutate(config)
    with pytest.raises(SchemaError):
        EmbeddingProfile.from_config(config)


def test_profile_rejects_noncanonical_json_and_conflicts(config):
    profile = EmbeddingProfile.from_config(config)
    with pytest.raises(SchemaError):
        EmbeddingProfile(json.dumps(config))
    changed = deepcopy(config)
    changed['library_versions']['unit-library'] = '2.0'
    other = EmbeddingProfile.from_config(changed)
    assert profile.profile_id != other.profile_id
    with pytest.raises(SchemaError):
        profile.assert_same(other)
    profile.assert_same(EmbeddingProfile.from_config(config))


@pytest.mark.parametrize('value', [float('nan'), float('inf'), object()])
def test_canonical_json_refuses_unserializable_or_nonfinite(value):
    with pytest.raises(SchemaError):
        canonical_json({'value': value})


def test_namespace_isolation_and_c_reuse():
    namespaces = [Namespace(d, p, s) for d in ['dataset-one', 'dataset-two']
                  for p in ['a' * 64, 'b' * 64] for s in ['A', 'B']]
    assert len({n.parameters for n in namespaces}) == 8
    assert len({n.lock_key for n in namespaces}) == 8
    for n in namespaces:
        assert n.lock_key == Namespace(*n.parameters).lock_key
        assert -(2**63) <= n.lock_key < 2**63
    assert retrieval_namespace('dataset-one', 'a' * 64, 'C') == namespaces[1]
    with pytest.raises(SchemaError):
        Namespace('dataset-one', 'a' * 64, 'C')


@pytest.mark.parametrize('dataset,profile,strategy', [
    ('../escape', 'a' * 64, 'A'), ('x:y', 'a' * 64, 'A'),
    ('x', 'main', 'A'), ('x', 'a' * 64, 'D'), ('', 'a' * 64, 'A'),
])
def test_namespace_rejects_ambiguous_or_invalid_identifiers(dataset, profile, strategy):
    with pytest.raises(SchemaError):
        Namespace(dataset, profile, strategy)


@pytest.mark.parametrize('filters', [{'year': 2026}, {'section': None},
                                    {'section': ''}, {'section': 1}, [], 'section'])
def test_filter_fails_closed(filters):
    with pytest.raises(SchemaError):
        section_filter(filters)


def test_filter_value_is_kept_as_data_without_interpolation():
    value = "x' OR true --"
    assert section_filter({'section': value}) == (value,)
    assert section_filter(None) == section_filter({}) == (None,)


def snapshot(strategy, **changes):
    initial = dict(namespace=Namespace('unit-corpus', 'a' * 64, strategy),
                   manifest_sha256='b' * 64, corpus_sha256='c' * 64,
                   chunkset_sha256=('d' if strategy == 'A' else 'e') * 64,
                   selected_page_count=40, expected_count=246 if strategy == 'A' else 264,
                   actual_count=246 if strategy == 'A' else 264, status='complete')
    initial.update(changes)
    return Snapshot(**initial)


def test_comparison_allows_different_chunking_but_same_corpus_profile():
    a, b = snapshot('A'), snapshot('B')
    require_compatible(a, b)
    assert a.snapshot_id != b.snapshot_id
    assert a.snapshot_id == snapshot('A').snapshot_id
    syncing = replace(a, actual_count=0, status='syncing')
    assert syncing.snapshot_id == a.snapshot_id


@pytest.mark.parametrize('changes', [
    dict(namespace=Namespace('another-corpus', 'a' * 64, 'B')),
    dict(namespace=Namespace('unit-corpus', 'f' * 64, 'B')),
    dict(manifest_sha256='f' * 64), dict(corpus_sha256='f' * 64),
    dict(selected_page_count=41), dict(status='syncing', actual_count=0),
])
def test_comparison_blocks_incompatible_snapshots(changes):
    with pytest.raises(SchemaError):
        require_compatible(snapshot('A'), snapshot('B', **changes))


@pytest.mark.parametrize('changes', [dict(actual_count=263), dict(selected_page_count=29),
                                    dict(expected_count=0), dict(actual_count=True),
                                    dict(status='unknown'), dict(corpus_sha256='bad')])
def test_snapshot_rejects_invalid_count_and_checksum(changes):
    with pytest.raises(SchemaError):
        snapshot('B', **changes)


@pytest.fixture
def migration_copy(tmp_path):
    target = tmp_path / 'migrations'
    shutil.copytree(MIGRATIONS, target)
    return target


def test_migration_checksum_and_replay_decision():
    migrations = load_migrations()
    assert len(migrations) == 1
    assert plan_migrations(migrations, schema_exists=False) == migrations
    m = migrations[0]
    history = [(m.version, m.name, m.checksum)]
    assert plan_migrations(migrations, schema_exists=True, applied=history, catalog_matches=True) == ()
    for options in [dict(schema_exists=True),
                    dict(schema_exists=True, applied=history, catalog_matches=False),
                    dict(schema_exists=False, applied=history),
                    dict(schema_exists=True, applied=[None], catalog_matches=True),
                    dict(schema_exists=True, applied=[(1, m.name, '0' * 64)], catalog_matches=True),
                    dict(schema_exists=True, applied=history + [(2, 'unknown', '0' * 64)], catalog_matches=True)]:
        with pytest.raises(SchemaError):
            plan_migrations(migrations, **options)


@pytest.mark.parametrize('corruption', ['content', 'crlf', 'bom', 'extra-file', 'missing-file'])
def test_migration_tampering_is_not_repaired(migration_copy, corruption):
    path = next(migration_copy.glob('*.sql'))
    original = path.read_bytes()
    if corruption == 'content':
        path.write_bytes(original + b'-- changed\n')
    elif corruption == 'crlf':
        path.write_bytes(original.replace(b'\n', b'\r\n'))
    elif corruption == 'bom':
        path.write_bytes(b'\xef\xbb\xbf' + original)
    elif corruption == 'extra-file':
        (migration_copy / '0002_unregistered.sql').write_bytes(b'SELECT 1;\n')
    else:
        path.unlink()
    with pytest.raises(SchemaError):
        load_migrations(migration_copy)


@pytest.mark.parametrize('mutation', ['version', 'duplicate', 'path', 'hash', 'unknown-schema-version'])
def test_migration_registry_rejects_unknown_history(migration_copy, mutation):
    path = migration_copy / 'manifest.json'
    registry = json.loads(path.read_text())
    if mutation == 'version':
        registry['migrations'][0]['version'] = 2
    elif mutation == 'duplicate':
        registry['migrations'].append(registry['migrations'][0].copy())
    elif mutation == 'path':
        registry['migrations'][0]['name'] = '../outside.sql'
    elif mutation == 'hash':
        registry['migrations'][0]['sha256'] = 'invalid'
    else:
        registry['schema_version'] = 99
    path.write_text(json.dumps(registry))
    with pytest.raises(SchemaError):
        load_migrations(migration_copy)


def test_sql_has_required_schema_boundaries_and_commit_guards():
    sql = load_migrations()[0].sql
    tables = re.findall(r'CREATE TABLE ([a-z0-9_.]+)', sql)
    assert set(tables) == {f'day6_ingestion.{name}' for name in
                           ['schema_migrations', 'embedding_profiles', 'strategy_snapshots', 'chunks']}
    assert not re.search(r'^\s*(DROP|ALTER|TRUNCATE|CREATE EXTENSION)\b', sql, re.M | re.I)
    assert 'embedding public.vector(384) NOT NULL' in sql
    assert 'PRIMARY KEY (dataset_id, profile_id, strategy, chunk_id)' in sql
    assert 'FOREIGN KEY (dataset_id, profile_id, strategy, snapshot_id, manifest_sha256, corpus_sha256)' in sql
    assert 'DEFERRABLE INITIALLY DEFERRED' in sql
    assert 'catalog_fingerprint() IS DISTINCT FROM applied_catalog' in sql
    assert 'profile_content_address CHECK' in sql
    assert "metadata->>'text_sha256' = page_text_sha256" in sql
    assert 'a.manifest_sha256 = b.manifest_sha256 AND a.corpus_sha256 = b.corpus_sha256' in sql


def test_offline_planner_has_no_apply_option_or_database_side_effects():
    script = Path(__file__).resolve().parents[1] / 'scripts/plan_schema.py'
    result = subprocess.run([sys.executable, '-B', str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['database_connected'] is report['ddl_executed'] is False
    assert report['migrations'][0]['sha256'] == load_migrations()[0].checksum
    rejected = subprocess.run([sys.executable, '-B', str(script), '--apply'], capture_output=True, text=True)
    assert rejected.returncode == 2
