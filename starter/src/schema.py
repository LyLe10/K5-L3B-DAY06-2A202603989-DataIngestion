"""Offline schema contracts and migration planning. Never connects or executes SQL."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

SCHEMA = 'day6_ingestion'
MIGRATION_LOCK_KEY = 6753728366513601
MIGRATIONS = Path(__file__).resolve().parents[1] / 'migrations'
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
DATASET = re.compile(r'[a-z0-9][a-z0-9_.-]{0,127}\Z')


class SchemaError(ValueError):
    """Fail closed on unknown schema/history/configuration; never repair it."""


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise SchemaError('Configuration must be finite JSON') from exc


def _hash(value: str, name: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise SchemaError(f'{name} must be lowercase SHA-256')
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise SchemaError(f'{name} must be nonempty text without NUL')
    return value


@dataclass(frozen=True)
class EmbeddingProfile:
    """Content-addressed config; access returns a new dict, not mutable state."""
    config_canonical: str

    def __post_init__(self):
        try:
            config = json.loads(self.config_canonical)
        except (ValueError, TypeError) as exc:
            raise SchemaError('Invalid profile JSON') from exc
        if not isinstance(config, dict) or canonical_json(config) != self.config_canonical:
            raise SchemaError('Profile must use canonical JSON')
        required = {'profile_schema_version', 'model_name', 'revision', 'dimensions',
                    'dtype', 'pooling', 'normalize_embeddings', 'document_prefix',
                    'query_prefix', 'tokenizer', 'max_seq_length', 'artifact_sha256',
                    'library_versions', 'device', 'backend', 'trust_remote_code',
                    'pooling_include_prompt'}
        if set(config) != required:
            raise SchemaError('Missing or unknown profile keys')
        for key, expected in {'profile_schema_version': 1, 'dimensions': 384,
                              'dtype': 'float32', 'pooling': 'mean',
                              'normalize_embeddings': True, 'document_prefix': 'passage: ',
                              'query_prefix': 'query: ', 'max_seq_length': 512,
                              'device': 'cpu', 'backend': 'torch', 'trust_remote_code': False,
                              'pooling_include_prompt': True}.items():
            if type(config[key]) is not type(expected) or config[key] != expected:
                raise SchemaError(f'Unsupported {key}')
        _text(config['model_name'], 'model_name')
        if not isinstance(config['revision'], str) or not HEX40.fullmatch(config['revision']):
            raise SchemaError('Model revision must be a complete lowercase commit SHA')
        tokenizer = config['tokenizer']
        keys = {'name', 'revision', 'class', 'use_fast', 'model_max_length'}
        if not isinstance(tokenizer, dict) or set(tokenizer) != keys:
            raise SchemaError('Invalid tokenizer config')
        for key in ['name', 'class']:
            _text(tokenizer[key], 'tokenizer.' + key)
        if (tokenizer['name'] != config['model_name'] or tokenizer['revision'] != config['revision'] or tokenizer['use_fast'] is not True
                or type(tokenizer['model_max_length']) is not int or tokenizer['model_max_length'] != 512):
            raise SchemaError('Tokenizer revision/limit must match the approved profile')
        for field in ['artifact_sha256', 'library_versions']:
            entries = config[field]
            if not isinstance(entries, dict) or not entries:
                raise SchemaError(f'{field} must be a nonempty object')
            for key, value in entries.items():
                _text(key, field + ' key')
                if field == 'artifact_sha256':
                    _hash(value, key)
                else:
                    _text(value, key)

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> 'EmbeddingProfile':
        return cls(canonical_json(dict(config)))

    @property
    def config(self) -> dict:
        return json.loads(self.config_canonical)

    @property
    def profile_id(self) -> str:
        return hashlib.sha256(self.config_canonical.encode('utf-8')).hexdigest()

    def assert_same(self, other: 'EmbeddingProfile') -> None:
        if self.config_canonical != other.config_canonical:
            raise SchemaError('Immutable profile conflict; create a new profile')


@dataclass(frozen=True)
class Namespace:
    dataset_id: str
    profile_id: str
    strategy: str

    def __post_init__(self):
        if not isinstance(self.dataset_id, str) or not DATASET.fullmatch(self.dataset_id):
            raise SchemaError('Invalid dataset namespace')
        _hash(self.profile_id, 'profile_id')
        if self.strategy not in ('A', 'B'):
            raise SchemaError('Only A/B are stored; retrieval must map C to B')

    @property
    def lock_key(self) -> int:
        payload = f'{SCHEMA}:sync:{self.dataset_id}:{self.profile_id}:{self.strategy}'
        return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], 'big', signed=True)

    @property
    def parameters(self) -> tuple[str, str, str]:
        return self.dataset_id, self.profile_id, self.strategy


def retrieval_namespace(dataset_id: str, profile_id: str, strategy: str) -> Namespace:
    if strategy not in ('A', 'B', 'C'):
        raise SchemaError('Unknown retrieval strategy')
    return Namespace(dataset_id, profile_id, 'B' if strategy == 'C' else strategy)


def section_filter(filters: dict | None) -> tuple[str | None]:
    """One bind value only. Caller uses a fixed SQL section predicate, never keys."""
    if filters is None or filters == {}:
        return (None,)
    if not isinstance(filters, dict) or set(filters) != {'section'}:
        raise SchemaError('Only section equality filtering is supported')
    return (_text(filters['section'], 'section filter'),)


@dataclass(frozen=True)
class Snapshot:
    namespace: Namespace
    manifest_sha256: str
    corpus_sha256: str
    chunkset_sha256: str
    selected_page_count: int
    expected_count: int
    actual_count: int
    status: str

    def __post_init__(self):
        if not isinstance(self.namespace, Namespace):
            raise SchemaError('Invalid snapshot namespace')
        for name in ['manifest_sha256', 'corpus_sha256', 'chunkset_sha256']:
            _hash(getattr(self, name), name)
        if any(type(getattr(self, name)) is not int for name in
               ['selected_page_count', 'expected_count', 'actual_count']):
            raise SchemaError('Snapshot counts must be integers')
        if (self.selected_page_count < 30 or self.expected_count < self.selected_page_count
                or not 0 <= self.actual_count <= self.expected_count
                or self.status not in ('syncing', 'complete')):
            raise SchemaError('Invalid snapshot counts/status')
        if self.status == 'complete' and self.actual_count != self.expected_count:
            raise SchemaError('Incomplete committed snapshot')

    @property
    def snapshot_id(self) -> str:
        # Mutable completion counters/time are deliberately outside content identity.
        content = dict(namespace=self.namespace.parameters, manifest_sha256=self.manifest_sha256,
                       corpus_sha256=self.corpus_sha256, chunkset_sha256=self.chunkset_sha256,
                       selected_page_count=self.selected_page_count, expected_count=self.expected_count)
        return hashlib.sha256(canonical_json(content).encode()).hexdigest()


def require_compatible(a: Snapshot, b: Snapshot) -> None:
    if a.namespace.strategy != 'A' or b.namespace.strategy != 'B':
        raise SchemaError('Comparison requires an A snapshot and a B snapshot')
    if (a.namespace.parameters[:2] != b.namespace.parameters[:2]
            or a.status != 'complete' or b.status != 'complete'
            or a.manifest_sha256 != b.manifest_sha256
            or a.corpus_sha256 != b.corpus_sha256
            or a.selected_page_count != b.selected_page_count):
        raise SchemaError('Incompatible A/B snapshots; comparison is blocked')


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    checksum: str
    sql: str


def load_migrations(directory: Path = MIGRATIONS) -> tuple[Migration, ...]:
    """SHA is over exact UTF-8 LF bytes; never silently repair newline/checksum."""
    directory = directory.resolve()
    try:
        registry = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise SchemaError('Cannot read migration manifest') from exc
    if (not isinstance(registry, dict) or set(registry) != {'schema_version', 'migrations'}
            or type(registry['schema_version']) is not int or registry['schema_version'] != 1
            or not isinstance(registry['migrations'], list) or not registry['migrations']):
        raise SchemaError('Invalid migration manifest')
    migrations = []
    for number, entry in enumerate(registry['migrations'], 1):
        if (not isinstance(entry, dict) or set(entry) != {'version', 'name', 'sha256'}
                or type(entry['version']) is not int or entry['version'] != number
                or not isinstance(entry['name'], str)
                or not re.fullmatch(rf'{number:04d}_[a-z0-9_]+\.sql', entry['name'])):
            raise SchemaError('Invalid, duplicate or noncontiguous migration version/name')
        _hash(entry['sha256'], 'migration checksum')
        path = directory / entry['name']
        if path.resolve().parent != directory:
            raise SchemaError('Migration must stay in its directory')
        try:
            data = path.read_bytes()
            sql = data.decode('utf-8')
        except (OSError, UnicodeError) as exc:
            raise SchemaError('Cannot read UTF-8 migration') from exc
        if b'\r' in data or data.startswith(b'\xef\xbb\xbf'):
            raise SchemaError('Migration must use UTF-8 LF without BOM')
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise SchemaError('Migration checksum mismatch; do not rewrite history')
        migrations.append(Migration(number, entry['name'], entry['sha256'], sql))
    if {p.name for p in directory.glob('*.sql')} != {m.name for m in migrations}:
        raise SchemaError('Unregistered SQL file')
    return tuple(migrations)


def plan_migrations(migrations: Sequence[Migration], *, schema_exists: bool,
                    applied: Sequence[tuple[int, str, str]] = (),
                    catalog_matches: bool = False) -> tuple[Migration, ...]:
    """Pure decision, not a runner. Existing schemas always need catalog evidence."""
    if type(schema_exists) is not bool or type(catalog_matches) is not bool:
        raise SchemaError('Schema/catalog flags must be boolean')
    if not schema_exists and applied:
        raise SchemaError('History cannot exist without schema')
    if schema_exists and (not applied or not catalog_matches):
        raise SchemaError('Existing schema needs explicit history/catalog review')
    for index, row in enumerate(applied):
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise SchemaError('Malformed migration history row')
        if index >= len(migrations):
            raise SchemaError('Unknown database migration version')
        m = migrations[index]
        if tuple(row) != (m.version, m.name, m.checksum):
            raise SchemaError('Database migration history/checksum conflict')
    return tuple(migrations[len(applied):])
