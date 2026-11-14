"""Split-gated evaluation orchestration. All backends are explicitly supplied.

Importing this module never loads a model, connects a database or runs a benchmark.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import hashlib
import json
import math
import re
import subprocess
import time
import uuid

from .benchmark import validate_benchmark
from .corpus import ROOT, load_manifest_pages
from .embeddings import validate_vector
from .evaluation import (METRIC_VERSION, digest, evaluate_query, summarize,
                         validate_hits, manual_review_template, trace_identity)
from .schema import EmbeddingProfile, canonical_json

DEFAULT_CONFIG = dict(config_version=1,top_k=3,strategies=['A','B','C'],deadline_seconds=120,
                      metric_version=METRIC_VERSION,filter_empty_policy='NOT_APPLICABLE',selected_strategy=None)
IDENTITY_FILES = ('starter/src/evaluation.py','starter/src/evaluation_runner.py',
                  'starter/src/retrieval.py','starter/src/store.py','starter/src/embeddings.py',
                  'starter/src/benchmark.py','starter/scripts/run_evaluation.py')

def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate_config(config):
    if (set(config)!=set(DEFAULT_CONFIG) or config['config_version']!=1 or type(config['config_version']) is not int
            or config['top_k']!=3 or type(config['top_k']) is not int
            or config['strategies']!=['A','B','C'] or config['metric_version']!=METRIC_VERSION
            or config['filter_empty_policy']!='NOT_APPLICABLE'
            or config['selected_strategy'] not in (None,'A','B','C')
            or isinstance(config['deadline_seconds'],bool)
            or not isinstance(config['deadline_seconds'],(int,float))
            or not math.isfinite(config['deadline_seconds']) or config['deadline_seconds']<=0):
        raise ValueError('Unsupported evaluation configuration')

def evaluator_identity(root=ROOT):
    """Hashes bind dirty code as well as committed code; no credentials or paths."""
    root=Path(root)
    files={name:file_sha(root/name) for name in IDENTITY_FILES}
    cmd=['git','--no-optional-locks','-c','safe.directory='+root.as_posix(),'-C',str(root)]
    head=subprocess.check_output(cmd+['rev-parse','HEAD'],text=True).strip()
    dirty=bool(subprocess.check_output(cmd+['status','--porcelain','--untracked-files=normal']))
    return dict(code_revision=head,dirty=dirty,source_hashes=files,evaluator_sha256=digest(files))

def approval_gate(split,approval,freeze_hash,evaluator_hash,config):
    """Validate self-declared metadata only. This is NOT authorization."""
    if split not in ('dev','test'):
        raise ValueError('Run exactly one split: dev or test')
    validate_config(config)
    if split=='dev': return
    required=dict(approval_version=1,approved=True,split='test',freeze_sha256=freeze_hash,
                  evaluator_sha256=evaluator_hash,config_sha256=digest(config))
    if (not isinstance(approval,dict) or any(approval.get(k)!=v for k,v in required.items())
            or approval.get('approved') is not True or type(approval.get('approval_version')) is not int
            or config['selected_strategy'] not in ('A','B','C')
            or approval.get('selected_strategy') != config['selected_strategy']
            or not isinstance(approval.get('reviewer'),str) or not approval['reviewer'].strip()
            or not isinstance(approval.get('rationale'),str) or not approval['rationale'].strip()):
        raise ValueError('A separately reviewed, identity-bound test approval artifact is required')


def authorize_test_execution(split):
    """Fail closed: no independent approval authority/trust root is configured.

    Deliberately no boolean, callback or locally minted token can unlock test.
    A future independently verified approval integration needs explicit review.
    """
    if split=='test':
        raise PermissionError('TEST_EXECUTION_BLOCKED: independent approval verification is not configured')

def load_benchmark(directory,split,*,config,identity,approval=None,root=ROOT,corpus=None):
    """Validates both frozen files, but only returns the selected split to execution."""
    directory=Path(directory)
    corpus=corpus if corpus is not None else load_manifest_pages(Path(root)/'data/manifest.json',root=root)
    checked=validate_benchmark(directory,root=root,corpus=corpus)
    if not checked['frozen'] or not checked['human_approved'] or not checked['structural_source_valid']:
        raise ValueError('Only a validated approved frozen benchmark can execute')
    freeze_hash=file_sha(directory/'freeze_manifest.json')
    approval_gate(split,approval,freeze_hash,identity['evaluator_sha256'],config)
    data=(directory/(split+'.jsonl')).read_bytes()
    records=[json.loads(line) for line in data.decode().splitlines() if line.strip()]
    expected=15 if split=='dev' else 5
    if len(records)!=expected or any(q['split']!=split for q in records):
        raise ValueError('Split isolation/count mismatch')
    manifest=json.loads((directory/'manifest.json').read_text())
    return dict(split=split,questions=records,corpus=corpus,freeze_sha256=freeze_hash,
                questions_sha256=digest(records),
                benchmark_manifest_sha256=file_sha(directory/'manifest.json'),
                frozen_files=manifest['files'],approval=approval,
                source_checksums={s['source_id']:s['sha256'] for s in corpus.sources})

class QueryProducer:
    """Stage 5 wrapper around the unchanged Stage 4 adapter; never prefixes twice."""
    def __init__(self,adapter,expected_profile,cache_root=ROOT/'data/local/stage5/embedding_cache'):
        self.adapter=adapter
        self.profile=EmbeddingProfile(expected_profile.config_canonical)
        if (adapter.profile_id!=self.profile.profile_id
                or adapter.profile.config_canonical!=self.profile.config_canonical
                or adapter._cache_dir.resolve()!=Path(cache_root).resolve()):
            raise ValueError('Producer profile or separate Stage 5 cache mismatch')
        c=self.profile.config
        if c['query_prefix']!='query: ' or c['max_seq_length']!=512:
            raise ValueError('Producer query contract mismatch')

    def prepare(self,questions):
        vectors,receipts=[],[]
        for q in questions:
            text=q['question']
            if not isinstance(text,str) or not text.strip() or '\x00' in text:
                raise ValueError('Invalid raw query')
            before=self.adapter.stats
            started=time.perf_counter()
            vector=validate_vector(self.adapter.embed_query(text))
            after=self.adapter.stats
            lengths=after['token_lengths'][len(before['token_lengths']):]
            if (len(lengths)!=1 or type(lengths[0]) is not int or not 1<=lengths[0]<=512
                    or self.adapter.profile_id!=self.profile.profile_id
                    or self.adapter.profile.config_canonical!=self.profile.config_canonical):
                raise ValueError('Missing/mismatched producer token/profile receipt')
            receipt=dict(question_id=q['id'],producer_profile_id=self.profile.profile_id,
                         input_sha256=hashlib.sha256(('query: '+text).encode()).hexdigest(),
                         vector_sha256=digest(vector),token_count=lengths[0],dimensions=384,
                         query_prefix='query: ',dtype='float32',
                         cache_hits=after['cache_hits']-before['cache_hits'],
                         encoded_inputs=after['encoded_inputs']-before['encoded_inputs'],
                         elapsed_seconds=time.perf_counter()-started)
            vectors.append(vector);receipts.append(receipt)
        return vectors,receipts

# Explicit fields only: no arbitrary backend payload, embeddings, DSN or exceptions.
HIT_FIELDS=('rank','chunk_id','document_id','source','physical_page','printed_page_label','section',
            'start_char','end_char','text','metadata','snapshot_id','manifest_sha256','corpus_sha256',
            'source_sha256','page_text_sha256','text_sha256','page_id','cosine_distance','score',
            'dataset_id','profile_id','requested_strategy','stored_strategy')

def safe_hit(hit):
    out={k:hit[k] for k in HIT_FIELDS if k in hit}
    metadata=hit.get('metadata',{})
    allowed=('source_id','physical_page','page_id','printed_page_label','section','section_evidence',
             'version','normalized_char_count','text_sha256','extraction_status','_chunking')
    out['metadata']={k:metadata[k] for k in allowed if k in metadata}
    if '_chunking' in out['metadata']:
        out['metadata']['_chunking']={k:v for k,v in metadata['_chunking'].items()
            if k in ('strategy','algorithm_version','unit','parameters','start_char','end_char','split_sql_statement')}
    return out

def dependency_versions():
    out={}
    for name in ('torch','sentence-transformers','transformers','tokenizers','psycopg','pgvector','pypdf'):
        try: out[name]=version(name)
        except PackageNotFoundError: out[name]='NOT_INSTALLED'
    return out

def run_evaluation(bundle,*,store,producer,baseline,config,identity,backend_identity,output_directory=None):
    """Explicit backend invocation. Tests supply synthetic doubles only.

    Failures return INCOMPLETE with partial traces; no metrics, retry or fallback.
    An explicit new output directory persists even INCOMPLETE run evidence.
    """
    validate_config(config)
    if output_directory is not None and Path(output_directory).exists():
        raise FileExistsError('Run artifact directory already exists; never overwrite')
    approval_gate(bundle['split'],bundle.get('approval'),bundle['freeze_sha256'],identity['evaluator_sha256'],config)
    authorize_test_execution(bundle['split'])
    questions=bundle['questions']
    if (len(questions)!=(15 if bundle['split']=='dev' else 5)
            or bundle['questions_sha256']!=digest(questions)
            or len({q['id'] for q in questions})!=len(questions)
            or any(q['split']!=bundle['split'] for q in questions)):
        raise ValueError('Invalid split execution bundle')
    if (producer.profile.profile_id!=store.profile_id or baseline.profile_id!=store.profile_id
            or baseline.dataset_id!=store.dataset_id):
        raise ValueError('Producer/store/baseline profile namespace mismatch')
    baseline.validate_approved_identity()
    result=dict(status='INCOMPLETE',manifest=dict(run_version=1,run_id=uuid.uuid4().hex,
        started_at=datetime.now(timezone.utc).isoformat(),split=bundle['split'],
        question_ids=[q['id'] for q in questions],freeze_sha256=bundle['freeze_sha256'],
        benchmark_manifest_sha256=bundle['benchmark_manifest_sha256'],frozen_files=bundle['frozen_files'],
        source_checksums=bundle['source_checksums'],profile_id=store.profile_id,
        embedding_config=producer.profile.config,
        profile_config_sha256=digest(producer.profile.config),model_revision=producer.profile.config['revision'],
        dataset_id=store.dataset_id,snapshot_ids=[s.snapshot_id for s in baseline.snapshots],
        manifest_sha256=baseline.snapshots[0].manifest_sha256,corpus_sha256=baseline.snapshots[0].corpus_sha256,
        descriptor_hashes=list(baseline.descriptor_hashes),code=identity,configuration=config,
        configuration_sha256=digest(config),backend_identity=backend_identity,
        library_versions=dependency_versions(),test_approval=bundle.get('approval')),
        receipts=[],traces=[],summary=None,error=None,manual_review=None)
    started=time.perf_counter()
    stage='QUERY_EMBEDDING'
    try:
        # Gold never reaches embedding or retrieval components.
        retrieval_inputs=[dict(id=q['id'],question=q['question'],filter=q.get('filter')) for q in questions]
        vectors,receipts=producer.prepare(retrieval_inputs)
        if len(vectors)!=len(questions) or len(receipts)!=len(questions):
            raise ValueError('Producer receipt count mismatch')
        for q,v,r in zip(questions,vectors,receipts,strict=True):
            validate_vector(v)
            if (r['question_id']!=q['id'] or r['producer_profile_id']!=store.profile_id
                    or r['input_sha256']!=hashlib.sha256(('query: '+q['question']).encode()).hexdigest()
                    or r['vector_sha256']!=digest(v) or not 1<=r['token_count']<=512):
                raise ValueError('Producer receipt identity/order mismatch')
        result['receipts']=receipts
        stage='RETRIEVAL'
        retrieval_started=time.perf_counter()
        with store.retrieval_session(baseline=baseline,deadline_seconds=config['deadline_seconds']) as session:
            result['manifest']['integrity_labels']=list(session.integrity)
            if tuple(s.snapshot_id for s in session.snapshots)!=tuple(s.snapshot_id for s in baseline.snapshots):
                raise ValueError('Session snapshot mismatch')
            for q,vector,receipt in zip(questions,vectors,receipts,strict=True):
                for strategy in config['strategies']:
                    if time.perf_counter()-retrieval_started>=config['deadline_seconds']:
                        raise TimeoutError('Total retrieval deadline exceeded')
                    trace=dict(question_id=q['id'],split=q['split'],strategy=strategy,
                        question=q['question'],query_receipt=receipt,status='STARTED',hits=[],
                        applied_filter=q.get('filter') if strategy=='C' else None,
                        snapshot_id=baseline.snapshots[0 if strategy=='A' else 1].snapshot_id,
                        integrity_labels=list(session.integrity))
                    result['traces'].append(trace)
                    call_started=time.perf_counter()
                    hits=session.search(strategy,vector,top_k=3,filters=trace['applied_filter'])
                    trace.update(status='RETRIEVED',hits=[safe_hit(h) for h in hits],
                                 retrieval_seconds=time.perf_counter()-call_started)
        result['manifest']['retrieval_seconds']=time.perf_counter()-retrieval_started
        stage='EVALUATION'
        # Source verification and scoring happen AFTER transaction/locks close.
        pages={(p.document_id,p.page):p for p in bundle['corpus'].pages}
        sources={s['source_id']:s for s in bundle['corpus'].sources}
        by_id={q['id']:q for q in questions}
        for trace in result['traces']:
            for hit in trace['hits']:
                if (hit['dataset_id']!=store.dataset_id or hit['profile_id']!=store.profile_id
                        or hit['snapshot_id']!=trace['snapshot_id']
                        or hit['stored_strategy']!=('B' if trace['strategy']=='C' else trace['strategy'])
                        or not math.isfinite(hit['cosine_distance']) or not math.isfinite(hit['score'])
                        or abs(hit['score']-(1-hit['cosine_distance']))>1e-7):
                    raise ValueError('Hit namespace/snapshot/score mismatch')
            if [(h['cosine_distance'],h['chunk_id']) for h in trace['hits']]!=sorted(
                    (h['cosine_distance'],h['chunk_id']) for h in trace['hits']):
                raise ValueError('Hit ordering mismatch')
            validate_hits(trace['hits'],pages,sources)
            q=dict(by_id[trace['question_id']])
            if trace['strategy']!='C': q.pop('filter',None)
            trace.update(status='SUCCESS',evaluation=evaluate_query(q,trace['hits']))
            trace['raw_trace_sha256']=trace_identity(trace)
            trace['trace_sha256']=trace['raw_trace_sha256']  # legacy alias, not export identity
        if len(result['traces'])!=len(questions)*3:
            raise ValueError('Incomplete strategy/question coverage')
        result.update(status='COMPLETE',summary=summarize(result['traces']),
                      manual_review=manual_review_template([q['id'] for q in questions] if bundle['split']=='test' else []))
    except Exception as exc:
        # Exception text can contain passwords/DSNs, SQL or personal paths. Never export it.
        result['error']=dict(type=type(exc).__name__,sqlstate=getattr(exc,'sqlstate',None),
                             stage=stage,message='RUN_FAILED_NO_RETRY')
        if result['traces'] and result['traces'][-1]['status']=='STARTED':
            result['traces'][-1]['status']='FAILED'
        result['summary']=None
    result['manifest'].update(finished_at=datetime.now(timezone.utc).isoformat(),
                              elapsed_seconds=time.perf_counter()-started,status=result['status'],
                              attempted=len(result['traces']),succeeded=sum(t['status']=='SUCCESS' for t in result['traces']),
                              retrieved=sum(t['status'] in ('RETRIEVED','SUCCESS') for t in result['traces']),
                              failed=sum(t['status']=='FAILED' for t in result['traces']))
    if output_directory is not None:
        write_artifacts(result,output_directory)
    return result

def redact(value):
    """Publication-only redaction; exact in-memory metrics and gold stay unchanged."""
    if isinstance(value,dict):
        return {k:('[REDACTED]' if any(w in k.lower() for w in ('password','secret','credential','api_key','authorization','database_url'))
                   or k.lower().endswith('_token') else redact(v))
                for k,v in value.items() if k.lower() not in ('vector','vectors','embedding','embeddings')}
    if isinstance(value,list): return [redact(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'\b(?:postgres(?:ql)?|https?)://[^\s/@]+:[^\s/@]+@', '[REDACTED_CREDENTIAL_URL]@',value)
        value=re.sub(r'(?i)\bBearer\s+\S+', 'Bearer [REDACTED]',value)
        value=re.sub(r'(?i)\b(password|api_key|access_token|secret)\s*[=:]\s*[^\s,;]+', r'\1=[REDACTED]',value)
        if re.search(r'-----BEGIN .*PRIVATE KEY-----|(?:[A-Za-z]:[\\/]|/mnt/[a-z]/|/home/|/Users/)',value):
            return '[REDACTED_LOCAL_OR_KEY_MATERIAL]'
        return value
    return value

def exported_trace_identity(trace):
    return digest({k:v for k,v in trace.items() if k!='exported_trace_sha256'})


def export_trace(raw):
    raw_hash=trace_identity(raw)
    if any(raw.get(k,raw_hash)!=raw_hash for k in ('raw_trace_sha256','trace_sha256')):
        raise ValueError('Raw trace identity mismatch')
    exported=redact({k:v for k,v in raw.items() if k not in ('raw_trace_sha256','trace_sha256')})
    exported.update(hash_contract='exported-trace-v1',raw_trace_sha256=raw_hash)
    exported['exported_trace_sha256']=exported_trace_identity(exported)
    return exported


def verify_exported_trace(exported,raw_trace=None):
    """Without raw: verifies exported bytes only, not truth or raw equivalence."""
    valid=(exported.get('hash_contract')=='exported-trace-v1'
           and exported.get('exported_trace_sha256')==exported_trace_identity(exported))
    if raw_trace is not None:
        valid=valid and export_trace(raw_trace)==exported
    return valid


def write_artifacts(result,directory):
    """New directory only; no overwrites. Full text stays local pending publication review."""
    path=Path(directory)
    safe=redact(result)
    safe['publication_redacted']=safe!=result
    safe['traces']=[export_trace(t) for t in result.get('traces',[])]
    safe['trace_export_contract']='exported-trace-v1'
    path.mkdir(parents=True,exist_ok=False)
    (path/'run.json').write_text(json.dumps(safe,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
