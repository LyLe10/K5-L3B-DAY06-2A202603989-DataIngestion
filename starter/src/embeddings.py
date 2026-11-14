"""Pinned local E5 CPU adapter. No downloads, database access or mock fallback."""
from importlib.metadata import version
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import struct
import tempfile
from time import perf_counter
from typing import Protocol

from .schema import EmbeddingProfile, canonical_json

MODEL = 'intfloat/multilingual-e5-small'
REVISION = 'fd1525a9fd15316a2d503bf26ab031a61d056e98'
ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / 'data/local'
SNAPSHOT = LOCAL / 'models/intfloat--multilingual-e5-small' / REVISION
CACHE = LOCAL / 'stage4/embedding_cache'
NORM_TOLERANCE = 1e-5
# SHA-256 verified against the official snapshot during accepted Checkpoint 4.1.
ARTIFACTS = {
    'README.md': '0038de97aee16258cecbad7ffda4b4febd6953e747a00e0ddbc8e6ed241e9c1c',
    'config.json': '69137736cab8b8903a07fe8afaafdda25aac55415a12a55d1bffa9f581abf959',
    'modules.json': 'c6e29747481e8b5dd2b58401966aeac910de39092f90cda9a704b1545f902b04',
    'sentence_bert_config.json': '948201d8329907aae938fa62f9ceeed53f5694dacc2b87b9f3b78b37ee986529',
    '1_Pooling/config.json': '987f7a67a38fa564c849bb5d277c52ab9088a84368fc0be31a354125aebb12a0',
    'tokenizer_config.json': 'a1d6bc8734a6f635dc158508bef000f8e2e5a759c7d92f984b2c86e5ff53425b',
    'special_tokens_map.json': 'd05497f1da52c5e09554c0cd874037a083e1dc1b9cfd48034d1c717f1afc07a7',
    'sentencepiece.bpe.model': 'cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865',
    'tokenizer.json': '0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39',
    'model.safetensors': '1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477',
}
PINS = {'torch': '2.9.1+cpu', 'sentence-transformers': '5.1.2', 'transformers': '4.57.1',
        'tokenizers': '0.22.1', 'huggingface-hub': '0.36.0', 'sentencepiece': '0.2.1'}


class EmbeddingError(ValueError):
    """Invalid input, runtime, vector or cache; never silently repair or truncate."""


class TokenOverflowError(EmbeddingError):
    def __init__(self, inputs):
        self.inputs = inputs
        super().__init__(f'Input exceeds 512 tokens: {inputs}')


def validate_vector(values) -> list[float]:
    """Validate the float32 representation that will be cached/stored later."""
    if len(values) != 384:
        raise EmbeddingError('Embedding dimension must be 384')
    result = []
    for value in values:
        if isinstance(value, (bool, str, bytes)):
            raise EmbeddingError('Embedding values must be real numbers')
        try:
            number = float(value)
            if not math.isfinite(number):
                raise EmbeddingError('Nonfinite embedding value')
            number = struct.unpack('!f', struct.pack('!f', number))[0]
        except (TypeError, ValueError, OverflowError, struct.error) as exc:
            raise EmbeddingError('Invalid float32 embedding value') from exc
        if not math.isfinite(number):
            raise EmbeddingError('Nonfinite float32 embedding value')
        result.append(number)
    norm = math.sqrt(math.fsum(value * value for value in result))
    if norm == 0 or abs(norm - 1) > NORM_TOLERANCE:
        raise EmbeddingError(f'Embedding must have unit norm; got {norm}')
    return result


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Implements Embedder; public inputs are raw texts, never pre-prefixed batches."""

    def __init__(self, model_name: str, *, revision: str = REVISION,
                 snapshot_path: Path = SNAPSHOT, cache_dir: Path = CACHE,
                 batch_size: int = 16) -> None:
        if model_name != MODEL or revision != REVISION:
            raise EmbeddingError('Only the approved model and revision are allowed')
        if type(batch_size) is not int or not 1 <= batch_size <= 16:
            raise EmbeddingError('batch_size must be an integer from 1 to 16')
        snapshot = Path(snapshot_path).resolve()
        cache = Path(cache_dir).resolve()
        if not cache.is_relative_to(LOCAL.resolve()):
            raise EmbeddingError('Production vector cache must remain under data/local/')
        started = perf_counter()
        for name, expected in ARTIFACTS.items():
            file = snapshot / name
            if not file.is_file():
                raise EmbeddingError(f'Missing local snapshot artifact: {name}')
            with file.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != expected:
                raise EmbeddingError(f'Snapshot checksum mismatch: {name}')
        verified_seconds = perf_counter() - started
        libraries = {name: version(name) for name in [*PINS, 'numpy', 'safetensors']}
        if any(libraries[name] != expected for name, expected in PINS.items()):
            raise EmbeddingError('Dependency versions differ from approved preflight pins')
        libraries['python'] = platform.python_version()
        # Heavy packages are lazy imports: pure unit tests still run in baseline venv.
        import torch
        from sentence_transformers import SentenceTransformer, models
        started = perf_counter()
        model = SentenceTransformer(str(snapshot), device='cpu', local_files_only=True,
                                    trust_remote_code=False,
                                    model_kwargs={'use_safetensors': True, 'dtype': torch.float32},
                                    tokenizer_kwargs={'use_fast': True})
        model.eval()
        modules = list(model.children())
        if (model.get_sentence_embedding_dimension() != 384 or model.max_seq_length != 512
                or model.tokenizer.model_max_length != 512 or not model.tokenizer.is_fast
                or type(model.tokenizer).__name__ != 'XLMRobertaTokenizerFast'
                or model[0].auto_model.config.max_position_embeddings != 512
                or len(modules) != 3 or not isinstance(modules[1], models.Pooling)
                or not isinstance(modules[2], models.Normalize)
                or model.training or any(p.device.type != 'cpu' or p.dtype != torch.float32 for p in model.parameters())):
            raise EmbeddingError('Loaded model/tokenizer runtime differs from approved profile')
        pooling = modules[1].get_config_dict()
        if (not pooling['pooling_mode_mean_tokens'] or not pooling['include_prompt']
                or any(value for key, value in pooling.items()
                       if key.startswith('pooling_mode_') and key != 'pooling_mode_mean_tokens')):
            raise EmbeddingError('Expected mean pooling including the prefix tokens')
        profile = EmbeddingProfile.from_config(dict(
            profile_schema_version=1, model_name=MODEL, revision=REVISION, dimensions=384,
            dtype='float32', pooling='mean', normalize_embeddings=True,
            document_prefix='passage: ', query_prefix='query: ', max_seq_length=512,
            device='cpu', backend='torch', trust_remote_code=False, pooling_include_prompt=True,
            tokenizer=dict(name=MODEL, revision=REVISION, **{'class': type(model.tokenizer).__name__},
                           use_fast=True, model_max_length=512),
            artifact_sha256=dict(ARTIFACTS), library_versions=libraries))
        self._configure(model, profile, cache, batch_size)
        self.runtime = dict(load_seconds=perf_counter() - started,
                            artifact_verification_seconds=verified_seconds,
                            modules=[type(m).__name__ for m in modules], pooling=pooling,
                            device='cpu', dtype='float32', eval_mode=not model.training,
                            tokenizer_limit=512, sentence_transformers_limit=512)

    def _configure(self, model, profile, cache, batch_size):
        """Private component boundary for unit-test doubles; not a runtime fallback."""
        self._model, self._profile = model, profile
        self._cache_dir, self._batch_size = Path(cache), batch_size
        self._stats = dict(calls=0, inputs=0, cache_hits=0, deduplicated_inputs=0,
                           encoded_inputs=0, encode_batches=0, tokenization_seconds=0.0,
                           encode_seconds=0.0, token_lengths=[])

    @property
    def model_name(self):
        return self._profile.config['model_name']

    @property
    def dimensions(self):
        return 384

    @property
    def profile(self):
        return self._profile

    @property
    def profile_id(self):
        return self._profile.profile_id

    @property
    def stats(self):
        return json.loads(json.dumps(self._stats))

    def _path(self, key):
        return self._cache_dir / self.profile_id / (key + '.json')

    def _read_cache(self, key):
        path = self._path(key)
        if not path.exists():
            return None
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            if (set(record) != {'cache_version', 'profile_id', 'input_sha256', 'vector', 'vector_sha256'}
                    or type(record['cache_version']) is not int or record['cache_version'] != 1
                    or record['profile_id'] != self.profile_id or record['input_sha256'] != key
                    or record['vector_sha256'] != _digest(canonical_json(record['vector']))):
                raise EmbeddingError('Cache identity/checksum mismatch')
            vector = validate_vector(record['vector'])
            if vector != record['vector']:
                raise EmbeddingError('Cache vector is not float32')
            return vector
        except (OSError, TypeError, ValueError, KeyError) as exc:
            raise EmbeddingError(f'Invalid cache entry {key}; not overwritten') from exc

    def _write_cache(self, key, vector):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = dict(cache_version=1, profile_id=self.profile_id, input_sha256=key,
                      vector=vector, vector_sha256=_digest(canonical_json(vector)))
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             prefix='.pending-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(canonical_json(record) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # Atomic publication without overwriting an existing/protected entry.
                os.link(temporary, path)
            except FileExistsError:
                if self._read_cache(key) != vector:
                    raise EmbeddingError('Concurrent cache conflict; entry not overwritten')
        finally:
            if temporary is not None:
                temporary.unlink()

    def _embed(self, texts, prefix):
        if not isinstance(texts, list) or any(not isinstance(t, str) or not t.strip() or '\x00' in t for t in texts):
            raise EmbeddingError('Inputs must be a list of nonempty raw strings without NUL')
        if not texts:
            return []
        inputs = [prefix + text for text in texts]
        if self._model.max_seq_length != 512 or self._model.tokenizer.model_max_length != 512:
            raise EmbeddingError('Runtime token limits changed after profile creation')
        started = perf_counter()
        tokens = self._model.tokenizer(inputs, add_special_tokens=True, truncation=False,
                                       padding=False, return_length=True)
        lengths = [len(ids) for ids in tokens['input_ids']]
        if len(lengths) != len(inputs) or lengths != tokens['length']:
            raise EmbeddingError('Tokenizer batch length/order contract failed')
        overflow = [dict(index=i, token_length=n, input_sha256=_digest(inputs[i]))
                    for i, n in enumerate(lengths) if n > 512]
        if overflow:
            raise TokenOverflowError(overflow)
        self._stats['tokenization_seconds'] += perf_counter() - started
        self._stats['token_lengths'].extend(lengths)
        self._stats['calls'] += 1
        self._stats['inputs'] += len(inputs)
        vectors, pending = {}, {}
        for text in inputs:
            key = _digest(text)
            if key in vectors:
                self._stats['cache_hits'] += 1
            elif key in pending:
                self._stats['deduplicated_inputs'] += 1
            else:
                cached = self._read_cache(key)
                if cached is not None:
                    vectors[key] = cached
                    self._stats['cache_hits'] += 1
                else:
                    pending[key] = text
        keys = list(pending)
        for start in range(0, len(keys), self._batch_size):
            batch = keys[start:start + self._batch_size]
            started = perf_counter()
            output = self._model.encode([pending[k] for k in batch], batch_size=self._batch_size,
                                        show_progress_bar=False, convert_to_numpy=True,
                                        normalize_embeddings=True, precision='float32',
                                        device='cpu', prompt='')
            self._stats['encode_seconds'] += perf_counter() - started
            self._stats['encode_batches'] += 1
            if len(output) != len(batch):
                raise EmbeddingError('Encoder returned the wrong number of vectors')
            for key, vector in zip(batch, output, strict=True):
                vectors[key] = validate_vector(vector)
            self._stats['encoded_inputs'] += len(batch)
        # Never publish malformed vectors or a partial cache on validation failure.
        for key in keys:
            self._write_cache(key, vectors[key])
        return [vectors[_digest(text)].copy() for text in inputs]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, 'passage: ')

    def embed_query(self, question: str) -> list[float]:
        return self._embed([question], 'query: ')[0]
