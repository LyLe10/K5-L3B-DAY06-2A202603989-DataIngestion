"""Lab-controlled dev preparation: mock-only simulation, no live execution/issuance.

Manual authority selection/custody is outside the executor. This is not a
production anti-rollback boundary and does not authorize any real benchmark run.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Protocol

from . import dev_authorization as auth, dev_bootstrap as boot
from .evaluation import digest
from .evaluation_runner import DEFAULT_CONFIG, file_sha
from .schema import EmbeddingProfile, canonical_json

LAB_SCOPE='LAB_CONTROLLED_DEV'
REQUEST_KEYS=frozenset(('authorization_version scope split single_execution run_id output plan_sha256 '
    'question_ids question_count retrieval_calls freeze_sha256 benchmark_manifest_sha256 frozen_files '
    'manifest_sha256 source_checksums code bootstrap_source_hashes execution_source_hashes model database '
    'profile_id snapshot_ids descriptor_hashes configuration configuration_sha256 executor_id custody_policy').split())


@dataclass(frozen=True)
class LabDecision:
    """Authenticated human decision returned by the independently selected verifier."""
    grant: auth.VerifiedGrant
    reviewer_id: str
    executor_id: str
    decision_id: str


class ManualApprovalVerifier(Protocol):
    authority_id: str
    scope: str

    def verify(self, request_canonical: str, approval: object) -> LabDecision:
        """Authenticate an external manual decision; never issue approval here."""
        ...


def lab_authorization_request(prepared, *, root, run_id, output, executor_id):
    auth._identifier(executor_id)
    request=json.loads(auth.authorization_request(prepared,root=root,run_id=run_id,output=output))
    root=Path(root).resolve();name='starter/src/lab_dev_runtime.py';path=root/name
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise auth.AuthorizationError('Lab execution code escapes workspace')
    request.update(authorization_version=2,scope=LAB_SCOPE,executor_id=executor_id,
                   custody_policy='LOCAL_LAB_NO_ANTI_ROLLBACK_GUARANTEE')
    request['execution_source_hashes'][name]=file_sha(path)
    return canonical_json(request)


def validate_lab_request(request_canonical):
    """Existing canonical lab invariants, without authenticating an approval."""
    try:
        request=json.loads(request_canonical)
        profile=EmbeddingProfile.from_config(request['model']['profile'])
        valid=(set(request)==REQUEST_KEYS and canonical_json(request)==request_canonical
            and type(request['authorization_version']) is int and request['authorization_version']==2
            and request['scope']==LAB_SCOPE and request['split']=='dev' and request['single_execution'] is True
            and type(request['question_count']) is int and request['question_count']==15
            and type(request['retrieval_calls']) is int and request['retrieval_calls']==45
            and len(request['question_ids'])==len(set(request['question_ids']))==15
            and all(isinstance(q,str) and q for q in request['question_ids'])
            and request['freeze_sha256']==boot.APPROVED_FREEZE
            and request['manifest_sha256']==boot.APPROVED_MANIFEST
            and request['source_checksums']==boot.APPROVED_SOURCES
            and request['profile_id']==profile.profile_id==boot.STAGE4_PROFILE
            and request['model']['revision']==profile.config['revision']==boot.REVISION
            and request['model']['model_name']==profile.config['model_name']==boot.MODEL
            and request['snapshot_ids']==list(boot.STAGE4_SNAPSHOTS)
            and canonical_json(request['configuration'])==canonical_json(DEFAULT_CONFIG)
            and request['configuration_sha256']==digest(DEFAULT_CONFIG)
            and request['database']['host']=='127.0.0.1'
            and type(request['database']['port']) is int and request['database']['port']==55433
            and request['database']['dbname']=='day6_lab' and request['database']['cluster']==boot.CLUSTER
            and request['database']['postgresql']=='16.16' and request['database']['pgvector']=='0.8.7'
            and request['database']['migration_sha256']==boot.MIGRATION_SHA256
            and request['database']['catalog_sha256']==boot.APPROVED_CATALOG
            and request['database']['read_only'] is True
            and request['custody_policy']=='LOCAL_LAB_NO_ANTI_ROLLBACK_GUARANTEE')
        auth._identifier(request['executor_id']);auth._identifier(request['run_id'])
    except Exception:
        raise auth.AuthorizationError('Invalid canonical lab request') from None
    if not valid:
        raise auth.AuthorizationError('Invalid canonical lab request')
    return request


def verify_lab_approval(request_canonical, approval, *, authority):
    """No issuer, default authority, flags, environment shortcuts or clock override."""
    validate_lab_request(request_canonical)
    return verify_manual_decision(request_canonical,approval,authority=authority,scope=LAB_SCOPE)


def verify_manual_decision(request_canonical, approval, *, authority, scope):
    """Shared external human-decision verification; no issuance or clock override.

    Scope-specific request validation belongs to the caller before this helper.
    """
    request=json.loads(request_canonical)
    if (canonical_json(request)!=request_canonical or request.get('scope')!=scope
            or authority is None or getattr(authority,'scope',None)!=scope or approval is None):
        raise auth.AuthorizationError('Independent lab manual approval required')
    try:
        decision=authority.verify(request_canonical,deepcopy(approval))
        if type(decision) is not LabDecision or type(decision.grant) is not auth.VerifiedGrant:
            raise ValueError()
        grant=decision.grant;current=time.time()
        for value in (decision.reviewer_id,decision.executor_id,decision.decision_id,grant.approval_id,grant.authority_id):
            auth._identifier(value)
        valid=(grant.authority_id==authority.authority_id and grant.request_sha256==digest(request)
            and decision.executor_id==request['executor_id'] and decision.reviewer_id!=decision.executor_id
            and all(type(v) in (float,int) and math.isfinite(v) for v in (current,grant.not_before,grant.expires_at))
            and grant.not_before<=current<grant.expires_at)
    except Exception:
        raise auth.AuthorizationError('Manual approval verification failed') from None
    if not valid:raise auth.AuthorizationError('Manual approval identity or expiry mismatch')
    return decision


class ModelAdapterFactory(Protocol):
    def __call__(self, model_name: str, *, revision: str, snapshot_path: Path, cache_dir: Path) -> Any: ...


class QueryCacheFactory(Protocol):
    def __call__(self, *, root: Path, profile_id: str) -> Path: ...


class ReadOnlyConnectionFactory(Protocol):
    def __call__(self, *, target: dict, readonly: bool) -> Any: ...


class NamespaceStoreFactory(Protocol):
    def __call__(self, *, dimensions: int, dataset_id: str, profile_id: str,
                 profile: EmbeddingProfile, context: Any) -> Any: ...


class DisabledLabFactories:
    """Reviewable contracts only. No model import, DSN discovery or connection."""
    @staticmethod
    def model_adapter(model_name, *, revision, snapshot_path, cache_dir):
        raise PermissionError('LAB_LIVE_RUNTIME_DISABLED')

    @staticmethod
    def query_cache(*, root, profile_id):
        raise PermissionError('LAB_LIVE_RUNTIME_DISABLED')

    @staticmethod
    def readonly_connection(*, target, readonly):
        raise PermissionError('LAB_LIVE_RUNTIME_DISABLED')

    @staticmethod
    def database_probe(target):
        raise PermissionError('LAB_LIVE_RUNTIME_DISABLED')

    @staticmethod
    def namespace_store(*, dimensions, dataset_id, profile_id, profile, context):
        raise PermissionError('LAB_LIVE_RUNTIME_DISABLED')


class LabAuditError(RuntimeError):
    pass


class _LabAudit:
    """Local audit, exclusive files and fsync. No exception message/credential payload."""
    def __init__(self, *, root, request, decision):
        self.root=Path(root).resolve();self.request=request;self.decision=decision;self.sequence=0
        self.path=boot.stage5_path(self.root,'data/local/stage5/lab_audit/'+request['run_id'],category='lab_audit')
        self.path.mkdir(parents=True,mode=0o700,exist_ok=False)
        self.stage='CONSUMPTION'

    def write(self, status, *, error_code=None, sqlstate=None, artifact_sha256=None):
        try:return self._write(status,error_code=error_code,sqlstate=sqlstate,artifact_sha256=artifact_sha256)
        except Exception:raise LabAuditError('CONSUMED_AUDIT_WRITE_FAILED_NO_RETRY') from None

    def _write(self, status, *, error_code=None, sqlstate=None, artifact_sha256=None):
        self.sequence+=1
        record=dict(audit_version=1,scope=self.request['scope'],run_id=self.request['run_id'],
            request_sha256=digest(self.request),approval_id=self.decision.grant.approval_id,
            authority_id=self.decision.grant.authority_id,decision_id=self.decision.decision_id,
            consumed=True,sequence=self.sequence,timestamp=time.time(),stage=self.stage,status=status,
            error_code=error_code,sqlstate=sqlstate,artifact_sha256=artifact_sha256)
        record.update(profile_id=self.request.get('profile_id'),
            execution_mode=self.request.get('execution_mode','OFFLINE_SYNTHETIC'),
            model_name=self.request.get('model',{}).get('model_name'),
            model_revision=self.request.get('model',{}).get('revision'),
            consumption_identity=digest(dict(authority_id=self.decision.grant.authority_id,
                approval_id=self.decision.grant.approval_id,run_id=self.request['run_id'],
                request_sha256=self.decision.grant.request_sha256)))
        path=boot.stage5_path(self.root,self.path/f'{self.sequence:04}.json',category='lab_audit')
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write((canonical_json(record)+'\n').encode());stream.flush();os.fsync(stream.fileno())
        if os.name=='posix':
            parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(parent)
            finally:os.close(parent)
        return digest(record)

    def write_verified(self,status,**kwargs):
        """Opt-in read-back for live owners; existing write behavior is unchanged."""
        try:
            expected=self.write(status,**kwargs)
            path=boot.stage5_path(self.root,self.path/f'{self.sequence:04}.json',category='lab_audit')
            raw=path.read_bytes();record=json.loads(raw)
            if (raw!=(canonical_json(record)+'\n').encode() or digest(record)!=expected
                    or record['request_sha256']!=digest(self.request)
                    or record['run_id']!=self.request['run_id'] or record['status']!=status):
                raise ValueError()
        except Exception:raise LabAuditError('CONSUMED_AUDIT_VERIFICATION_FAILED_NO_RETRY') from None

    def begin(self, stage):
        self.stage=stage;self.write('STAGE_STARTED')


def simulate_lab_dev(*, root, run_id, output, executor_id, request_canonical, approval,
                     authority, wiring, split='dev'):
    """Offline seam only: authority is injected; runtime dependencies MUST be mocks."""
    if split!='dev':raise auth.AuthorizationError('TEST_EXECUTION_BLOCKED')
    wiring.validate()
    root=Path(root).resolve()
    prepared=wiring.prepare(split='dev',root=root,output=output)
    actual=lab_authorization_request(prepared,root=root,run_id=run_id,output=output,executor_id=executor_id)
    if actual!=request_canonical:raise auth.AuthorizationError('Lab request differs from fresh preparation')
    decision=verify_lab_approval(actual,approval,authority=authority)
    # The accepted local ledger is reused unchanged. An uncertain/error claim never reaches runtime.
    auth.ConsumptionLedger(root=root).consume(actual,decision.grant)
    try:
        audit=_LabAudit(root=root,request=json.loads(actual),decision=decision)
        audit.write('CONSUMED')
    except Exception:
        raise LabAuditError('CONSUMED_AUDIT_UNAVAILABLE_NO_RUNTIME_NO_RETRY') from None
    try:
        result=auth._run_prepared_offline(root=root,run_id=run_id,output=output,prepared=prepared,
            wiring=wiring,scope=LAB_SCOPE,stage=audit.begin)
        audit.write('COMPLETED_VERIFIED' if result['status']=='COMPLETE' else 'RUN_INCOMPLETE',
                    artifact_sha256=digest(result['artifact']))
        return result
    except Exception as error:
        if isinstance(error,LabAuditError):raise
        # Never turn exceptions into a fake benchmark result or leak str(error)/traceback.
        code=('DEADLINE_EXCEEDED' if isinstance(error,TimeoutError) else
              'AUTHORIZATION_OR_IDENTITY_REJECTED' if isinstance(error,auth.AuthorizationError) else 'OPERATION_FAILED')
        state=getattr(error,'sqlstate',None)
        state=state if isinstance(state,str) and re.fullmatch('[0-9A-Z]{5}',state) else None
        status={'ARTIFACT_SAVE':'ARTIFACT_WRITE_FAILED','ARTIFACT_VERIFY':'ARTIFACT_VERIFY_FAILED'}.get(
            audit.stage,'FAILED_NO_RESULT')
        try:audit.write(status,error_code=code,sqlstate=state)
        except Exception:raise LabAuditError('CONSUMED_FAILURE_AUDIT_UNAVAILABLE_NO_RETRY') from None
        raise LabAuditError('CONSUMED_RUN_FAILED_SEE_SANITIZED_AUDIT_NO_RETRY') from None
