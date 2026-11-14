"""Synthetic bundles, context and connection mocks only; no model/DB/evaluation."""
from copy import deepcopy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import json
import subprocess
import sys

import pytest

from starter.src import dev_bootstrap as boot
from starter.src.evaluation_runner import DEFAULT_CONFIG, file_sha, export_trace
from starter.src.evaluation import trace_identity, digest, evaluate_query, summarize
from starter.tests.test_benchmark import sample, bundle, frozen_bundle
from starter.tests.test_store import profile


@pytest.fixture
def local(frozen_bundle,profile,monkeypatch):
    root,folder,corpus=frozen_bundle
    for p in corpus.pages:
        p.metadata.update(source_id=p.document_id,physical_page=p.page,page_id='fixture:'+str(p.page),
            printed_page_label=None,section_evidence='Synthetic heading',version=None,
            normalized_char_count=len(p.text),extraction_status='ok')
    corpus.sources[0]['source']=corpus.pages[0].source
    snapshots=tuple(SimpleNamespace(snapshot_id=c*64,expected_count=n,selected_page_count=40)
                    for c,n in (('a',246),('b',264)))
    baseline=SimpleNamespace(snapshots=snapshots,descriptor_hashes=('c'*64,'d'*64),
                             validate_approved_identity=Mock())
    monkeypatch.setattr(boot,'APPROVED_MANIFEST',corpus.manifest_sha256)
    monkeypatch.setattr(boot,'APPROVED_SOURCES',{'synthetic':'a'*64})
    monkeypatch.setattr(boot,'APPROVED_FREEZE',file_sha(folder/'freeze_manifest.json'))
    monkeypatch.setattr(boot,'STAGE4_PROFILE',profile.profile_id)
    monkeypatch.setattr(boot,'STAGE4_SNAPSHOTS',tuple(s.snapshot_id for s in snapshots))
    monkeypatch.setattr(boot,'MODEL',profile.config['model_name'])
    monkeypatch.setattr(boot,'REVISION',profile.config['revision'])
    loader=Mock(return_value=corpus)
    monkeypatch.setattr(boot,'load_manifest_pages',loader)
    baseline_factory=Mock(return_value=baseline)
    monkeypatch.setattr(boot.RetrievalBaseline,'from_context',baseline_factory)
    for name in (*boot.IDENTITY_FILES,'starter/src/dev_bootstrap.py','starter/scripts/prepare_dev_evaluation.py'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('Synthetic source identity only: '+name)
    def identity(*,root):
        hashes={name:file_sha(root/name) for name in boot.IDENTITY_FILES}
        return dict(evaluator_sha256=digest(hashes),source_hashes=hashes,code_revision='f'*40,dirty=True)
    identity_mock=Mock(side_effect=identity)
    monkeypatch.setattr(boot,'evaluator_identity',identity_mock)
    (root/'results').mkdir()
    evidence=root/'results/full_corpus_embedding_preflight.json'
    evidence.write_text(json.dumps(dict(passed=True,profile_id=profile.profile_id,profile=profile.config)))
    return SimpleNamespace(root=root,folder=folder,corpus=corpus,profile=profile,baseline=baseline,
        loader=loader,baseline_factory=baseline_factory,evidence=evidence,identity=identity_mock)


def test_valid_local_plan_no_runtime(local,monkeypatch):
    probe=Mock(side_effect=AssertionError('must not connect'))
    monkeypatch.setattr(boot,'probe_database',probe)
    prepared=boot.prepare_dev(root=local.root)
    assert prepared.plan['execution_enabled'] is False
    assert prepared.plan['test_execution']=='BLOCKED'
    assert prepared.plan['physical_pages']==40 and prepared.plan['question_count']==15
    assert prepared.plan['retrieval_calls']==45 and prepared.plan['config']['deadline_seconds']==120
    assert prepared.plan['model']['state']=='PLANNED_NOT_LOADED'
    assert prepared.plan['database']['state']=='PLANNED_NOT_CONNECTED'
    assert len(prepared.context.pages)==40
    args=local.baseline_factory.call_args.args
    assert args[2] is prepared.context  # independent loader context, not DB rows
    probe.assert_not_called()
    assert not (local.root/'data/local/stage5').exists()


@pytest.mark.parametrize('split',['test','all',None])
def test_split_rejected_before_local_access(local,split):
    with pytest.raises(PermissionError):boot.prepare_dev(split=split,root=local.root)
    local.loader.assert_not_called()


@pytest.mark.parametrize('field,value',[('top_k',4),('top_k',3.0),('deadline_seconds',121),
    ('deadline_seconds',True),('strategies',['B']),('selected_strategy','A')])
def test_wrong_dev_config(local,field,value):
    c=deepcopy(DEFAULT_CONFIG);c[field]=value
    with pytest.raises(ValueError):boot.prepare_dev(root=local.root,config=c)
    local.loader.assert_not_called()


@pytest.mark.parametrize('bad',['pages','source','manifest','duplicate'])
def test_bad_corpus(local,bad):
    if bad=='pages':local.corpus.pages.pop()
    elif bad=='source':local.corpus.sources[0]['sha256']='f'*64
    elif bad=='manifest':local.corpus.manifest_sha256='f'*64
    else:local.corpus.pages[-1]=local.corpus.pages[0]
    with pytest.raises(ValueError):boot.prepare_dev(root=local.root)


@pytest.mark.parametrize('name',['dev.jsonl','test.jsonl','freeze_manifest.json'])
def test_frozen_hash_mismatch(local,name):
    p=local.folder/name;p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(ValueError):boot.prepare_dev(root=local.root)


def test_wrong_profile(local):
    e=json.loads(local.evidence.read_text());e['profile_id']='0'*64;local.evidence.write_text(json.dumps(e))
    with pytest.raises(ValueError,match='profile'):boot.prepare_dev(root=local.root)


@pytest.mark.parametrize('field,value',[('snapshot_id','f'*64),('expected_count',245),('selected_page_count',39)])
def test_wrong_snapshot(local,field,value):
    setattr(local.baseline.snapshots[0],field,value)
    with pytest.raises(ValueError,match='snapshot'):boot.prepare_dev(root=local.root)


def test_execute_cannot_be_enabled_by_flags():
    with pytest.raises(PermissionError,match='DISABLED'):boot.execute_dev(approved=True,force=True)


@pytest.fixture
def db(monkeypatch):
    connection,cursor=Mock(),Mock()
    connection.info=SimpleNamespace(host='127.0.0.1',port=55433,dbname='day6_lab')
    connection.__enter__=Mock(return_value=connection)
    connection.__exit__=Mock(return_value=False)
    connection.transaction.side_effect=lambda:nullcontext()
    connection.cursor.return_value=cursor
    cursor.__enter__=Mock(return_value=cursor);cursor.__exit__=Mock(return_value=False)
    cursor.fetchone.side_effect=[('day6_lab','160016','on',boot.CLUSTER,'0.8.7'),(True,False,False)]
    cursor.fetchall.return_value=[(1,boot.MIGRATION_SHA256,boot.APPROVED_CATALOG,boot.APPROVED_CATALOG)]
    monkeypatch.setattr(boot.PgVectorStore,'_verify_schema',Mock())
    factory=Mock(return_value=connection)
    return SimpleNamespace(conn=connection,cursor=cursor,factory=factory,
                           target=dict(host='127.0.0.1',port=55433,dbname='day6_lab'))


def test_readonly_identity_probe_with_mock(db):
    result=boot.probe_database(db.target,db.factory)
    db.factory.assert_called_once_with(target=db.target,readonly=True)
    assert result['transaction_read_only'] and not result['role_review_required']
    assert all(c.args[0].startswith(('SELECT ','SET TRANSACTION READ ONLY')) for c in db.cursor.execute.call_args_list)
    db.conn.__exit__.assert_called_once()


@pytest.mark.parametrize('index,value',[(0,'wrong'),(1,'160015'),(2,'off'),(3,'999'),(4,'0.8.6')])
def test_wrong_server_identity_fails_and_closes(db,index,value):
    row=['day6_lab','160016','on',boot.CLUSTER,'0.8.7'];row[index]=value
    db.cursor.fetchone.side_effect=[tuple(row)]
    with pytest.raises(ValueError):boot.probe_database(db.target,db.factory)
    db.conn.__exit__.assert_called_once();db.factory.assert_called_once()


def test_target_rejected_before_factory(db):
    with pytest.raises(ValueError):boot.probe_database(dict(db.target,port=55434),db.factory)
    db.factory.assert_not_called()


def test_actual_client_endpoint_mismatch(db):
    db.conn.info.port=55434
    with pytest.raises(ValueError):boot.probe_database(db.target,db.factory)
    db.cursor.execute.assert_not_called();db.conn.__exit__.assert_called_once()


def test_migration_catalog_mismatch(db):
    db.cursor.fetchall.return_value=[(1,boot.MIGRATION_SHA256,'f'*64,'f'*64)]
    with pytest.raises(ValueError,match='catalog'):boot.probe_database(db.target,db.factory)
    db.conn.__exit__.assert_called_once()


@pytest.mark.parametrize('privileges',[(True,True,False),(True,False,True)])
def test_privileged_role_requires_review(db,privileges):
    db.cursor.fetchone.side_effect=[('day6_lab','160016','on',boot.CLUSTER,'0.8.7'),privileges]
    assert boot.probe_database(db.target,db.factory)['role_review_required']


def test_backend_failure_no_retry(db):
    db.factory.side_effect=RuntimeError('synthetic connection unavailable')
    with pytest.raises(RuntimeError):boot.probe_database(db.target,db.factory)
    db.factory.assert_called_once()


def run_fixture():
    # Storage-only partial record, deliberately NOT a complete benchmark result.
    trace=dict(question_id='synthetic',split='dev',strategy='A',status='RETRIEVED',
               question='C:/Users/Synthetic/source',hits=[])
    trace['raw_trace_sha256']=trace['trace_sha256']=trace_identity(trace)
    return dict(status='INCOMPLETE',manifest=dict(split='dev',freeze_sha256='a'*64),
                receipts=[],traces=[trace],summary=None)


def test_raw_and_exported_artifacts_separate_verifiable(tmp_path):
    result=run_fixture();before=deepcopy(result)
    path='data/local/stage5/runs/synthetic'
    manifest=boot.save_dev_artifacts(result,path,root=tmp_path)
    assert boot.verify_dev_artifacts(path,root=tmp_path)==manifest
    assert result==before
    raw=json.loads((tmp_path/path/'private/raw_run.json').read_text())
    export=json.loads((tmp_path/path/'exported/run.json').read_text())
    assert raw['traces'][0]['question']=='C:/Users/Synthetic/source'
    assert 'Synthetic/source' not in json.dumps(export)
    assert export['traces'][0]['raw_trace_sha256']==raw['traces'][0]['raw_trace_sha256']
    with pytest.raises(FileExistsError):boot.save_dev_artifacts(result,path,root=tmp_path)


@pytest.mark.parametrize('key,value',[('vector',[1]*384),('dsn','hidden'),('password','hidden'),('cache_payload',{})])
def test_forbidden_payload_rejected_before_creating_directory(tmp_path,key,value):
    result=run_fixture();result[key]=value
    with pytest.raises(ValueError):boot.save_dev_artifacts(result,'data/local/stage5/runs/x',root=tmp_path)
    assert not (tmp_path/'data').exists()


@pytest.mark.parametrize('path',['../outside','data/local/stage4/x','data/local/stage5/embedding_cache/x',
                               'data/local/stage5/runs/x/../y'])
def test_bad_output_path(tmp_path,path):
    with pytest.raises(ValueError):boot.save_dev_artifacts(run_fixture(),path,root=tmp_path)


def test_artifact_tamper_detected(tmp_path):
    path=tmp_path/'data/local/stage5/runs/x'
    boot.save_dev_artifacts(run_fixture(),path,root=tmp_path)
    p=path/'exported/run.json';p.write_text(p.read_text()+' ')
    with pytest.raises(ValueError,match='checksum'):boot.verify_dev_artifacts(path,root=tmp_path)


def test_failed_bundle_unfinalized_on_write_error(tmp_path,monkeypatch):
    path=tmp_path/'data/local/stage5/runs/x'
    monkeypatch.setattr(boot,'write_artifacts',Mock(side_effect=OSError('synthetic disk full')))
    with pytest.raises(OSError):boot.save_dev_artifacts(run_fixture(),path,root=tmp_path)
    assert (path/'private/raw_run.json').is_file() and not (path/'artifact_manifest.json').exists()
    boot.write_artifacts.assert_called_once()
    with pytest.raises(FileNotFoundError):boot.verify_dev_artifacts(path,root=tmp_path)


def test_incomplete_cannot_have_summary(tmp_path):
    result=run_fixture();result['summary']={}
    with pytest.raises(ValueError):boot.save_dev_artifacts(result,'data/local/stage5/runs/x',root=tmp_path)


def test_symlink_escape(tmp_path):
    base=tmp_path/'data/local/stage5/runs';base.mkdir(parents=True)
    outside=tmp_path/'outside';outside.mkdir()
    (base/'linked').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):boot.save_dev_artifacts(run_fixture(),base/'linked/x',root=tmp_path)


def test_cli_no_execution_flags():
    script=Path(boot.__file__).parents[1]/'scripts/prepare_dev_evaluation.py'
    result=subprocess.run([sys.executable,'-B',str(script),'--split','test'],capture_output=True,text=True)
    assert result.returncode==2
    help_text=subprocess.check_output([sys.executable,'-B',str(script),'--help'],text=True)
    assert '--execute' not in help_text and '--force' not in help_text and '--test-approval' not in help_text


def test_existing_output_blocks_before_preflight(local):
    (local.root/'data/local/stage5/runs/planned-dev').mkdir(parents=True)
    with pytest.raises(FileExistsError):boot.prepare_dev(root=local.root)
    local.loader.assert_not_called()


def test_cache_symlink_rejected_without_runtime(local):
    stage5=local.root/'data/local/stage5';stage5.mkdir(parents=True)
    old=local.root/'data/local/stage4/cache';old.mkdir(parents=True)
    (stage5/'embedding_cache').symlink_to(old,target_is_directory=True)
    with pytest.raises(ValueError):boot.prepare_dev(root=local.root)
    local.loader.assert_not_called()


def test_incomplete_artifacts_preserve_null_summary(tmp_path):
    result=run_fixture();result.update(status='INCOMPLETE',summary=None)
    path='data/local/stage5/runs/incomplete'
    manifest=boot.save_dev_artifacts(result,path,root=tmp_path)
    assert manifest['status']=='INCOMPLETE' and boot.verify_dev_artifacts(path,root=tmp_path)==manifest


def test_artifact_manifest_symlink_rejected(tmp_path):
    path=tmp_path/'data/local/stage5/runs/x'
    boot.save_dev_artifacts(run_fixture(),path,root=tmp_path)
    p=path/'artifact_manifest.json';outside=tmp_path/'other.json'
    outside.write_bytes(p.read_bytes());p.unlink();p.symlink_to(outside)
    with pytest.raises(ValueError):boot.verify_dev_artifacts(path,root=tmp_path)


def test_embedded_web_credentials_rejected_before_write(tmp_path):
    result=run_fixture();result['traces'][0]['question']='https://fixture:DO_NOT_EXPORT@example.invalid/file'
    with pytest.raises(ValueError,match='Credential'):
        boot.save_dev_artifacts(result,'data/local/stage5/runs/x',root=tmp_path)
    assert not (tmp_path/'data').exists()


def test_rehashed_export_cannot_diverge_from_raw(tmp_path):
    path=tmp_path/'data/local/stage5/runs/x'
    boot.save_dev_artifacts(run_fixture(),path,root=tmp_path)
    p=path/'exported/run.json';e=json.loads(p.read_text());e['manifest']['run_id']='forged-synthetic'
    p.write_text(json.dumps(e))
    mpath=path/'artifact_manifest.json';m=json.loads(mpath.read_text())
    m['files']['exported/run.json']=file_sha(p);mpath.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='deterministic'):
        boot.verify_dev_artifacts(path,root=tmp_path)


@pytest.fixture
def complete_artifact(profile,monkeypatch):
    """Synthetic coverage fixture only: no model, retrieval or real benchmark results."""
    import hashlib
    for key,value in dict(STAGE4_PROFILE=profile.profile_id,APPROVED_FREEZE='a'*64,
            APPROVED_MANIFEST='b'*64,APPROVED_SOURCES={'synthetic':'c'*64},
            STAGE4_SNAPSHOTS=('d'*64,'e'*64)).items():
        monkeypatch.setattr(boot,key,value)
    ids=['synthetic-dev-'+str(i) for i in range(15)]
    labels=['STRUCTURAL_INTEGRITY_VERIFIED','VECTOR_INTEGRITY_NOT_REVERIFIED']
    receipts=[];traces=[]
    for qid in ids:
        question='Synthetic question '+qid
        receipt=dict(question_id=qid,producer_profile_id=profile.profile_id,
            input_sha256=hashlib.sha256(('query: '+question).encode()).hexdigest(),vector_sha256='f'*64,
            token_count=10,dimensions=384,query_prefix='query: ',dtype='float32')
        receipts.append(receipt)
        for strategy in ('A','B','C'):
            traces.append(dict(question_id=qid,split='dev',strategy=strategy,question=question,
                query_receipt=deepcopy(receipt),status='SUCCESS',hits=[],applied_filter=None,
                snapshot_id=boot.STAGE4_SNAPSHOTS[0 if strategy=='A' else 1],integrity_labels=labels,
                retrieval_seconds=0.0,evaluation=evaluate_query(dict(id=qid,split='dev'),[])))
    sources={'synthetic.py':'f'*64}
    manifest=dict(run_version=1,run_id='SYNTHETIC_FIXTURE',started_at='SYNTHETIC_FIXTURE',
        finished_at='SYNTHETIC_FIXTURE',split='dev',question_ids=ids,freeze_sha256=boot.APPROVED_FREEZE,
        benchmark_manifest_sha256='f'*64,frozen_files={name:dict(sha256='f'*64,count=count)
            for name,count in (('dev.jsonl',15),('test.jsonl',5))},source_checksums=boot.APPROVED_SOURCES,
        profile_id=profile.profile_id,embedding_config=profile.config,profile_config_sha256=profile.profile_id,
        model_revision=profile.config['revision'],dataset_id='synthetic',snapshot_ids=list(boot.STAGE4_SNAPSHOTS),
        manifest_sha256=boot.APPROVED_MANIFEST,corpus_sha256='f'*64,descriptor_hashes=['f'*64,'f'*64],
        code=dict(source_hashes=sources,evaluator_sha256=digest(sources),code_revision='f'*40,dirty=True),
        configuration=deepcopy(DEFAULT_CONFIG),configuration_sha256=digest(DEFAULT_CONFIG),
        backend_identity=dict(verification='SYNTHETIC_FIXTURE'),library_versions={'fixture':'synthetic'},
        integrity_labels=labels,status='COMPLETE',attempted=45,succeeded=45,retrieved=45,failed=0)
    return dict(status='COMPLETE',manifest=manifest,receipts=receipts,traces=traces,
                summary=summarize(traces),error=None,manual_review=None)


def test_synthetic_complete_coverage_round_trip(tmp_path,complete_artifact):
    path='data/local/stage5/runs/synthetic-complete'
    manifest=boot.save_dev_artifacts(complete_artifact,path,root=tmp_path)
    assert boot.verify_dev_artifacts(path,root=tmp_path)==manifest


@pytest.mark.parametrize('tamper',['missing_trace','duplicate_trace','missing_question','duplicate_question',
    'missing_receipt','receipt_profile','query_hash','snapshot','profile','summary','metric','failed_trace'])
def test_complete_rejects_partial_or_tampered_coverage(tmp_path,complete_artifact,tamper):
    r=complete_artifact
    if tamper=='missing_trace':r['traces'].pop()
    elif tamper=='duplicate_trace':r['traces'][-1]=deepcopy(r['traces'][0])
    elif tamper=='missing_question':r['manifest']['question_ids'].pop()
    elif tamper=='duplicate_question':r['manifest']['question_ids'][-1]=r['manifest']['question_ids'][0]
    elif tamper=='missing_receipt':r['receipts'].pop()
    elif tamper=='receipt_profile':r['receipts'][0]['producer_profile_id']='0'*64
    elif tamper=='query_hash':r['receipts'][0]['input_sha256']='0'*64
    elif tamper=='snapshot':r['traces'][0]['snapshot_id']='0'*64
    elif tamper=='profile':r['manifest']['profile_id']='0'*64
    elif tamper=='summary':r['summary']['groups'][0]['exact_hit_at_1']['numerator']=1
    elif tamper=='metric':
        r['traces'][0]['evaluation']['exact_hit_at_1']=1;r['summary']=summarize(r['traces'])
    else:r['traces'][0]['status']='FAILED'
    with pytest.raises(ValueError):boot.save_dev_artifacts(r,'data/local/stage5/runs/bad',root=tmp_path)
    assert not (tmp_path/'data').exists()


@pytest.mark.parametrize('field',['query_vector','database_password','embedding_values','unexpected_payload'])
@pytest.mark.parametrize('boundary',['run','trace','receipt','hit','metadata','backend'])
def test_closed_schema_rejects_nested_payloads(tmp_path,complete_artifact,field,boundary):
    r=complete_artifact
    target={'run':r,'trace':r['traces'][0],'receipt':r['receipts'][0],
            'backend':r['manifest']['backend_identity']}.get(boundary)
    if boundary in ('hit','metadata'):
        hit={'metadata':{}};r['traces'][0]['hits']=[hit]
        target=hit if boundary=='hit' else hit['metadata']
    target[field]={'nested':{'payload':[0.1,0.2]}}
    with pytest.raises(ValueError,match='allowlist'):
        boot.save_dev_artifacts(r,'data/local/stage5/runs/bad',root=tmp_path)
    assert not (tmp_path/'data').exists()


def test_storage_fixture_cannot_claim_complete(tmp_path):
    r=run_fixture();r['status']='COMPLETE'
    with pytest.raises(ValueError):boot.save_dev_artifacts(r,'data/local/stage5/runs/bad',root=tmp_path)


def test_all_code_hashes_use_explicit_workspace(local):
    prepared=boot.prepare_dev(root=local.root)
    local.identity.assert_called_once_with(root=local.root.resolve())
    for name,sha in prepared.plan['code']['source_hashes'].items():
        assert sha==file_sha(local.root/name)
    for name,sha in prepared.plan['bootstrap_source_hashes'].items():
        assert sha==file_sha(local.root/name)


def test_mixed_workspace_hashes_rejected(local):
    original=local.identity.side_effect
    def mixed(*,root):
        result=original(root=root);result['source_hashes'][boot.IDENTITY_FILES[0]]='0'*64
        result['evaluator_sha256']=digest(result['source_hashes'])
        return result
    local.identity.side_effect=mixed
    with pytest.raises(ValueError,match='workspace'):boot.prepare_dev(root=local.root)
