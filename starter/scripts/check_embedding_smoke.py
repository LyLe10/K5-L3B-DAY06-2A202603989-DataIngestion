"""Checkpoint 4.3A: bounded real-model smoke; PostgreSQL is read-only."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import mean
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from starter.src.corpus import load_manifest_pages
from starter.src.embeddings import CACHE, MODEL, MyEmbedder, validate_vector
from starter.src.preparation import audit_chunks, build_strategies


def database_snapshot():
    import psycopg
    from dotenv import load_dotenv
    load_dotenv(ROOT / 'starter/.env')
    with psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=5,
                         options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:
        with conn.cursor() as cursor:
            cursor.execute("""SELECT current_database(),current_setting('transaction_read_only'),
                (SELECT system_identifier::text FROM pg_control_system()),
                (SELECT count(*) FROM day6_ingestion.embedding_profiles),
                (SELECT count(*) FROM day6_ingestion.strategy_snapshots),
                (SELECT count(*) FROM day6_ingestion.chunks),
                day6_ingestion.catalog_fingerprint(),
                (SELECT jsonb_agg(to_jsonb(m) ORDER BY version) FROM day6_ingestion.schema_migrations m)""")
            row = cursor.fetchone()
            if row[:6] != ('day6_lab', 'on', '7707847059457269799', 0, 0, 0):
                raise RuntimeError('Unexpected database identity/counts; no embedding attempted')
        conn.rollback()
    return list(row)


def distribution(values):
    ordered = sorted(values)
    return dict(count=len(values), min=min(values), mean=mean(values), max=max(values),
                p95=ordered[math.ceil(.95*len(values))-1], over_512=sum(n>512 for n in values))


def main():
    report = dict(passed=False, started_at=datetime.now(timezone.utc).isoformat(),
                  corpus_fully_encoded=False, database_writes=False, errors=[])
    started = perf_counter()
    try:
        if CACHE.exists():
            raise RuntimeError('Smoke requires a new cache; existing cache is protected, not cleared')
        report['database_before'] = database_snapshot()
        corpus = load_manifest_pages(ROOT/'data/manifest.json')
        strategies = build_strategies(corpus.pages)
        report['baseline'] = dict(pages=len(corpus.pages), characters=sum(len(p.text) for p in corpus.pages),
                                  A=len(strategies['A']), B=len(strategies['B']), C_reuses_B=strategies['C'] is strategies['B'])
        for name in ['A','B']:
            saved = [json.loads(line) for line in (ROOT/f'data/local/stage3/chunks/{name}.jsonl').read_text().splitlines()]
            assert [asdict(c) for c in strategies[name]] == saved
            audit = audit_chunks(corpus.pages,strategies[name],name)
            assert not audit['errors'] and audit['covered_characters']==103371
        selected = {}
        for name in ['A','B']:
            selected[name] = [chunk for section in ['Data Definition','Data Manipulation']
                              for chunk in [c for c in strategies[name] if c.metadata['section']==section][:2]]
            assert len(selected[name])==4
        embedder = MyEmbedder(MODEL)
        report['profile_id'] = embedder.profile_id
        report['profile'] = embedder.profile.config
        report['runtime'] = embedder.runtime
        vectors = {}
        records = []
        for name in ['A','B']:
            before_tokens = len(embedder.stats['token_lengths'])
            vectors[name] = embedder.embed_documents([c.text for c in selected[name]])
            lengths = embedder.stats['token_lengths'][before_tokens:]
            for chunk,vector,tokens in zip(selected[name],vectors[name],lengths,strict=True):
                records.append(dict(strategy=name,chunk_id=chunk.chunk_id,physical_page=chunk.page,
                                    section=chunk.metadata['section'],token_length=tokens,
                                    input_sha256=hashlib.sha256(('passage: '+chunk.text).encode()).hexdigest(),
                                    dimension=len(vector),norm=math.sqrt(sum(x*x for x in vector))))
            report.setdefault('tokens',{})[name] = distribution(lengths)
        # C is the SAME list of B vectors, with no third embedding invocation.
        calls_before_c = embedder.stats['calls']
        vectors['C'] = vectors['B']
        report['C_reuses_B_vectors'] = vectors['C'] is vectors['B'] and embedder.stats['calls']==calls_before_c
        report['stats_after_documents'] = embedder.stats
        reordered = embedder.embed_documents([c.text for c in reversed(selected['A']+selected['B'])])
        assert reordered == list(reversed(vectors['A']+vectors['B']))
        report['cache_order_check'] = True
        report['stats_after_document_cache_replay'] = embedder.stats
        question = 'How does PostgreSQL insert rows into a table?'
        query = embedder.embed_query(question)
        assert query == embedder.embed_query(question)
        report['query'] = dict(token_length=embedder.stats['token_lengths'][-1],dimension=len(query),
                               norm=math.sqrt(sum(x*x for x in query)),cache_replay_equal=True)
        # Independent single-item model encodes check actual batch ordering/numerics.
        # These TWO reference inputs are counted explicitly, never a corpus encode.
        started_reference = perf_counter()
        differences = []
        for name in ['A','B']:
            reference = embedder._model.encode(['passage: '+selected[name][0].text],batch_size=1,
                        normalize_embeddings=True,precision='float32',device='cpu',prompt='',
                        show_progress_bar=False,convert_to_numpy=True)
            reference = validate_vector(reference[0])
            error = max(abs(a-b) for a,b in zip(reference,vectors[name][0],strict=True))
            assert error < 1e-5
            differences.append(error)
        report['real_batch_order_reference'] = dict(encoded_inputs=2,max_abs_differences=differences,
                                                    encode_seconds=perf_counter()-started_reference)
        report['smoke_records'] = records
        report['stats'] = embedder.stats
        report['document_token_distribution'] = distribution([r['token_length'] for r in records])
        report['total_model_encoded_inputs_including_references'] = embedder.stats['encoded_inputs']+2
        report['cache_entries'] = len(list((CACHE/embedder.profile_id).glob('*.json')))
        report['cache_bytes'] = sum(p.stat().st_size for p in (CACHE/embedder.profile_id).glob('*.json'))
        report['database_after'] = database_snapshot()
        assert report['database_after']==report['database_before']
        report['database_unchanged'] = True
        report['passed'] = True
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
        # No re-encode, cache cleanup/repair, dependency change or DB mutation.
    report['total_seconds'] = perf_counter()-started
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    (ROOT/'results/embedding_implementation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
