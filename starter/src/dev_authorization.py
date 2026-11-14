"""Offline-only dev authorization and mock wiring. No production execution entry point.

Authority selection is a trusted dependency, never request metadata. This module
ships no signing key, production authority, model constructor or DB connector.
"""
from copy import deepcopy
from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Protocol
from unittest.mock import Mock

from . import dev_bootstrap as boot
from .evaluation import digest
from .evaluation_runner import DEFAULT_CONFIG, file_sha
from .schema import canonical_json


class AuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class VerifiedGrant:
    approval_id: str
    authority_id: str
    request_sha256: str
    not_before: float
    expires_at: float


class SyntheticAuthority(Protocol):
    """Explicit trusted injection; tests implement authentication, not this module."""
    authority_id: str
    scope: str  # must be SYNTHETIC_ONLY

    def verify(self, request_canonical: str, approval: object) -> VerifiedGrant:
        ...


def _identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}',value):
        raise AuthorizationError('Invalid authorization/run identifier')
    return value


def authorization_request(prepared, *, root, run_id, output):
    """Build canonical identities from a fresh prepare_dev result, not approval flags."""
    root=Path(root).resolve();p=deepcopy(prepared.plan)
    _identifier(run_id)
    destination=boot.stage5_path(root,output,category='runs')
    if destination.exists():
        raise FileExistsError('Output already exists')
    if (p['split']!='dev' or p['config']!=DEFAULT_CONFIG or p['question_count']!=15
            or p['retrieval_calls']!=45 or len(set(p['question_ids']))!=15
            or p['freeze_sha256']!=boot.APPROVED_FREEZE
            or p['output']!=destination.relative_to(root).as_posix()
            or prepared.bundle['split']!='dev'
            or [q['id'] for q in prepared.bundle['questions']]!=p['question_ids']
            or prepared.profile.profile_id!=p['profile_id']):
        raise AuthorizationError('Unapproved dev preparation')
    execution='starter/src/dev_authorization.py'
    path=(root/execution).resolve()
    if not path.is_relative_to(root):
        raise AuthorizationError('Execution code escapes workspace')
    request=dict(authorization_version=1,scope='SYNTHETIC_ONLY',split='dev',single_execution=True,
        run_id=run_id,output=p['output'],plan_sha256=p['plan_sha256'],question_ids=p['question_ids'],
        question_count=15,retrieval_calls=45,freeze_sha256=p['freeze_sha256'],
        benchmark_manifest_sha256=p['benchmark_manifest_sha256'],frozen_files=p['frozen_files'],
        manifest_sha256=p['manifest_sha256'],source_checksums=p['source_checksums'],
        code=p['code'],bootstrap_source_hashes=p['bootstrap_source_hashes'],
        execution_source_hashes={execution:file_sha(path)},model=p['model'],database=p['database'],
        profile_id=p['profile_id'],snapshot_ids=p['snapshot_ids'],descriptor_hashes=p['descriptor_hashes'],
        configuration=p['config'],configuration_sha256=p['configuration_sha256'])
    return canonical_json(request)


def verify_authorization(request_canonical, approval, *, authority, now=None):
    """No default authority; a self-declared approved=True never authorizes anything."""
    if authority is None or getattr(authority,'scope',None)!='SYNTHETIC_ONLY' or approval is None:
        raise AuthorizationError('Independent synthetic authority and authenticated approval required')
    import json
    request=json.loads(request_canonical)
    if canonical_json(request)!=request_canonical or request.get('split')!='dev' or request.get('scope')!='SYNTHETIC_ONLY':
        raise AuthorizationError('Only canonical synthetic dev requests are accepted')
    try:
        grant=authority.verify(request_canonical,deepcopy(approval))
    except Exception:
        raise AuthorizationError('Authority rejected approval') from None
    current=time.time() if now is None else now
    if (type(grant) is not VerifiedGrant or grant.authority_id!=authority.authority_id
            or grant.request_sha256!=digest(request)
            or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)
                   for v in (current,grant.not_before,grant.expires_at))
            or not grant.not_before<=current<grant.expires_at):
        raise AuthorizationError('Approval identity or validity mismatch')
    _identifier(grant.approval_id);_identifier(grant.authority_id)
    return grant


class ConsumptionLedger:
    """Durable SQLite unique claims, committed before any runtime factory call.

    Lock contention fails closed. Existing claims are never reset or deleted.
    The local ledger directory must remain under exclusive operator control.
    """
    def __init__(self, *, root, path='data/local/stage5/authorization/consumption.sqlite3'):
        self.root=Path(root).resolve();self.path=Path(path)

    def require_consumed(self,request_canonical):
        """Read-only ordering assertion, not independent authorization or a lease."""
        import json
        request=json.loads(request_canonical)
        path=boot.stage5_path(self.root,self.path,category='authorization')
        if not path.is_file():raise AuthorizationError('No durable consumption claim')
        connection=None
        try:
            connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=0)
            rows=connection.execute('SELECT authority,approval_id FROM consumed WHERE run_id=? AND request_sha256=?',
                                    (_identifier(request['run_id']),digest(request))).fetchall()
            if len(rows)!=1:raise AuthorizationError('No exact durable consumption claim')
            _identifier(rows[0][0]);_identifier(rows[0][1])
        except sqlite3.Error:
            raise AuthorizationError('Consumption cannot be confirmed; no initialization') from None
        finally:
            if connection is not None:connection.close()

    def consume(self, request_canonical, grant):
        import json
        request=json.loads(request_canonical)
        if type(grant) is not VerifiedGrant or grant.request_sha256!=digest(request):
            raise AuthorizationError('Consumption identity mismatch')
        path=boot.stage5_path(self.root,self.path,category='authorization')
        path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
        path=boot.stage5_path(self.root,self.path,category='authorization')
        for candidate in (path,Path(str(path)+'-journal'),Path(str(path)+'-wal'),Path(str(path)+'-shm')):
            boot.stage5_path(self.root,candidate,category='authorization')
        try:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
        except FileExistsError:
            if not path.is_file() or path.is_symlink():
                raise AuthorizationError('Unsafe ledger file')
        else:
            os.fsync(fd);os.close(fd)
            if os.name=='posix':
                parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(parent)
                finally:os.close(parent)
        connection=None
        try:
            connection=sqlite3.connect(path,timeout=0,isolation_level=None)
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('PRAGMA journal_mode=DELETE')
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('CREATE TABLE IF NOT EXISTS consumed ('
                'authority TEXT NOT NULL, approval_id TEXT NOT NULL, run_id TEXT NOT NULL UNIQUE, '
                'request_sha256 TEXT NOT NULL UNIQUE, consumed_at REAL NOT NULL, '
                'PRIMARY KEY(authority,approval_id))')
            connection.execute('INSERT INTO consumed VALUES (?,?,?,?,?)',
                (grant.authority_id,grant.approval_id,_identifier(request['run_id']),grant.request_sha256,time.time()))
            connection.execute('COMMIT')
        except sqlite3.Error:
            raise AuthorizationError('Approval consumed, ledger busy or ledger unavailable; no retry') from None
        finally:
            if connection is not None:connection.close()


def verify_model_artifacts(*, root, model):
    """Filesystem/hash checks only, no tokenizer/model import or cache writes."""
    root=Path(root).resolve()
    snapshot=root/model['snapshot']
    base=root/'data/local/models'
    if '..' in Path(model['snapshot']).parts or not snapshot.resolve().is_relative_to(base.resolve()):
        raise AuthorizationError('Model snapshot escapes approved local path')
    for name,expected in model['profile']['artifact_sha256'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise AuthorizationError('Unsafe model artifact path')
        candidate=snapshot/relative
        for part in (candidate,*candidate.parents):
            if part==root:break
            if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
                raise AuthorizationError('Symlink/junction model artifact forbidden')
        if not candidate.is_file() or file_sha(candidate)!=expected:
            raise AuthorizationError('Model artifact checksum mismatch')


@dataclass(frozen=True)
class OfflineWiring:
    """Mocks required: cannot accidentally pass MyEmbedder, psycopg or live runner."""
    prepare: Mock
    model_factory: Mock
    producer_factory: Mock
    database_probe: Mock
    store_factory: Mock
    runner: Mock
    save: Mock
    verify: Mock

    def validate(self):
        if any(not isinstance(value,Mock) for value in self.__dict__.values()):
            raise AuthorizationError('Offline checkpoint requires mock dependencies only')


def simulate_authorized_dev(*, root, run_id, output, request_canonical, approval, authority,
                            wiring, split='dev', now=None):
    """Synthetic integration seam only; not a production authorization gateway.

    The existing runner alone owns query preparation and retrieval_session.
    Arbitrary injected Python remains trusted test code, not a security sandbox.
    """
    if split!='dev':raise AuthorizationError('TEST_EXECUTION_BLOCKED')
    wiring.validate()
    root=Path(root).resolve()
    prepared=wiring.prepare(split='dev',root=root,output=output)
    actual=authorization_request(prepared,root=root,run_id=run_id,output=output)
    if actual!=request_canonical:
        raise AuthorizationError('Request differs from fresh local preparation')
    grant=verify_authorization(actual,approval,authority=authority,now=now)
    ConsumptionLedger(root=root).consume(actual,grant)
    return _run_prepared_offline(root=root,run_id=run_id,output=output,prepared=prepared,
                                 wiring=wiring,scope='SYNTHETIC_ONLY')


def _run_prepared_offline(*, root, run_id, output, prepared, wiring, scope, stage=lambda name:None):
    """Shared mock-only wiring after a claim. Runner alone owns retrieval logic."""
    wiring.validate()
    # All exceptions below burn the authorization. No reset, fallback or retry.
    plan=prepared.plan
    stage('MODEL_ARTIFACTS')
    verify_model_artifacts(root=root,model=plan['model'])
    stage('MODEL_FACTORY')
    adapter=wiring.model_factory(plan['model']['model_name'],revision=plan['model']['revision'],
        snapshot_path=root/plan['model']['snapshot'],cache_dir=root/plan['model']['cache'])
    stage('MODEL_PROFILE')
    if (adapter.profile_id!=prepared.profile.profile_id
            or adapter.profile.config_canonical!=prepared.profile.config_canonical
            or Path(adapter._cache_dir).resolve()!=(root/plan['model']['cache']).resolve()):
        raise AuthorizationError('Runtime model/profile/cache mismatch')
    stage('QUERY_PRODUCER')
    producer=wiring.producer_factory(adapter,prepared.profile,cache_root=root/plan['model']['cache'])
    if producer.profile.config_canonical!=prepared.profile.config_canonical:
        raise AuthorizationError('Producer profile mismatch')
    expected=plan['database']
    stage('DATABASE_PROBE')
    backend=wiring.database_probe(dict(host=expected['host'],port=expected['port'],dbname=expected['dbname']))
    checks=dict(database=expected['dbname'],cluster=expected['cluster'],postgresql=expected['postgresql'],
        pgvector=expected['pgvector'],migration_sha256=expected['migration_sha256'],
        catalog_sha256=expected['catalog_sha256'],transaction_read_only=True,
        role='SELECT_ONLY_TABLE_GRANTS',role_review_required=False)
    if (not isinstance(backend,dict) or not set(backend)<=set(checks)|{'scope'}
            or any(type(backend.get(k)) is not type(v) or backend.get(k)!=v for k,v in checks.items())):
        raise AuthorizationError('Database identity/role mismatch')
    # Factory owns private DSN handling; it must not return/export the DSN.
    stage('STORE_FACTORY')
    store=wiring.store_factory(dimensions=384,dataset_id=prepared.baseline.dataset_id,
        profile_id=prepared.profile.profile_id,profile=prepared.profile,context=prepared.context)
    if store.dataset_id!=prepared.baseline.dataset_id or store.profile_id!=prepared.profile.profile_id:
        raise AuthorizationError('Store namespace mismatch')
    stage('EVALUATION_RUNNER')
    result=wiring.runner(prepared.bundle,store=store,producer=producer,baseline=prepared.baseline,
        config=deepcopy(DEFAULT_CONFIG),identity=plan['code'],backend_identity=backend,output_directory=None)
    if result.get('status') not in ('COMPLETE','INCOMPLETE'):
        raise AuthorizationError('Invalid runner outcome')
    if result['status']=='INCOMPLETE' and result.get('summary') is not None:
        raise AuthorizationError('Incomplete result cannot publish quality summary')
    # Runner has no run_id parameter. Bind outer run identity before artifact hashing.
    result=deepcopy(result);result['manifest']['run_id']=run_id
    stage('ARTIFACT_SAVE')
    artifact=wiring.save(result,root/output,root=root)
    stage('ARTIFACT_VERIFY')
    verified=wiring.verify(root/output,root=root)
    if verified!=artifact:
        raise AuthorizationError('Artifact verification mismatch')
    return dict(status=result['status'],run_id=run_id,artifact=verified,scope=scope)
