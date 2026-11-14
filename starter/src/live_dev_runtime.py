"""Explicitly authorized DEV orchestration. Importing does not start runtime."""
from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path
import sys

from . import dev_bootstrap as boot, dev_authorization as auth, lab_dev_runtime as lab
from . import live_probe, database_probe
from .evaluation import digest
from .evaluation_runner import QueryProducer, run_evaluation, DEFAULT_CONFIG, file_sha
from .schema import canonical_json
from .store import PgVectorStore
from .pinned_model_factory import validate_snapshot_inventory

SCOPE='LAB_LIVE_DEV_EVALUATION'
CODE_FILES=tuple(dict.fromkeys(live_probe.PROBE_CODE_FILES+(
    'starter/src/live_dev_runtime.py','starter/src/chunking.py','starter/src/ingestion.py','starter/src/models.py')))
RETRIEVAL_SETTINGS=dict(lock_timeout_ms=5000,statement_timeout_ms=30000,
    idle_timeout_ms=60000,deadline_seconds=120)
_EXECUTING_ROOT=Path(__file__).resolve().parents[2]


def _loaded_module_origins():
    """Metadata only; never imports a missing module or a heavy runtime."""
    origins={}
    for name in CODE_FILES:
        if not name.startswith('starter/src/') or not name.endswith('.py'):continue
        module_name=name[:-3].replace('/','.')
        module=sys.modules.get(module_name)
        if module is None:continue
        spec=getattr(module,'__spec__',None)
        file=getattr(module,'__file__',None)
        origin=getattr(spec,'origin',None)
        if not file or not origin or Path(file).resolve()!=Path(origin).resolve():
            raise auth.AuthorizationError('Loaded module origin mismatch')
        origins[module_name]=str(Path(file).resolve())
    return origins


def _workspace_identity(root):
    root=Path(root).resolve()
    if root!=_EXECUTING_ROOT:raise auth.AuthorizationError('Root differs from executing workspace')
    origins=_loaded_module_origins()
    relative={}
    for module_name,origin in origins.items():
        expected=root/(module_name.replace('.','/')+'.py')
        if Path(origin)!=expected:raise auth.AuthorizationError('Module belongs to another workspace')
        relative[module_name]=expected.relative_to(root).as_posix()
    if __name__ not in relative:raise auth.AuthorizationError('Executing module origin missing')
    return dict(workspace_sha256=digest(root.as_posix()),module_origins=relative,
        interpreter_sha256=digest(str(Path(sys.executable).resolve())),
        environment_sha256=digest(str(Path(sys.prefix).resolve())),
        python_version=list(sys.version_info[:3]),implementation=sys.implementation.name,
        cache_tag=sys.implementation.cache_tag)


def _assert_runtime_identity(root,request):
    binding=request['runtime_binding']
    if _workspace_identity(root)!=binding['executing_identity']:
        raise auth.AuthorizationError('Executing workspace/module identity changed')
    for name,expected in binding['code_hashes'].items():
        path=root/name
        if not path.resolve().is_relative_to(root):raise auth.AuthorizationError('Code escapes root')
        for part in (path,*path.parents):
            if part==root:break
            if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
                raise auth.AuthorizationError('Unsafe runtime code path')
        if file_sha(path)!=expected:raise auth.AuthorizationError('Runtime source changed')


def _channel(provider,channel_id):
    if type(provider) is not live_probe.CredentialChannel or provider.credential_channel_id!=channel_id:
        raise auth.AuthorizationError('Explicit approved credential channel required')


def live_dev_request(*,root,prepared,run_id,output,executor_id,selected_role,credential_channel_id):
    """Metadata only. Regenerate this exact request immediately before consumption."""
    root=Path(root).resolve()
    executing_identity=_workspace_identity(root)
    base=json.loads(lab.lab_authorization_request(prepared,root=root,run_id=run_id,
        output=output,executor_id=executor_id))
    lab.validate_lab_request(canonical_json(base))
    # Reuse the explicit database/profile/snapshot/descriptor invariant gate.
    probe_request=json.loads(live_probe.probe_request(root=root,prepared=prepared,run_id=run_id,
        executor_id=executor_id,selected_role=selected_role,credential_channel_id=credential_channel_id))
    live_probe.validate_probe_request(probe_request,prepared=prepared,selected_role=selected_role,
        credential_channel_id=credential_channel_id)
    hashes={}
    for name in CODE_FILES:
        path=root/name
        if not path.resolve().is_relative_to(root):raise auth.AuthorizationError('Code escapes root')
        for part in (path,*path.parents):
            if part==root:break
            if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
                raise auth.AuthorizationError('Unsafe code identity')
        hashes[name]=file_sha(path)
    base.update(scope=SCOPE,authorization_version=3,execution_mode='LIVE_DEV_ONLY',
        runtime_binding=dict(selected_role=selected_role,credential_channel_id=credential_channel_id,
            connection=dict(live_probe.CONNECTION_SETTINGS),retrieval=dict(RETRIEVAL_SETTINGS),
            code_hashes=hashes,code_sha256=digest(hashes),executing_identity=executing_identity))
    return canonical_json(base)


def _initialize_model(prepared,root):
    # Heavy constructor is reachable only after durable consumption and verified audit.
    from .embeddings import MyEmbedder
    model=prepared.plan['model']
    return MyEmbedder(model['model_name'],revision=model['revision'],
        snapshot_path=root/model['snapshot'],cache_dir=root/model['cache'],batch_size=16)


def _verify_model(adapter,prepared,root):
    if (adapter.profile_id!=prepared.profile.profile_id
            or adapter.profile.config_canonical!=prepared.profile.config_canonical
            or Path(adapter._cache_dir).resolve()!=(root/prepared.plan['model']['cache']).resolve()
            or adapter.dimensions!=384
            or any(type(adapter.runtime.get(k)) is not type(v) or adapter.runtime.get(k)!=v
                   for k,v in dict(device='cpu',dtype='float32',eval_mode=True,
                       tokenizer_limit=512,sentence_transformers_limit=512).items())
            or any(type(adapter.stats.get(k)) is not int or adapter.stats.get(k)!=0
                   for k in ('calls','inputs','encoded_inputs','encode_batches'))
            or adapter.stats.get('token_lengths')!=[]):
        raise auth.AuthorizationError('Runtime model/profile/cache mismatch')


def _connector(channel,role,*,target,readonly,connect_timeout=5,autocommit=True,
               options='-c default_transaction_read_only=on',selected_role=None):
    if (target!=database_probe.TARGET or readonly is not True or connect_timeout!=5
            or autocommit is not True or options!='-c default_transaction_read_only=on'
            or selected_role not in (None,role)):
        raise auth.AuthorizationError('Unapproved connection request')
    return live_probe._connect(credential_provider=channel,host='127.0.0.1',port=55433,
        dbname='day6_lab',user=role,connect_timeout=5,autocommit=True,options=options)


def _verify_retrieval_connection(connection,role):
    """Run inside the existing read-only retrieval transaction, before searches."""
    try:
        if connection.info.transaction_status.name!='INTRANS':raise ValueError()
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(),current_setting('server_version_num'),"
                "(SELECT system_identifier::text FROM pg_catalog.pg_control_system()),"
                "(SELECT extversion FROM pg_extension WHERE extname='vector'),"
                "(SELECT checksum FROM day6_ingestion.schema_migrations WHERE version=1),"
                "day6_ingestion.catalog_fingerprint()")
            if cursor.fetchone()!=('day6_lab','160016',boot.CLUSTER,'0.8.7',
                    boot.MIGRATION_SHA256,boot.APPROVED_CATALOG):raise ValueError()
            cursor.execute(database_probe.PERMISSIONS_SQL)
            row=cursor.fetchone()
            if (not isinstance(row,tuple) or len(row)!=17 or row[:2]!=(role,role)
                    or any(type(v) is not bool for v in row[2:14])
                    or not all(row[2:7]) or any(row[7:14])
                    or row[14:16]!=('on','repeatable read')):raise ValueError()
            cursor.execute("SELECT c.relname,has_table_privilege(current_user,c.oid,'SELECT') "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=%s AND c.relkind='r' ORDER BY c.relname",('day6_ingestion',))
            rows=cursor.fetchall()
            if (rows!=[(name,True) for name in sorted(database_probe.TABLES)]
                    or any(type(r[1]) is not bool for r in rows)):raise ValueError()
    except Exception:raise auth.AuthorizationError('Retrieval connection identity/permissions rejected') from None


class _ReadOnlyStore(PgVectorStore):
    def __init__(self,prepared,channel,role,*,root,request):
        super().__init__('EXPLICIT_PRIVATE_CONNECTOR',384,dataset_id=prepared.baseline.dataset_id,
            profile_id=prepared.profile.profile_id,profile=prepared.profile,context=prepared.context)
        self._channel=channel;self._role=role
        self._root=root;self._approved_request=deepcopy(request)

    def _connect(self,*,readonly=False):
        if readonly is not True:raise auth.AuthorizationError('Writable connections prohibited')
        connection=_connector(self._channel,self._role,target=dict(database_probe.TARGET),readonly=True)
        try:
            if (connection.info.host,connection.info.port,connection.info.dbname,connection.info.user)!= (
                    '127.0.0.1',55433,'day6_lab',self._role):
                raise auth.AuthorizationError('Actual connection identity mismatch')
        except Exception:
            connection.close()
            raise auth.AuthorizationError('Actual connection identity mismatch') from None
        return connection

    @contextmanager
    def retrieval_session(self,**kwargs):
        _assert_runtime_identity(self._root,self._approved_request)
        with super().retrieval_session(**kwargs) as session:
            _assert_runtime_identity(self._root,self._approved_request)
            _verify_retrieval_connection(session._connection,self._role)
            yield session


def execute_live_dev(*,root,run_id,output,executor_id,selected_role,credential_channel_id,
                     credential_channel,request_canonical,approval,authority,split='dev'):
    """One authorized attempt; no default authority, wiring overrides or retries."""
    if split!='dev':raise auth.AuthorizationError('TEST_EXECUTION_BLOCKED')
    _channel(credential_channel,credential_channel_id)
    root=Path(root).resolve()
    _workspace_identity(root)
    prepared=boot.prepare_dev(root=root,split='dev',output=output)
    actual=live_dev_request(root=root,prepared=prepared,run_id=run_id,output=output,
        executor_id=executor_id,selected_role=selected_role,credential_channel_id=credential_channel_id)
    if actual!=request_canonical:raise auth.AuthorizationError('Fresh DEV request mismatch')
    decision=lab.verify_manual_decision(actual,approval,authority=authority,scope=SCOPE)
    request=json.loads(actual)
    _assert_runtime_identity(root,request)
    auth.ConsumptionLedger(root=root).consume(actual,decision.grant)
    try:
        audit=lab._LabAudit(root=root,request=json.loads(actual),decision=decision)
        audit.write_verified('CONSUMED')
    except Exception:raise lab.LabAuditError('CONSUMED_AUDIT_UNAVAILABLE_NO_RUNTIME_NO_RETRY') from None
    adapter=producer=store=None
    try:
        def stage(name):
            _assert_runtime_identity(root,request)
            audit.stage=name;audit.write_verified('STAGE_STARTED')
        stage('MODEL_ARTIFACTS')
        model=prepared.plan['model']
        validate_snapshot_inventory(root=root,model=model,snapshot_path=root/model['snapshot'],
            cache_dir=root/model['cache'])
        stage('MODEL_FACTORY')
        adapter=_initialize_model(prepared,root);_verify_model(adapter,prepared,root)
        producer=QueryProducer(adapter,prepared.profile,cache_root=root/prepared.plan['model']['cache'])
        stage('DATABASE_PROBE')
        def connector(**kwargs):return _connector(credential_channel,selected_role,**kwargs)
        backend=database_probe._inspect(prepared,selected_role=selected_role,connection_factory=connector)
        if (backend.get('status')!='PASS' or backend.get('warnings')
                or backend.get('identity',{}).get('role_review_required') is not False):
            raise auth.AuthorizationError('Database role/identity rejected')
        stage('EVALUATION_RUNNER')
        store=_ReadOnlyStore(prepared,credential_channel,selected_role,root=root,request=request)
        result=run_evaluation(prepared.bundle,store=store,producer=producer,baseline=prepared.baseline,
            config=deepcopy(DEFAULT_CONFIG),identity=prepared.plan['code'],backend_identity=backend['identity'],
            output_directory=None)
        if (result.get('status') not in ('COMPLETE','INCOMPLETE')
                or (result['status']=='INCOMPLETE' and result.get('summary') is not None)):
            raise auth.AuthorizationError('Invalid runner outcome')
        result=deepcopy(result);result['manifest']['run_id']=run_id
        stage('ARTIFACT_SAVE')
        artifact=boot.save_dev_artifacts(result,root/output,root=root)
        stage('ARTIFACT_VERIFY')
        verified=boot.verify_dev_artifacts(root/output,root=root)
        if verified!=artifact:raise auth.AuthorizationError('Artifact verification mismatch')
        audit.write_verified('COMPLETED_VERIFIED' if result['status']=='COMPLETE' else 'RUN_INCOMPLETE',
            artifact_sha256=digest(verified))
        return dict(status=result['status'],run_id=run_id,artifact=verified,scope=SCOPE)
    except Exception as error:
        if isinstance(error,lab.LabAuditError):raise
        status={'ARTIFACT_SAVE':'ARTIFACT_WRITE_FAILED','ARTIFACT_VERIFY':'ARTIFACT_VERIFY_FAILED'}.get(
            audit.stage,'FAILED_NO_RESULT')
        audit.write_verified(status,error_code='RUN_FAILED_NO_RETRY')
        raise lab.LabAuditError('CONSUMED_DEV_FAILED_SEE_AUDIT_NO_RETRY') from None
    finally:
        store=producer=adapter=None
