"""Adapter unit tests with explicit doubles, never real embedding evidence."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
import math
from types import SimpleNamespace

import pytest

from starter.src.embeddings import (
    ARTIFACTS, MODEL, REVISION, EmbeddingError, MyEmbedder, TokenOverflowError,
    validate_vector,
)
from starter.src.schema import EmbeddingProfile, canonical_json


def unit_vector(text):
    vector = [0.0] * 384
    vector[int(hashlib.sha256(text.encode()).hexdigest(), 16) % 384] = 1.0
    return vector


class TokenizerDouble:
    model_max_length = 512

    def __init__(self):
        self.calls = []
        self.lengths = {}

    def __call__(self, inputs, **kwargs):
        self.calls.append((list(inputs), kwargs))
        lengths = [self.lengths.get(text, len(text.split()) + 2) for text in inputs]
        return {'input_ids': [list(range(n)) for n in lengths], 'length': lengths}


class EncoderDouble:
    max_seq_length = 512

    def __init__(self):
        self.tokenizer = TokenizerDouble()
        self.calls = []
        self.output = None

    def encode(self, inputs, **kwargs):
        self.calls.append((list(inputs), kwargs))
        return self.output if self.output is not None else [unit_vector(text) for text in inputs]


def synthetic_profile(tag='unit'):
    return EmbeddingProfile.from_config(dict(
        profile_schema_version=1, model_name=MODEL, revision=REVISION, dimensions=384,
        dtype='float32', pooling='mean', normalize_embeddings=True, document_prefix='passage: ',
        query_prefix='query: ', max_seq_length=512, device='cpu', backend='torch',
        trust_remote_code=False, pooling_include_prompt=True,
        tokenizer={'name': MODEL, 'revision': REVISION, 'class': 'UnitTokenizerFast',
                   'use_fast': True, 'model_max_length': 512},
        artifact_sha256={'unit': 'a' * 64}, library_versions={'unit-test-double': tag}))


@pytest.fixture
def adapter(tmp_path):
    embedder = MyEmbedder.__new__(MyEmbedder)
    backend = EncoderDouble()
    embedder._configure(backend, synthetic_profile(), tmp_path, 2)
    return embedder, backend


def test_prefix_tokenizer_and_encode_contract(adapter):
    embedder, backend = adapter
    assert embedder.embed_documents(['alpha']) == [unit_vector('passage: alpha')]
    assert embedder.embed_query('alpha') == unit_vector('query: alpha')
    assert [c[0] for c in backend.calls] == [['passage: alpha'], ['query: alpha']]
    for inputs, kwargs in backend.tokenizer.calls:
        assert kwargs == dict(add_special_tokens=True, truncation=False, padding=False, return_length=True)
    for inputs, kwargs in backend.calls:
        assert kwargs['normalize_embeddings'] is True
        assert kwargs['precision'] == 'float32' and kwargs['device'] == 'cpu'
        assert kwargs['prompt'] == ''  # Disable implicit model prompts/double prefix.
    assert embedder.dimensions == 384


@pytest.mark.parametrize('method', ['documents', 'query'])
def test_overflow_stops_whole_call_before_encode_or_cache(adapter, method):
    embedder, backend = adapter
    prefix = 'passage: ' if method == 'documents' else 'query: '
    backend.tokenizer.lengths[prefix + 'too long'] = 513
    with pytest.raises(TokenOverflowError) as error:
        if method == 'documents':
            embedder.embed_documents(['valid', 'too long'])
        else:
            embedder.embed_query('too long')
    assert error.value.inputs[0]['token_length'] == 513
    assert not backend.calls and not list(embedder._cache_dir.rglob('*.json'))


def test_limit_exactly_512_is_accepted(adapter):
    embedder, backend = adapter
    backend.tokenizer.lengths['passage: limit'] = 512
    assert len(embedder.embed_documents(['limit'])) == 1


def test_cached_input_is_still_checked_for_overflow(adapter):
    embedder, backend = adapter
    embedder.embed_query('cached')
    backend.tokenizer.lengths['query: cached'] = 513
    with pytest.raises(TokenOverflowError):
        embedder.embed_query('cached')
    assert len(backend.calls) == 1


@pytest.mark.parametrize('texts', ['abc', None, [None], [''], ['  '], ['x\x00y'], [42]])
def test_invalid_input_rejected(adapter, texts):
    embedder, backend = adapter
    with pytest.raises(EmbeddingError):
        embedder.embed_documents(texts)
    assert not backend.calls


def test_empty_batch_has_no_side_effects(adapter):
    embedder, backend = adapter
    assert embedder.embed_documents([]) == []
    assert not backend.calls and not backend.tokenizer.calls


@pytest.mark.parametrize('vector', [
    [1.0] + [0.0] * 382,
    [1.0] + [0.0] * 384,
    [0.0] * 384,
    [2.0] + [0.0] * 383,
    [float('nan')] + [0.0] * 383,
    [float('inf')] + [0.0] * 383,
    [1e100] + [0.0] * 383,
    [True] + [0.0] * 383,
    ['1'] + [0.0] * 383,
])
def test_vector_validation(vector):
    with pytest.raises(EmbeddingError):
        validate_vector(vector)


def test_float32_rounding_and_norm():
    values = validate_vector([1 / math.sqrt(384)] * 384)
    assert abs(math.sqrt(sum(x*x for x in values)) - 1) < 1e-5
    assert values[0] != 1 / math.sqrt(384)


@pytest.mark.parametrize('output', [[], [[0.0] * 384], [[1.0] * 383]])
def test_encoder_bad_count_or_vectors_not_cached(adapter, output):
    embedder, backend = adapter
    backend.output = output
    with pytest.raises(EmbeddingError):
        embedder.embed_documents(['alpha'])
    assert not list(embedder._cache_dir.rglob('*.json'))


def test_input_order_dedup_mixed_hits_batches_and_detached_results(adapter):
    embedder, backend = adapter
    embedder.embed_documents(['cached'])
    texts = ['third', 'cached', 'first', 'third', 'second']
    result = embedder.embed_documents(texts)
    assert result == [unit_vector('passage: ' + text) for text in texts]
    assert [c[0] for c in backend.calls] == [['passage: cached'], ['passage: third', 'passage: first'], ['passage: second']]
    assert embedder.stats['encoded_inputs'] == 4 and embedder.stats['deduplicated_inputs'] == 1
    result[0][0] = 99
    assert result[3] == unit_vector('passage: third')
    assert embedder.embed_documents(['third'])[0] == unit_vector('passage: third')


def test_disk_cache_reload_and_profile_isolation(adapter):
    first, backend = adapter
    expected = first.embed_documents(['persisted'])
    second = MyEmbedder.__new__(MyEmbedder)
    second_backend = EncoderDouble()
    second._configure(second_backend, first.profile, first._cache_dir, 2)
    assert second.embed_documents(['persisted']) == expected
    assert not second_backend.calls and second.stats['cache_hits'] == 1
    changed = MyEmbedder.__new__(MyEmbedder)
    changed_backend = EncoderDouble()
    changed._configure(changed_backend, synthetic_profile('different'), first._cache_dir, 2)
    changed.embed_documents(['persisted'])
    assert changed_backend.calls and changed.profile_id != first.profile_id
    key = hashlib.sha256(b'passage: persisted').hexdigest()
    assert first._path(key).is_file() and changed._path(key).is_file()


@pytest.mark.parametrize('corruption', ['json', 'profile', 'input', 'checksum', 'zero-vector'])
def test_corrupt_cache_fails_closed_without_reencode_or_overwrite(adapter, corruption):
    embedder, backend = adapter
    embedder.embed_documents(['cached'])
    file = next(embedder._cache_dir.rglob('*.json'))
    record = json.loads(file.read_text())
    if corruption == 'json':
        raw = '{invalid'
    else:
        field = {'profile':'profile_id','input':'input_sha256','checksum':'vector_sha256'}.get(corruption)
        if field:
            record[field] = 'f' * 64
        else:
            record['vector'] = [0.0] * 384
            record['vector_sha256'] = hashlib.sha256(canonical_json(record['vector']).encode()).hexdigest()
        raw = canonical_json(record)
    file.write_text(raw)
    with pytest.raises(EmbeddingError):
        embedder.embed_documents(['cached'])
    assert file.read_text() == raw and len(backend.calls) == 1


def test_profile_identity_frozen_and_detached(adapter):
    embedder, backend = adapter
    assert embedder.profile_id == hashlib.sha256(embedder.profile.config_canonical.encode()).hexdigest()
    with pytest.raises(FrozenInstanceError):
        embedder.profile.config_canonical = '{}'
    detached = embedder.profile.config
    detached['query_prefix'] = 'changed'
    assert embedder.profile.config['query_prefix'] == 'query: '
    for key in ['revision', 'document_prefix', 'query_prefix', 'pooling', 'normalize_embeddings', 'tokenizer', 'library_versions']:
        changed = deepcopy(embedder.profile.config)
        if key == 'library_versions':
            changed[key]['unit-test-double'] = 'changed'
        elif key == 'tokenizer':
            changed[key]['class'] = 'OtherFastTokenizer'
        else:
            changed[key] = 'different'
        assert hashlib.sha256(canonical_json(changed).encode()).hexdigest() != embedder.profile_id
    stats = embedder.stats
    stats['token_lengths'].append(999)
    assert embedder.stats['token_lengths'] == []


def test_runtime_limit_drift_stops_encode(adapter):
    embedder, backend = adapter
    backend.max_seq_length = 128
    with pytest.raises(EmbeddingError):
        embedder.embed_query('test')
    assert not backend.calls


@pytest.mark.parametrize('model,revision', [('other/model', REVISION), (MODEL, 'main')])
def test_constructor_rejects_unapproved_model_before_loading(model, revision):
    with pytest.raises(EmbeddingError):
        MyEmbedder(model, revision=revision)


def test_snapshot_checksum_pinned_and_missing_or_modified_snapshot_rejected(tmp_path):
    assert ARTIFACTS['model.safetensors'] == '1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477'
    with pytest.raises(EmbeddingError, match='Missing local snapshot'):
        MyEmbedder(MODEL, snapshot_path=tmp_path)
    (tmp_path/'README.md').write_text('tampered')
    with pytest.raises(EmbeddingError, match='checksum mismatch'):
        MyEmbedder(MODEL, snapshot_path=tmp_path)
