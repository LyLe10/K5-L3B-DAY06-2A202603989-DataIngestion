"""Exact evidence metrics, never answer accuracy or automatic human judgement."""
from copy import deepcopy
import hashlib
from typing import Any
from .schema import canonical_json

METRIC_VERSION = 'exact-evidence-v1'

def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()

def trace_identity(trace):
    """SHA256 UTF-8 canonical JSON, raw-trace-v1 domain, excluding own aliases."""
    return digest(dict(hash_contract='raw-trace-v1',payload={k:v for k,v in trace.items()
                   if k not in ('trace_sha256','raw_trace_sha256')}))

def validate_hits(hits, pages, sources):
    """Bind returned chunks to independent normalized source text."""
    for hit in hits:
        page = pages[(hit['document_id'], hit['physical_page'])]
        start, end = hit['start_char'], hit['end_char']
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(page.text)
                or hit['text'] != page.text[start:end]
                or hit['text_sha256'] != hashlib.sha256(hit['text'].encode()).hexdigest()
                or hit['page_text_sha256'] != page.metadata['text_sha256']
                or hit['source_sha256'] != sources[page.document_id]['sha256']
                or hit['source'] != page.source or hit['section'] != page.metadata['section']
                or hit['metadata'].get('source_id') != page.document_id
                or hit['metadata'].get('physical_page') != page.page
                or hit['metadata'].get('section') != hit['section']):
            raise ValueError('Returned chunk differs from independent source text/provenance')

def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """One whole gold span in ONE chunk. Caller verifies source via validate_hits."""
    if len(hits) > 3 or len({h['chunk_id'] for h in hits}) != len(hits):
        raise ValueError('Expected at most three unique hits')
    golds = [question, *question.get('gold_alternatives', [])]
    diagnostics = []
    for rank, hit in enumerate(hits, 1):
        if hit['rank'] != rank:
            raise ValueError('Invalid retrieval rank order')
        matches = []
        for index, gold in enumerate(golds):
            start, end = gold['evidence_start_char'], gold['evidence_end_char']
            covered = hit['start_char'] <= start < end <= hit['end_char']
            consistent = (hit['end_char']-hit['start_char'] == len(hit['text'])
                          and hashlib.sha256(hit['text'].encode()).hexdigest() == hit['text_sha256'])
            checks = dict(source=hit['document_id'] == gold['gold_source_id'],
                          page=hit['physical_page'] == gold['gold_page'],
                          source_checksum=hit['source_sha256'] == gold['source_sha256'],
                          page_checksum=hit['page_text_sha256'] == gold['page_text_sha256'],
                          span_coverage=covered, text_consistency=consistent,
                          quote=(covered and end-start == len(gold['evidence_quote'])
                                 and hit['text'][start-hit['start_char']:end-hit['start_char']] == gold['evidence_quote']))
            matches.append(dict(gold_index=index, checks=checks, exact_match=all(checks.values())))
        diagnostics.append(dict(rank=rank, chunk_id=hit['chunk_id'], alternatives=matches,
                                exact_match=any(m['exact_match'] for m in matches)))
    first = next((d['rank'] for d in diagnostics if d['exact_match']), None)
    scope = question.get('filter')
    compliance = ('NOT_APPLICABLE' if not scope or not hits else
                  'VIOLATION' if any(h['section'] != scope['section'] for h in hits) else 'COMPLIANT')
    return dict(question_id=question['id'], split=question['split'], metric_version=METRIC_VERSION,
                exact_hit_at_1=int(first == 1), exact_evidence_hit_at_3=int(first is not None),
                mrr_at_3=0.0 if first is None else 1/first, first_exact_rank=first,
                evidence_status='EXACT_MATCH' if first else 'NO_EXACT_MATCH', diagnostics=diagnostics,
                empty_result=not hits, filter_applied=bool(scope), filter_compliance=compliance)

def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Completed unique records only; runner separately enforces full split coverage."""
    seen, groups = set(), {}
    for trace in traces:
        key = (trace['split'], trace['strategy'], trace['question_id'])
        if key in seen or trace.get('status') != 'SUCCESS':
            raise ValueError('Cannot summarize duplicate or failed retrieval records')
        seen.add(key)
        groups.setdefault(key[:2], []).append(trace['evaluation'])
    output = []
    for (split, strategy), rows in sorted(groups.items()):
        n = len(rows)
        filtered = [r for r in rows if r['filter_applied']]
        nonempty = [r for r in filtered if not r['empty_result']]
        compliant = sum(r['filter_compliance'] == 'COMPLIANT' for r in nonempty)
        output.append(dict(split=split, strategy=strategy, questions=n,
            exact_hit_at_1=dict(numerator=sum(r['exact_hit_at_1'] for r in rows), denominator=n,
                               rate=sum(r['exact_hit_at_1'] for r in rows)/n),
            exact_evidence_hit_at_3=dict(numerator=sum(r['exact_evidence_hit_at_3'] for r in rows), denominator=n,
                                       rate=sum(r['exact_evidence_hit_at_3'] for r in rows)/n),
            mrr_at_3=sum(r['mrr_at_3'] for r in rows)/n,
            empty_results=dict(count=sum(r['empty_result'] for r in rows), denominator=n,
                               rate=sum(r['empty_result'] for r in rows)/n),
            filter_diagnostics=dict(filtered_questions=len(filtered),
                empty_count=sum(r['empty_result'] for r in filtered),
                empty_rate=None if not filtered else sum(r['empty_result'] for r in filtered)/len(filtered),
                nonempty_denominator=len(nonempty), compliant=compliant,
                violations=sum(r['filter_compliance']=='VIOLATION' for r in nonempty),
                compliance=None if not nonempty else compliant/len(nonempty))))
    return dict(metric_version=METRIC_VERSION, groups=output)

def adjudicate(traces, decisions):
    """Explicit manual overrides returned separately, never changes exact traces/gold."""
    summarize(traces)  # Validate status and unique records without changing exact metrics.
    copies = deepcopy(traces)
    by_hash = {trace_identity(t): t for t in copies}
    if any(t.get(k,trace_identity(t))!=trace_identity(t) for t in copies
           for k in ('trace_sha256','raw_trace_sha256')):
        raise ValueError('Exact trace checksum mismatch')
    seen = set()
    for decision in decisions:
        for field in ('reviewer','rationale','trace_sha256'):
            if not isinstance(decision.get(field), str) or not decision[field].strip():
                raise ValueError('Explicit reviewer/rationale/trace identity required')
        trace = by_hash.get(decision['trace_sha256'])
        rank = decision.get('rank')
        if trace is None or type(rank) is not int or not 1 <= rank <= len(trace['hits']):
            raise ValueError('Adjudication does not bind an existing hit')
        key = (decision['trace_sha256'], rank)
        if key in seen or type(decision.get('relevant')) is not bool:
            raise ValueError('Duplicate or invalid adjudication')
        seen.add(key)
        trace['evaluation']['diagnostics'][rank-1]['adjudicated_relevant'] = decision['relevant']
    groups, diagnostics = {}, []
    for raw_hash, trace in by_hash.items():
        e = trace['evaluation']
        first = next((d['rank'] for d in e['diagnostics']
                      if d.get('adjudicated_relevant',d['exact_match'])),None)
        groups.setdefault((trace['split'],trace['strategy']),[]).append(
            (int(first==1),int(first is not None),0.0 if first is None else 1/first))
        diagnostics.append(dict(raw_trace_sha256=raw_hash,ranks=deepcopy(e['diagnostics'])))
    metrics=[]
    for (split,strategy), rows in sorted(groups.items()):
        n=len(rows)
        metrics.append(dict(split=split,strategy=strategy,questions=n,
            adjudicated_hit_at_1=dict(numerator=sum(r[0] for r in rows),denominator=n,rate=sum(r[0] for r in rows)/n),
            adjudicated_evidence_hit_at_3=dict(numerator=sum(r[1] for r in rows),denominator=n,rate=sum(r[1] for r in rows)/n),
            adjudicated_mrr_at_3=sum(r[2] for r in rows)/n))
    return dict(adjudication_version=1, decisions=deepcopy(decisions),diagnostics=diagnostics,
                metrics=dict(metric_version='manual-adjudicated-evidence-v1',groups=metrics))

def manual_review_template(question_ids):
    """Blank human labels only. Source anchors require later approval."""
    return dict(coherence=[dict(source_anchor=None, strategy=s, chunk_id=None, label=None,
                                reviewer=None, rationale=None) for _ in range(10) for s in ('A','B','C')],
        retrieval_accuracy=[dict(question_id=q,strategy=s,reviewer=None,rationale=None,judgement=None)
                            for q in question_ids for s in ('A','B','C')],
        metadata=[dict(question_id=q,strategy=s,rank=r,correct=None,reviewer=None,rationale=None)
                  for q in question_ids for s in ('A','B','C') for r in (1,2,3)],
        grounding=[dict(question_id=q,strategy=s,label=None,reviewer=None,rationale=None)
                   for q in question_ids for s in ('A','B','C')],
        strategy_impact=dict(reviewer=None,rationale=None,conclusion=None))
