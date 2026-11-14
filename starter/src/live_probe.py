"""One explicitly approved metadata probe; no default authority or credentials."""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import database_probe as probe, dev_authorization as auth, dev_bootstrap as boot
from . import lab_dev_runtime as lab
from .model_load_only import CODE_FILES
from .evaluation import digest
from .evaluation_runner import file_sha
from .schema import canonical_json, EmbeddingProfile, require_compatible

SCOPE='LAB_DATABASE_METADATA_PROBE_LIVE'
PROBE_CODE_FILES=CODE_FILES+('starter/src/database_probe.py','starter/src/live_probe.py','starter/src/corpus.py','starter/src/benchmark.py')
CONNECTION_SETTINGS=dict(connect_timeout=5,statement_timeout_seconds=10,readonly=True,
    isolation='repeatable read',autocommit=True,default_transaction_read_only=True,
    lock_timeout_ms=5000,idle_in_transaction_session_timeout_ms=15000)


@dataclass(frozen=True)
class CredentialChannel:
    """Explicit operator-reviewed binding, not authentication of arbitrary Python.

    The trusted operator supplies the reader; the executor never discovers one.
    No secret is fetched while checking this immutable channel label.
    """
    credential_channel_id: str
    reader: object

    def __post_init__(self):
        auth._identifier(self.credential_channel_id)
        if not callable(self.reader):raise auth.AuthorizationError('Credential reader required')

    def __call__(self):
        return self.reader()


def validate_probe_request(request,*,prepared,selected_role,credential_channel_id):
    """Explicit scope invariants, additional to exact fresh-request comparison."""
    try:
        for value in (selected_role,credential_channel_id):auth._identifier(value)
        database=dict(host='127.0.0.1',port=55433,dbname='day6_lab',cluster=boot.CLUSTER,
            postgresql='16.16',pgvector='0.8.7',migration_sha256=boot.MIGRATION_SHA256,
            catalog_sha256=boot.APPROVED_CATALOG,read_only=True)
        profile=EmbeddingProfile.from_config(request['profile'])
        baseline=prepared.baseline
        baseline.validate_approved_identity()
        snapshots=baseline.snapshots
        require_compatible(*snapshots)
        if (request['scope']!=SCOPE or request['purpose']!='DB_IDENTITY_PERMISSION_PROBE_ONLY'
                or request['execution_mode']!='LIVE_DATABASE_METADATA_PROBE'
                or request['single_execution'] is not True
                or request['selected_role']!=selected_role
                or request['credential_channel_id']!=credential_channel_id
                or any(type(request['database'].get(k)) is not type(v) or request['database'].get(k)!=v
                       for k,v in database.items())
                or canonical_json(request['connection'])!=canonical_json(CONNECTION_SETTINGS)
                or baseline.dataset_id!=boot.DATASET
                or profile.profile_id!=boot.STAGE4_PROFILE
                or request['profile_id']!=profile.profile_id
                or baseline.profile_id!=profile.profile_id
                or prepared.profile.config_canonical!=profile.config_canonical
                or request['snapshot_ids']!=list(boot.STAGE4_SNAPSHOTS)
                or tuple(s.snapshot_id for s in snapshots)!=boot.STAGE4_SNAPSHOTS
                or tuple(s.namespace.strategy for s in snapshots)!=('A','B')
                or any(s.namespace.dataset_id!=baseline.dataset_id or s.namespace.profile_id!=profile.profile_id
                       for s in snapshots)
                or tuple(s.expected_count for s in snapshots)!=(246,264)
                or any(s.actual_count!=s.expected_count or s.status!='complete' or s.selected_page_count!=40
                       for s in snapshots)
                or len(request['descriptor_hashes'])!=2
                or any(not isinstance(h,str) or not re.fullmatch('[0-9a-f]{64}',h)
                       for h in request['descriptor_hashes'])
                or request['descriptor_hashes']!=list(baseline.descriptor_hashes)
                or prepared.plan['descriptor_hashes']!=request['descriptor_hashes']
                or prepared.plan['database']!=request['database']):
            raise ValueError()
    except Exception:raise auth.AuthorizationError('Invalid live probe invariants') from None


def probe_request(*,root,prepared,run_id,executor_id,selected_role,credential_channel_id):
    root=Path(root).resolve()
    for value in (run_id,executor_id,selected_role,credential_channel_id):auth._identifier(value)
    output=boot.stage5_path(root,'data/local/stage5/lab_audit/'+run_id,category='lab_audit')
    if output.exists():raise FileExistsError('New audit destination required')
    prepared.baseline.validate_approved_identity()
    hashes={}
    for name in PROBE_CODE_FILES:
        path=root/name
        if not path.resolve().is_relative_to(root):raise auth.AuthorizationError('Code path escapes root')
        for part in (path,*path.parents):
            if part==root:break
            if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
                raise auth.AuthorizationError('Unsafe code path')
        hashes[name]=file_sha(path)
    return canonical_json(dict(scope=SCOPE,execution_mode='LIVE_DATABASE_METADATA_PROBE',
        purpose='DB_IDENTITY_PERMISSION_PROBE_ONLY',single_execution=True,
        run_id=run_id,executor_id=executor_id,audit_output=output.relative_to(root).as_posix(),
        selected_role=selected_role,credential_channel_id=credential_channel_id,
        database=prepared.plan['database'],profile_id=prepared.profile.profile_id,
        profile=prepared.profile.config,snapshot_ids=list(boot.STAGE4_SNAPSHOTS),
        descriptor_hashes=list(prepared.baseline.descriptor_hashes),
        manifest_sha256=boot.APPROVED_MANIFEST,freeze_sha256=boot.APPROVED_FREEZE,
        source_checksums=boot.APPROVED_SOURCES,code_hashes=hashes,code_sha256=digest(hashes),
        connection=dict(CONNECTION_SETTINGS),
        custody_policy='LOCAL_LAB_NO_ANTI_ROLLBACK_GUARANTEE'))


def _audit(audit,status,*,result=None):
    try:
        expected=audit.write(status,error_code=None if status in ('CONSUMED','PROBE_VERIFIED') else status,
            artifact_sha256=None if result is None else digest(result))
        path=boot.stage5_path(audit.root,audit.path/f'{audit.sequence:04}.json',category='lab_audit')
        raw=path.read_bytes();record=json.loads(raw)
        if (raw!=(canonical_json(record)+'\n').encode() or digest(record)!=expected
                or record['status']!=status or record['run_id']!=audit.request['run_id']
                or record['request_sha256']!=digest(audit.request)
                or record['artifact_sha256']!=(None if result is None else digest(result))):
            raise ValueError()
    except Exception:raise probe.ProbeBlocked('AUDIT_WRITE_FAILED; consumed; no retry') from None


def _connect(*,credential_provider,**parameters):
    # Operator supplies a reviewed protected callable; no env/DSN discovery.
    credential=credential_provider()
    if not isinstance(credential,str) or not credential:raise PermissionError('Credential unavailable')
    try:
        import psycopg
        return psycopg.connect(password=credential,**parameters)
    finally:credential=None


def execute(*,root,run_id,executor_id,selected_role,credential_provider,
            credential_channel_id,request_canonical,approval,authority):
    if (type(credential_provider) is not CredentialChannel
            or credential_provider.credential_channel_id!=credential_channel_id):
        raise auth.AuthorizationError('Approved credential channel binding required')
    # Reconstruct corpus/context independently, rather than trusting caller objects.
    prepared=boot.prepare_dev(root=root)
    actual=probe_request(root=root,prepared=prepared,run_id=run_id,executor_id=executor_id,
        selected_role=selected_role,credential_channel_id=credential_channel_id)
    if actual!=request_canonical:raise auth.AuthorizationError('Fresh probe request mismatch')
    request=json.loads(actual)
    validate_probe_request(request,prepared=prepared,selected_role=selected_role,
        credential_channel_id=credential_channel_id)
    decision=lab.verify_manual_decision(actual,approval,authority=authority,scope=SCOPE)
    auth.ConsumptionLedger(root=root).consume(actual,decision.grant)
    try:
        audit=lab._LabAudit(root=root,request=request,decision=decision);_audit(audit,'CONSUMED')
    except Exception:raise probe.ProbeBlocked('AUDIT_WRITE_FAILED; consumed; no retry') from None
    try:
        def connector(*,target,selected_role,readonly,connect_timeout,autocommit,options):
            if target!=probe.TARGET or readonly is not True:raise PermissionError('Target mismatch')
            return _connect(credential_provider=credential_provider,host=target['host'],port=target['port'],
                dbname=target['dbname'],user=selected_role,connect_timeout=connect_timeout,
                autocommit=autocommit,options=options)
        audit.stage='DATABASE_PROBE'
        result=probe._inspect(prepared,selected_role=selected_role,connection_factory=connector)
        if result.get('warnings'):raise PermissionError('Role warning requires separate review')
        result['scope']=SCOPE
        result=dict(result,run_id=run_id,request_sha256=digest(request))
        _audit(audit,'PROBE_VERIFIED',result=result)
        return result
    except Exception as error:
        if isinstance(error,probe.ProbeBlocked) and str(error).startswith('AUDIT_WRITE_FAILED'):raise
        _audit(audit,'PROBE_FAILED')
        raise probe.ProbeBlocked('PROBE_FAILED; consumed; no retry') from None
