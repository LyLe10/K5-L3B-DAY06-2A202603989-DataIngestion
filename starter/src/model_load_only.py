"""Model-load-only preparation. Live entry disabled; synthetic factory seam only."""
from pathlib import Path
import json
from unittest.mock import Mock

from . import dev_bootstrap as boot, dev_authorization as auth, lab_dev_runtime as lab
from .embeddings import MODEL, REVISION, ARTIFACTS
from .evaluation import digest
from .evaluation_runner import file_sha
from .schema import EmbeddingProfile, canonical_json

SCOPE='LAB_MODEL_LOAD_ONLY'
LIVE_SCOPE='LAB_MODEL_LOAD_ONLY_LIVE'
CODE_FILES=('starter/src/model_load_only.py','starter/src/pinned_model_factory.py','starter/src/embeddings.py','starter/src/schema.py',
    'starter/src/dev_authorization.py','starter/src/lab_dev_runtime.py','starter/src/dev_bootstrap.py',
    'starter/src/evaluation.py','starter/src/evaluation_runner.py','starter/src/retrieval.py','starter/src/store.py')
FACTORY_CONTRACT=dict(constructor='starter.src.embeddings.MyEmbedder',local_files_only=True,
    trust_remote_code=False,device='cpu',dtype='float32',eval_mode=True,batch_size=16)


def execute_model_load_only(*,root=None,run_id=None,executor_id=None,request_canonical=None,approval=None,authority=None,**unsupported):
    if authority is None or unsupported:raise PermissionError('MODEL_LOAD_ONLY_LIVE_DISABLED: independent verifier required; no bypass flags')
    return _run_model_load(root=root,run_id=run_id,executor_id=executor_id,
        request_canonical=request_canonical,approval=approval,authority=authority,
        model_factory=None,live=True)


class ModelLoadPreparationError(lab.LabAuditError):
    def __init__(self,status):
        self.status=status
        super().__init__(status+': consumed; no retry or reset')


def _verified_audit(audit,status,*,error_code=None):
    """Read back canonical audit bytes; no success on write/verification failure."""
    try:
        expected=audit.write(status,error_code=error_code)
        path=boot.stage5_path(audit.root,audit.path/f'{audit.sequence:04}.json',category='lab_audit')
        payload=path.read_bytes();record=json.loads(payload)
        if (payload!=(canonical_json(record)+'\n').encode() or digest(record)!=expected
                or record['status']!=status or record['run_id']!=audit.request['run_id']
                or record['request_sha256']!=digest(audit.request)
                or record['profile_id']!=audit.request['profile_id']
                or record['model_name']!=MODEL or record['model_revision']!=REVISION):
            raise ValueError('Audit mismatch')
    except Exception:raise ModelLoadPreparationError('AUDIT_WRITE_FAILED') from None


def model_load_request(*, root, run_id, executor_id, live=False):
    """Local metadata only. Does not instantiate, tokenize, encode or touch database."""
    root=Path(root).resolve();auth._identifier(run_id);auth._identifier(executor_id)
    destination=boot.stage5_path(root,'data/local/stage5/lab_audit/'+run_id,category='lab_audit')
    if destination.exists():raise FileExistsError('Model-load audit destination exists')
    cache=boot.stage5_path(root,'data/local/stage5/embedding_cache/.plan-check',category='embedding_cache').parent
    evidence_path=root/'results/full_corpus_embedding_preflight.json'
    evidence=json.loads(evidence_path.read_text(encoding='utf-8'))
    profile=EmbeddingProfile.from_config(evidence['profile'])
    if (evidence.get('passed') is not True or evidence.get('profile_id')!=boot.STAGE4_PROFILE
            or profile.profile_id!=boot.STAGE4_PROFILE or profile.config['model_name']!=MODEL
            or profile.config['revision']!=REVISION or len(ARTIFACTS)!=10
            or profile.config['artifact_sha256']!=ARTIFACTS):
        raise auth.AuthorizationError('Approved model-only profile/artifact identity mismatch')
    hashes={}
    for name in CODE_FILES:
        path=root/name
        if not path.resolve().is_relative_to(root):raise auth.AuthorizationError('Code identity escapes workspace')
        for part in (path,*path.parents):
            if part==root:break
            if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
                raise auth.AuthorizationError('Unsafe code identity path')
        hashes[name]=file_sha(path)
    request=dict(authorization_version=1,scope=LIVE_SCOPE if live else SCOPE,purpose='MODEL_LOAD_ONLY',single_execution=True,
        execution_mode='LIVE_MODEL_LOAD_ONLY' if live else 'OFFLINE_SYNTHETIC',
        run_id=run_id,executor_id=executor_id,audit_output=destination.relative_to(root).as_posix(),
        model=dict(model_name=MODEL,revision=REVISION,
            snapshot='data/local/models/intfloat--multilingual-e5-small/'+REVISION,
            cache=cache.relative_to(root).as_posix(),profile=profile.config),profile_id=profile.profile_id,
        source_evidence_sha256=file_sha(evidence_path),code_hashes=hashes,code_sha256=digest(hashes),
        runtime=dict(device='cpu',dtype='float32',eval_mode=True),
        factory_contract=dict(FACTORY_CONTRACT),
        prohibited_operations=['query_encoding','document_encoding','postgresql','retrieval','evaluation'],
        custody_policy='LOCAL_LAB_NO_ANTI_ROLLBACK_GUARANTEE')
    return canonical_json(request)


def verify_model_load_approval(request_canonical,approval,*,authority,live=False):
    """Independent purpose separation on top of the accepted manual verifier."""
    try:
        request=json.loads(request_canonical)
        profile=EmbeddingProfile.from_config(request['model']['profile'])
        if (request['scope']!=(LIVE_SCOPE if live else SCOPE) or request['purpose']!='MODEL_LOAD_ONLY'
                or request['single_execution'] is not True or request['execution_mode']!=('LIVE_MODEL_LOAD_ONLY' if live else 'OFFLINE_SYNTHETIC')
                or request['model']['model_name']!=MODEL or request['model']['revision']!=REVISION
                or profile.profile_id!=request['profile_id'] or profile.profile_id!=boot.STAGE4_PROFILE
                or profile.config['artifact_sha256']!=ARTIFACTS or len(ARTIFACTS)!=10
                or request['runtime']!=dict(device='cpu',dtype='float32',eval_mode=True)
                or canonical_json(request.get('factory_contract'))!=canonical_json(FACTORY_CONTRACT)
                or request['code_sha256']!=digest(request['code_hashes'])):
            raise ValueError()
    except Exception:raise auth.AuthorizationError('Invalid model-load-only request') from None
    return lab.verify_manual_decision(request_canonical,approval,authority=authority,scope=LIVE_SCOPE if live else SCOPE)


def simulate_model_load_only(*, root, run_id, executor_id, request_canonical, approval, authority, model_factory):
    """One authenticated, consumed synthetic attempt. No live factory is accepted.

    Return metadata only, never the adapter/model handle. Existing dev approvals
    cannot authorize this distinct purpose, and vice versa.
    """
    if not isinstance(model_factory,Mock):raise auth.AuthorizationError('Offline mock model factory required')
    return _run_model_load(root=root,run_id=run_id,executor_id=executor_id,request_canonical=request_canonical,
        approval=approval,authority=authority,model_factory=model_factory,live=False)


def _run_model_load(*,root,run_id,executor_id,request_canonical,approval,authority,model_factory,live):
    root=Path(root).resolve()
    actual=model_load_request(root=root,run_id=run_id,executor_id=executor_id,live=live)
    if actual!=request_canonical:raise auth.AuthorizationError('Model-load request differs from fresh identities')
    decision=verify_model_load_approval(actual,approval,authority=authority,live=live)
    if live:
        from .pinned_model_factory import PinnedLocalModelFactory
        model_factory=PinnedLocalModelFactory(root=root,request_canonical=actual)._live_binding()
    auth.ConsumptionLedger(root=root).consume(actual,decision.grant)
    request=json.loads(actual)
    try:
        audit=lab._LabAudit(root=root,request=request,decision=decision);_verified_audit(audit,'CONSUMED')
    except Exception:raise ModelLoadPreparationError('AUDIT_WRITE_FAILED') from None
    adapter=None
    try:
        audit.stage='MODEL_ARTIFACTS';_verified_audit(audit,'STAGE_STARTED')
        auth.verify_model_artifacts(root=root,model=request['model'])
        audit.stage='MODEL_FACTORY';_verified_audit(audit,'STAGE_STARTED')
        adapter=model_factory(MODEL,revision=REVISION,snapshot_path=root/request['model']['snapshot'],
                              cache_dir=root/request['model']['cache'])
        audit.stage='MODEL_RUNTIME_VERIFICATION';_verified_audit(audit,'STAGE_STARTED')
        profile=EmbeddingProfile.from_config(request['model']['profile'])
        runtime=adapter.runtime;stats=adapter.stats
        if (adapter.profile_id!=profile.profile_id or adapter.profile.config_canonical!=profile.config_canonical
                or type(adapter.dimensions) is not int or adapter.dimensions!=384
                or Path(adapter._cache_dir).resolve()!=(root/request['model']['cache']).resolve()
                or any(type(runtime.get(k)) is not type(v) or runtime.get(k)!=v
                       for k,v in dict(device='cpu',dtype='float32',eval_mode=True,
                                       tokenizer_limit=512,sentence_transformers_limit=512).items())
                or any(type(stats.get(k)) is not int or stats.get(k)!=0
                       for k in ('calls','inputs','encoded_inputs','encode_batches'))
                or stats.get('token_lengths')!=[]):
            raise auth.AuthorizationError('Model runtime/profile/cache or no-encoding contract mismatch')
        _verified_audit(audit,'MODEL_LOAD_VERIFIED')
        return dict(status='MODEL_LOAD_VERIFIED',scope=request['scope'],execution_mode=request['execution_mode'],
                    run_id=run_id,profile_id=profile.profile_id,
                    request_sha256=digest(request),device='cpu',dtype='float32',eval_mode=True,encoded_inputs=0)
    except Exception as error:
        if isinstance(error,ModelLoadPreparationError):raise
        status={'MODEL_ARTIFACTS':'ARTIFACT_MISMATCH','MODEL_RUNTIME_VERIFICATION':'MODEL_PROFILE_MISMATCH'}.get(
            audit.stage,'MODEL_LOAD_FAILED')
        _verified_audit(audit,status,error_code=status)
        raise ModelLoadPreparationError(status) from None
    finally:
        # Adapter has no public close() contract. Release this owner's reference;
        # do not invent backend cleanup calls or return a reusable model handle.
        adapter=None
