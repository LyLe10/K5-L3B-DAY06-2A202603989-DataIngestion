"""Dev-only offline preparation. No model constructor, connection or evaluation call."""
from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

from .corpus import ROOT, load_manifest_pages
from .embeddings import MODEL, REVISION
from .evaluation import digest, trace_identity, summarize
from .evaluation_runner import (DEFAULT_CONFIG, evaluator_identity, file_sha, load_benchmark,
                                redact, export_trace, verify_exported_trace, write_artifacts, IDENTITY_FILES, HIT_FIELDS)
from .retrieval import RetrievalBaseline, STAGE4_PROFILE, STAGE4_SNAPSHOTS
from .schema import EmbeddingProfile, canonical_json
from .store import SnapshotContext, PgVectorStore, MIGRATION_SHA256

APPROVED_FREEZE = 'f1aafb9c62ccf63a8f98d47283a8286abe0c46087f8546cec82121d9b9586f5d'
APPROVED_MANIFEST = '6ec73dc52b8cb5d83f5b08baeffcb231109cc2bbd95525c3315ae72c1f29db5d'
APPROVED_SOURCES = {'postgresql-16.16-a4':'4cf9a4f56001191572e07959396120de0d61ca65d29072df66f9e656c24ae568'}
APPROVED_CATALOG = '209b3597e6f2a6ff8cf13f4c12f5cfc45f3bb34c07f9ff363204902323a2da55'
DATASET = 'day06-postgresql'
CLUSTER = '7707847059457269799'


def stage5_path(root, path, *, category):
    """Reject traversal, symlinks/junctions and escaping the physical workspace."""
    root = Path(root).resolve()
    path = Path(path)
    if '..' in path.parts:
        raise ValueError('Path traversal is forbidden')
    candidate = path if path.is_absolute() else root/path
    base = root/'data/local/stage5'/category
    resolved = candidate.resolve()
    if not base.resolve().is_relative_to(root) or not resolved.is_relative_to(base.resolve()) or resolved == base.resolve():
        raise ValueError('Path must be a child of data/local/stage5/'+category)
    for part in (candidate, *candidate.parents):
        if part == root:
            break
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise ValueError('Symlink/junction artifact paths are forbidden')
    return resolved


@dataclass(frozen=True)
class DevPreparation:
    plan: dict
    bundle: dict
    context: SnapshotContext
    baseline: RetrievalBaseline
    profile: EmbeddingProfile


def prepare_dev(*, split='dev', config=None, root=ROOT, output='data/local/stage5/runs/planned-dev'):
    """Local preflight only. Even a valid result does not authorize execution."""
    if split != 'dev':
        raise PermissionError('TEST_EXECUTION_BLOCKED: bootstrap accepts dev only')
    config = deepcopy(DEFAULT_CONFIG if config is None else config)
    if canonical_json(config) != canonical_json(DEFAULT_CONFIG):
        raise ValueError('Dev requires the exact approved configuration: A/B/C, K=3, deadline=120s')
    root = Path(root).resolve()
    destination = stage5_path(root, output, category='runs')
    if destination.exists():
        raise FileExistsError('Output exists; never overwrite')
    stage5_path(root,'data/local/stage5/embedding_cache/.plan-check',category='embedding_cache')
    corpus = load_manifest_pages(root/'data/manifest.json',root=root)
    if (len(corpus.pages)!=40 or len({(p.document_id,p.page) for p in corpus.pages})!=40
            or any(type(p.page) is not int or p.page<1 for p in corpus.pages)
            or corpus.manifest_sha256!=APPROVED_MANIFEST
            or {s['source_id']:s['sha256'] for s in corpus.sources}!=APPROVED_SOURCES):
        raise ValueError('Verified corpus differs from approved 40-page source snapshot')
    context = SnapshotContext.from_ingestion_result(corpus)
    evidence = json.loads((root/'results/full_corpus_embedding_preflight.json').read_text())
    profile = EmbeddingProfile.from_config(evidence['profile'])
    if (evidence.get('passed') is not True or evidence.get('profile_id')!=STAGE4_PROFILE
            or profile.profile_id!=STAGE4_PROFILE or profile.config['model_name']!=MODEL
            or profile.config['revision']!=REVISION):
        raise ValueError('Canonical Stage 4 profile identity mismatch')
    baseline = RetrievalBaseline.from_context(DATASET,profile.profile_id,context)
    if (tuple(s.snapshot_id for s in baseline.snapshots)!=STAGE4_SNAPSHOTS
            or tuple(s.expected_count for s in baseline.snapshots)!=(246,264)
            or any(s.selected_page_count!=40 for s in baseline.snapshots)):
        raise ValueError('Approved A/B snapshots/counts mismatch')
    baseline.validate_approved_identity()
    identity = evaluator_identity(root=root)
    if set(identity.get('source_hashes',{})) != set(IDENTITY_FILES):
        raise ValueError('Incomplete workspace code identity')
    if identity.get('evaluator_sha256')!=digest(identity['source_hashes']):
        raise ValueError('Workspace evaluator hash mismatch')
    for name,sha in identity['source_hashes'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or file_sha(path)!=sha:
            raise ValueError('Source code identity differs from requested workspace')
    bundle = load_benchmark(root/'benchmark','dev',config=config,identity=identity,root=root,corpus=corpus)
    if bundle['freeze_sha256']!=APPROVED_FREEZE or len(bundle['questions'])!=15:
        raise ValueError('Approved freeze/dev question identity mismatch')
    code={}
    for name in ('starter/src/dev_bootstrap.py','starter/scripts/prepare_dev_evaluation.py'):
        path=(root/name).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Bootstrap source escapes requested workspace')
        code[name]=file_sha(path)
    plan = dict(plan_version=1,status='LOCAL_PREFLIGHT_VALID_RUNTIME_DISABLED',split='dev',
        execution_enabled=False,test_execution='BLOCKED',config=config,configuration_sha256=digest(config),
        freeze_sha256=bundle['freeze_sha256'],benchmark_manifest_sha256=bundle['benchmark_manifest_sha256'],
        frozen_files=bundle['frozen_files'],question_ids=[q['id'] for q in bundle['questions']],
        question_count=15,retrieval_calls=45,physical_pages=40,manifest_sha256=corpus.manifest_sha256,
        source_checksums=APPROVED_SOURCES,profile_id=profile.profile_id,
        snapshot_ids=list(STAGE4_SNAPSHOTS),descriptor_hashes=list(baseline.descriptor_hashes),
        model=dict(factory='starter.src.embeddings.MyEmbedder',model_name=MODEL,revision=REVISION,
                   snapshot='data/local/models/intfloat--multilingual-e5-small/'+REVISION,
                   cache='data/local/stage5/embedding_cache',device='cpu',dtype='float32',eval_mode=True,
                   normalize_embeddings=True,query_prefix='query: ',profile=profile.config,
                   state='PLANNED_NOT_LOADED'),
        database=dict(host='127.0.0.1',port=55433,dbname='day6_lab',cluster=CLUSTER,
                      postgresql='16.16',pgvector='0.8.7',read_only=True,
                      migration_sha256=MIGRATION_SHA256,catalog_sha256=APPROVED_CATALOG,
                      state='PLANNED_NOT_CONNECTED',preferred_role='SELECT_ONLY'),
        output=destination.relative_to(root).as_posix(),code=identity,bootstrap_source_hashes=code,
        integrity='LOCAL_SOURCE_VERIFIED_DATABASE_NOT_PROBED',
        required_approval=['model load + 15 dev query embeddings','main PostgreSQL read-only probe/retrieval',
                           'one dev run with deadline 120 seconds'])
    plan['plan_sha256']=digest(plan)
    return DevPreparation(plan,bundle,context,baseline,profile)


def execute_dev(*args,**kwargs):
    raise PermissionError('RUNTIME_EXECUTION_DISABLED: separate execution approval and implementation required')


def probe_database(target, connection_factory, *, inspection=None):
    """Explicit future read-only probe. No default driver, DSN, discovery or retry.

    Never called by prepare_dev or CLI. Tests pass a synthetic factory.
    A live factory requires separate approval; it must set default read-only mode.
    Optional trusted inspection runs in the same owned transaction; when supplied,
    the transaction uses REPEATABLE READ. It must not reconnect or issue writes.
    """
    expected = dict(host='127.0.0.1',port=55433,dbname='day6_lab')
    if target!=expected or type(target.get('port')) is not int:
        raise ValueError('Unapproved database endpoint')
    with connection_factory(target=deepcopy(target),readonly=True) as connection:
        info = connection.info
        if (info.host,info.port,info.dbname)!=('127.0.0.1',55433,'day6_lab'):
            raise ValueError('Actual client connection endpoint mismatch')
        with connection.transaction():
            with connection.cursor() as cursor:
                if inspection is not None:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                cursor.execute('SET TRANSACTION READ ONLY')
                cursor.execute("SELECT set_config('statement_timeout','10000ms',true)")
                cursor.execute("SELECT current_database(),current_setting('server_version_num'),"
                    "current_setting('transaction_read_only'),(SELECT system_identifier::text FROM pg_control_system()),"
                    "(SELECT extversion FROM pg_extension WHERE extname='vector')")
                if cursor.fetchone()!=('day6_lab','160016','on',CLUSTER,'0.8.7'):
                    raise ValueError('Database cluster/version/read-only identity mismatch')
                PgVectorStore._verify_schema(cursor)
                cursor.execute('SELECT version,checksum,catalog_sha256,day6_ingestion.catalog_fingerprint() '
                               'FROM day6_ingestion.schema_migrations')
                if cursor.fetchall()!=[(1,MIGRATION_SHA256,APPROVED_CATALOG,APPROVED_CATALOG)]:
                    raise ValueError('Approved migration/catalog identity mismatch')
                cursor.execute("SELECT bool_and(has_table_privilege(current_user,c.oid,'SELECT')),"
                    "bool_or(has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE')),"
                    "(SELECT rolsuper OR rolcreatedb OR rolcreaterole FROM pg_roles WHERE rolname=current_user) "
                    "OR has_database_privilege(current_user,current_database(),'CREATE') "
                    "OR has_schema_privilege(current_user,'day6_ingestion','CREATE') "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='day6_ingestion' AND c.relkind='r'")
                can_read,can_write,can_ddl = cursor.fetchone()
                if can_read is not True or type(can_write) is not bool or type(can_ddl) is not bool:
                    raise ValueError('Cannot verify role read privileges')
                privileged=can_write or can_ddl
            if inspection is not None:
                inspection(connection,privileged=privileged)
    return dict(database='day6_lab',postgresql='16.16',pgvector='0.8.7',cluster=CLUSTER,
                transaction_read_only=True,migration_sha256=MIGRATION_SHA256,catalog_sha256=APPROVED_CATALOG,
                role='PRIVILEGED_READONLY_TRANSACTION' if privileged else 'SELECT_ONLY_TABLE_GRANTS',
                role_review_required=privileged,scope='IDENTITY_ONLY_STRUCTURAL_PREFLIGHT_STILL_REQUIRED')


def _reject_private_secrets(value):
    if isinstance(value,dict):
        for key,item in value.items():
            if key.lower() in ('dsn','database_url','password','secret','secrets','credential','credentials',
                               'api_key','access_token','authorization','refresh_token','connection_string',
                               'vector','vectors','embedding','embeddings','cache_payload','weights','model_weights'):
                raise ValueError('Forbidden private artifact payload')
            _reject_private_secrets(item)
    elif isinstance(value,list):
        for item in value: _reject_private_secrets(item)
    elif isinstance(value,str) and re.search(r'(?i)postgres(?:ql)?://|https?://[^\s/@]+:[^\s/@]+@|-----BEGIN .*PRIVATE KEY|\bBearer\s+|\b(password|api_key|access_token|secret)\s*[=:]',value):
        raise ValueError('Credential/DSN material forbidden even in private artifacts')


def _write_new(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw)


def _artifact_schema():
    """Closed object shapes at every payload boundary; dynamic maps are scalar-only."""
    text={'type':'string'}; integer={'type':'integer'}; number={'type':'number'}
    boolean={'type':'boolean'}; null={'type':'null'}
    sha={'type':'string','pattern':'^[0-9a-f]{64}$'}
    def obj(properties,required=()):
        return dict(type='object',properties=properties,required=list(required),additionalProperties=False)
    def arr(item): return dict(type='array',items=item)
    def nullable(item): return dict(anyOf=[null,item])
    def scalar_map(item):
        return dict(type='object',additionalProperties=item,propertyNames={
            'not':{'pattern':'(?i)^(query_vector|database_password|embedding_values|payload|cache_payload)$'}})
    section=obj({'section':text},('section',))
    params=obj({'size':integer,'overlap':integer,'max_size':integer})
    chunking=obj({'strategy':text,'algorithm_version':integer,'unit':text,'parameters':params,
                  'start_char':integer,'end_char':integer,'split_sql_statement':boolean})
    metadata=obj(dict(source_id=text,physical_page=integer,page_id=text,printed_page_label=nullable(text),
        section=text,section_evidence=text,version=nullable(text),normalized_char_count=integer,
        text_sha256=sha,extraction_status=text,_chunking=chunking))
    hit=obj(dict(rank=integer,chunk_id=text,document_id=text,source=text,physical_page=integer,
        printed_page_label=nullable(text),section=text,start_char=integer,end_char=integer,text=text,
        metadata=metadata,snapshot_id=sha,manifest_sha256=sha,corpus_sha256=sha,source_sha256=sha,
        page_text_sha256=sha,text_sha256=sha,page_id=text,cosine_distance=number,score=number,
        dataset_id=text,profile_id=sha,requested_strategy=text,stored_strategy=text))
    receipt=obj(dict(question_id=text,producer_profile_id=sha,input_sha256=sha,vector_sha256=sha,
        token_count=integer,dimensions=integer,query_prefix=text,dtype=text,cache_hits=integer,
        encoded_inputs=integer,elapsed_seconds=number),('question_id','producer_profile_id','input_sha256',
        'vector_sha256','token_count','dimensions','query_prefix','dtype'))
    checks=obj({k:boolean for k in ('source','page','source_checksum','page_checksum','span_coverage',
                                    'text_consistency','quote')},('source','page','source_checksum',
                                    'page_checksum','span_coverage','text_consistency','quote'))
    diagnostic=obj(dict(rank=integer,chunk_id=text,exact_match=boolean,
        alternatives=arr(obj(dict(gold_index=integer,checks=checks,exact_match=boolean),
                             ('gold_index','checks','exact_match')))),('rank','chunk_id','exact_match','alternatives'))
    evaluation=obj(dict(question_id=text,split=text,metric_version=text,exact_hit_at_1=integer,
        exact_evidence_hit_at_3=integer,mrr_at_3=number,first_exact_rank=nullable(integer),
        evidence_status=text,diagnostics=arr(diagnostic),empty_result=boolean,filter_applied=boolean,
        filter_compliance=text),('question_id','split','metric_version','exact_hit_at_1','exact_evidence_hit_at_3',
        'mrr_at_3','first_exact_rank','evidence_status','diagnostics','empty_result','filter_applied','filter_compliance'))
    trace=obj(dict(question_id=text,split={'const':'dev'},strategy={'enum':['A','B','C']},question=text,
        query_receipt=receipt,status={'enum':['STARTED','RETRIEVED','SUCCESS','FAILED']},hits=arr(hit),
        applied_filter=nullable(section),snapshot_id=sha,integrity_labels=arr(text),retrieval_seconds=number,
        evaluation=evaluation,raw_trace_sha256=sha,trace_sha256=sha),('question_id','split','strategy','status','hits'))
    metric=obj(dict(numerator=integer,denominator=integer,rate=number),('numerator','denominator','rate'))
    group=obj(dict(split=text,strategy=text,questions=integer,exact_hit_at_1=metric,exact_evidence_hit_at_3=metric,
        mrr_at_3=number,empty_results=obj(dict(count=integer,denominator=integer,rate=number)),
        filter_diagnostics=obj(dict(filtered_questions=integer,empty_count=integer,empty_rate=nullable(number),
            nonempty_denominator=integer,compliant=integer,violations=integer,compliance=nullable(number)))))
    summary=obj(dict(metric_version=text,groups=arr(group)),('metric_version','groups'))
    config=obj({k:({'type':'array','items':text} if k=='strategies' else nullable(text) if k=='selected_strategy'
                   else number if k in ('config_version','top_k','deadline_seconds') else text)
                for k in DEFAULT_CONFIG},tuple(DEFAULT_CONFIG))
    tokenizer=obj(dict(name=text,revision=text,**{'class':text},use_fast=boolean,model_max_length=integer))
    profile=obj(dict(profile_schema_version=integer,model_name=text,revision=text,dimensions=integer,dtype=text,
        pooling=text,normalize_embeddings=boolean,document_prefix=text,query_prefix=text,tokenizer=tokenizer,
        max_seq_length=integer,artifact_sha256=scalar_map(sha),library_versions=scalar_map(text),device=text,
        backend=text,trust_remote_code=boolean,pooling_include_prompt=boolean))
    code=obj(dict(code_revision=text,dirty=boolean,source_hashes=scalar_map(sha),evaluator_sha256=sha))
    backend=obj(dict(database=text,postgresql=text,pgvector=text,cluster=text,transaction_read_only=boolean,
        migration_sha256=sha,migration_checksum=sha,catalog_sha256=sha,catalog_fingerprint=sha,
        role=text,role_review_required=boolean,scope=text,verification=text))
    file_entry=obj(dict(sha256=sha,count=integer),('sha256','count'))
    manifest=obj(dict(run_version=integer,run_id=text,started_at=text,finished_at=text,split={'const':'dev'},
        question_ids=arr(text),freeze_sha256=sha,benchmark_manifest_sha256=sha,
        frozen_files=obj({'dev.jsonl':file_entry,'test.jsonl':file_entry}),source_checksums=scalar_map(sha),
        profile_id=sha,embedding_config=profile,profile_config_sha256=sha,model_revision=text,dataset_id=text,
        snapshot_ids=arr(sha),manifest_sha256=sha,corpus_sha256=sha,descriptor_hashes=arr(sha),code=code,
        configuration=config,configuration_sha256=sha,backend_identity=backend,library_versions=scalar_map(text),
        test_approval=null,integrity_labels=arr(text),retrieval_seconds=number,elapsed_seconds=number,
        status=text,attempted=integer,succeeded=integer,retrieved=integer,failed=integer),('split','freeze_sha256'))
    manual_row=obj({k:nullable(text) for k in ('source_anchor','strategy','chunk_id','reviewer','rationale',
                                              'question_id','judgement','conclusion')}
                   | dict(label=nullable(integer),rank=integer,correct=nullable(boolean)))
    manual=obj({k:arr(manual_row) for k in ('coherence','retrieval_accuracy','metadata','grounding')}
               | dict(strategy_impact=manual_row))
    return obj(dict(status={'enum':['COMPLETE','INCOMPLETE']},manifest=manifest,receipts=arr(receipt),traces=arr(trace),
        summary=nullable(summary),error=nullable(obj(dict(type=text,sqlstate=nullable(text),stage=text,message=text))),
        manual_review=nullable(manual)),('status','manifest','receipts','traces','summary'))


def _validate_artifact(result):
    from jsonschema import Draft202012Validator
    errors=list(Draft202012Validator(_artifact_schema()).iter_errors(result))
    if errors:
        raise ValueError('Artifact schema/allowlist mismatch at '+str(list(errors[0].absolute_path)))
    canonical_json(result)  # Reject NaN/Infinity and non-JSON types.
    _reject_private_secrets(result)
    if result['status']=='INCOMPLETE':
        if result['summary'] is not None:
            raise ValueError('Incomplete run cannot publish quality summary')
        return
    manifest=result['manifest'];traces=result['traces'];receipts=result['receipts']
    required={'run_version','run_id','started_at','finished_at','question_ids','benchmark_manifest_sha256',
        'frozen_files','source_checksums','profile_id','embedding_config','profile_config_sha256','model_revision',
        'dataset_id','snapshot_ids','manifest_sha256','corpus_sha256','descriptor_hashes','code','configuration',
        'configuration_sha256','backend_identity','library_versions','integrity_labels','status',
        'attempted','succeeded','retrieved','failed'}
    if not required <= manifest.keys():
        raise ValueError('COMPLETE manifest missing run identities')
    ids=manifest.get('question_ids',[])
    if (len(ids)!=15 or len(set(ids))!=15 or len(traces)!=45 or len(receipts)!=15
            or canonical_json(manifest.get('configuration'))!=canonical_json(DEFAULT_CONFIG)
            or manifest.get('status')!='COMPLETE'
            or any(manifest.get(k)!=v for k,v in dict(attempted=45,succeeded=45,retrieved=45,failed=0).items())
            or result.get('error') is not None
            or {(t['question_id'],t['strategy']) for t in traces}!={(q,s) for q in ids for s in ('A','B','C')}
            or any(t['status']!='SUCCESS' for t in traces)):
        raise ValueError('COMPLETE run requires 15 unique dev questions and 45 successful A/B/C traces')
    if result['summary']!=summarize(traces):
        raise ValueError('COMPLETE summary differs from validated trace aggregation')
    profile=EmbeddingProfile.from_config(manifest.get('embedding_config',{}))
    if (profile.profile_id!=STAGE4_PROFILE or profile.profile_id!=manifest.get('profile_id')
            or profile.profile_id!=manifest.get('profile_config_sha256')
            or profile.config['revision']!=manifest.get('model_revision')
            or digest(manifest['configuration'])!=manifest.get('configuration_sha256')
            or manifest['snapshot_ids']!=list(STAGE4_SNAPSHOTS) or len(manifest['descriptor_hashes'])!=2
            or manifest['freeze_sha256']!=APPROVED_FREEZE or manifest['manifest_sha256']!=APPROVED_MANIFEST
            or manifest['source_checksums']!=APPROVED_SOURCES
            or manifest['frozen_files'].get('dev.jsonl',{}).get('count')!=15
            or manifest['frozen_files'].get('test.jsonl',{}).get('count')!=5
            or not manifest['code'].get('source_hashes')
            or digest(manifest['code']['source_hashes'])!=manifest['code'].get('evaluator_sha256')):
        raise ValueError('COMPLETE profile/config/snapshot identity mismatch')
    by_id={r['question_id']:r for r in receipts}
    if len(by_id)!=15 or set(by_id)!=set(ids):
        raise ValueError('COMPLETE receipt coverage mismatch')
    import hashlib
    for trace in traces:
        qid=trace['question_id'];strategy=trace['strategy'];receipt=by_id[qid]
        if (trace.get('query_receipt')!=receipt or receipt['producer_profile_id']!=profile.profile_id
                or receipt['dimensions']!=384 or receipt['dtype']!='float32' or receipt['query_prefix']!='query: '
                or not 1<=receipt['token_count']<=512
                or receipt['input_sha256']!=hashlib.sha256(('query: '+trace.get('question','')).encode()).hexdigest()
                or trace.get('snapshot_id')!=manifest['snapshot_ids'][0 if strategy=='A' else 1]
                or trace.get('integrity_labels')!=manifest.get('integrity_labels')
                or trace['evaluation']['question_id']!=qid or trace['evaluation']['split']!='dev'
                or len(trace['hits'])>3 or len(trace['evaluation']['diagnostics'])!=len(trace['hits'])):
            raise ValueError('COMPLETE trace/receipt/snapshot identity mismatch')
        for rank,hit in enumerate(trace['hits'],1):
            if (not set(HIT_FIELDS)<=hit.keys() or hit.get('rank')!=rank
                    or hit.get('dataset_id')!=manifest.get('dataset_id')
                    or hit.get('profile_id')!=profile.profile_id or hit.get('snapshot_id')!=trace['snapshot_id']
                    or hit.get('manifest_sha256')!=manifest.get('manifest_sha256')
                    or hit.get('corpus_sha256')!=manifest.get('corpus_sha256')
                    or hit.get('stored_strategy')!=('B' if strategy=='C' else strategy)
                    or hit.get('requested_strategy')!=strategy
                    or manifest.get('source_checksums',{}).get(hit.get('document_id'))!=hit.get('source_sha256')):
                raise ValueError('COMPLETE hit provenance mismatch')
        evaluation=trace['evaluation']
        for rank,(diagnostic,hit) in enumerate(zip(evaluation['diagnostics'],trace['hits'],strict=True),1):
            if (diagnostic['rank']!=rank or diagnostic['chunk_id']!=hit['chunk_id']
                    or any(a['exact_match']!=all(a['checks'].values()) for a in diagnostic['alternatives'])
                    or diagnostic['exact_match']!=any(a['exact_match'] for a in diagnostic['alternatives'])):
                raise ValueError('COMPLETE exact diagnostics mismatch')
        first=next((d['rank'] for d in evaluation['diagnostics'] if d['exact_match']),None)
        scope=trace.get('applied_filter')
        compliance=('NOT_APPLICABLE' if not scope or not trace['hits'] else
                    'VIOLATION' if any(h.get('section')!=scope['section'] for h in trace['hits']) else 'COMPLIANT')
        if (evaluation['first_exact_rank']!=first or evaluation['exact_hit_at_1']!=int(first==1)
                or evaluation['exact_evidence_hit_at_3']!=int(first is not None)
                or evaluation['mrr_at_3']!=(0.0 if first is None else 1/first)
                or evaluation['empty_result']!=(not trace['hits']) or evaluation['filter_applied']!=bool(scope)
                or evaluation['filter_compliance']!=compliance or (strategy!='C' and scope)
                or evaluation['metric_version']!=manifest['configuration']['metric_version']
                or evaluation['evidence_status']!=('EXACT_MATCH' if first else 'NO_EXACT_MATCH')):
            raise ValueError('COMPLETE exact metric/filter consistency mismatch')


def save_dev_artifacts(result,directory,*,root=ROOT):
    """Private raw and redacted export, bound by a final checksum manifest.

    A filesystem failure leaves an incomplete directory, never overwrites/retries.
    No manifest means the artifact bundle is not finalized.
    """
    if result.get('manifest',{}).get('split')!='dev':
        raise PermissionError('Only dev artifacts are accepted')
    if result.get('status')!='COMPLETE' and result.get('summary') is not None:
        raise ValueError('Incomplete run cannot publish quality summary')
    destination=stage5_path(root,directory,category='runs')
    if destination.exists(): raise FileExistsError('Artifact directory exists')
    raw=deepcopy(result)
    _validate_artifact(raw)
    for trace in raw.get('traces',[]):
        if trace.get('split')!='dev': raise ValueError('Mixed split traces forbidden')
        sha=trace_identity(trace)
        if any(trace.get(k,sha)!=sha for k in ('raw_trace_sha256','trace_sha256')):
            raise ValueError('Raw trace checksum mismatch')
        trace['raw_trace_sha256']=trace['trace_sha256']=sha
    destination.mkdir(parents=True,mode=0o700,exist_ok=False)
    private=destination/'private';private.mkdir(mode=0o700)
    _write_new(private/'raw_run.json',(canonical_json(raw)+'\n').encode())
    write_artifacts(raw,destination/'exported')
    files={name:file_sha(destination/name) for name in ('private/raw_run.json','exported/run.json')}
    manifest=dict(artifact_version=1,split='dev',status=raw['status'],files=files,
                  freeze_sha256=raw['manifest'].get('freeze_sha256'),
                  raw_contract='raw-trace-v1',export_contract='exported-trace-v1',
                  publication='LOCAL_ONLY_REQUIRES_REVIEW')
    _write_new(destination/'artifact_manifest.json',(canonical_json(manifest)+'\n').encode())
    return manifest


def verify_dev_artifacts(directory,*,root=ROOT):
    destination=stage5_path(root,directory,category='runs')
    manifest=json.loads(stage5_path(root,destination/'artifact_manifest.json',category='runs').read_text())
    expected={'private/raw_run.json','exported/run.json'}
    if manifest.get('artifact_version')!=1 or manifest.get('split')!='dev' or set(manifest['files'])!=expected:
        raise ValueError('Invalid artifact manifest')
    for name in expected:
        if file_sha(stage5_path(root,destination/name,category='runs'))!=manifest['files'][name]:
            raise ValueError('Artifact file checksum mismatch')
    raw=json.loads((destination/'private/raw_run.json').read_text())
    exported=json.loads((destination/'exported/run.json').read_text())
    _validate_artifact(raw)
    if (raw.get('manifest',{}).get('split')!='dev' or exported.get('manifest',{}).get('split')!='dev'
            or raw.get('status')!=manifest.get('status') or exported.get('status')!=raw.get('status')
            or raw['manifest'].get('freeze_sha256')!=manifest.get('freeze_sha256')
            or exported['manifest'].get('freeze_sha256')!=manifest.get('freeze_sha256')
            or any(t.get('split')!='dev' for t in raw['traces'])
            or (raw['status']!='COMPLETE' and (raw.get('summary') is not None or exported.get('summary') is not None))):
        raise ValueError('Artifact split/status/freeze identity mismatch')
    if len(raw['traces'])!=len(exported['traces']) or any(
            not verify_exported_trace(e,t) for t,e in zip(raw['traces'],exported['traces'],strict=True)):
        raise ValueError('Raw/exported trace identity mismatch')
    expected_export=redact(raw)
    expected_export['publication_redacted']=expected_export!=raw
    expected_export['traces']=[export_trace(t) for t in raw['traces']]
    expected_export['trace_export_contract']='exported-trace-v1'
    if expected_export!=exported:
        raise ValueError('Export does not match deterministic raw-run redaction')
    return manifest
