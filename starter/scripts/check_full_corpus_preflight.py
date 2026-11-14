"""CP4.3C-1: real full-corpus embeddings; no database mutation."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import resource
from statistics import mean
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from starter.src.corpus import load_manifest_pages
from starter.src.embeddings import CACHE, MODEL, MyEmbedder, validate_vector
from starter.src.preparation import audit_chunks, build_strategies
from starter.src.schema import Namespace, require_compatible
from starter.src.store import PgVectorStore, SnapshotContext
from starter.scripts.check_embedding_smoke import database_snapshot, distribution

PROFILE = '528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = perf_counter()
    report = dict(passed=False, started_at=datetime.now(timezone.utc).isoformat(),
                  database_writes=False, errors=[])
    output = ROOT/'results/full_corpus_embedding_preflight.json'
    if output.exists():
        raise RuntimeError('Evidence already exists; do not overwrite or retry automatically')
    cache_dir = CACHE/PROFILE
    cache_before = {p.name: sha(p) for p in sorted(cache_dir.glob('*.json'))}
    report['cache_before'] = cache_before
    try:
        print('Checking read-only database and corpus', flush=True)
        report['database_before'] = database_snapshot()
        corpus = load_manifest_pages(ROOT/'data/manifest.json')
        strategies = build_strategies(corpus.pages)
        assert len(corpus.pages) == 40 and sum(len(p.text) for p in corpus.pages) == 103371
        assert len(strategies['A']) == 246 and len(strategies['B']) == 264
        assert strategies['C'] is strategies['B']
        report['baseline'] = dict(pages=40, characters=103371, A=246, B=264, C_reuses_B=True,
                                  physical_pages=[p.page for p in corpus.pages], sources=corpus.sources,
                                  manifest_sha256=corpus.manifest_sha256, skipped_pages=corpus.skipped_pages)
        for name in ('A', 'B'):
            saved = [json.loads(line) for line in (ROOT/f'data/local/stage3/chunks/{name}.jsonl').read_text().splitlines()]
            assert [asdict(c) for c in strategies[name]] == saved
            audit = audit_chunks(corpus.pages, strategies[name], name)
            assert not audit['errors'] and audit['covered_characters'] == 103371
            report.setdefault('coverage', {})[name] = audit
        context = SnapshotContext.from_ingestion_result(corpus)
        print('Loading pinned real model offline', flush=True)
        embedder = MyEmbedder(MODEL)
        assert embedder.profile_id == PROFILE
        report.update(profile_id=PROFILE, profile=embedder.profile.config, runtime=embedder.runtime)
        store = PgVectorStore(os.environ['DATABASE_URL'], 384, dataset_id='day06-postgresql',
                              profile_id=PROFILE, profile=embedder.profile, context=context)
        store.create_schema()  # This API only verifies the existing registry using SELECT.
        all_chunks = strategies['A'] + strategies['B']
        tokenized = embedder._model.tokenizer(['passage: '+c.text for c in all_chunks],
                       add_special_tokens=True, truncation=False, padding=False, return_length=True)
        lengths = tokenized['length']
        assert len(lengths) == 510
        overflow = [dict(chunk_id=c.chunk_id, page=c.page, tokens=int(n))
                    for c, n in zip(all_chunks, lengths, strict=True) if n > 512]
        report['overflow'] = overflow
        if overflow:
            raise RuntimeError('Token overflow; no corpus encoding attempted')
        report['tokens'] = dict(all=distribution(lengths), A=distribution(lengths[:246]),
                               B=distribution(lengths[246:]))
        snapshots, receipts, vectors = {}, [], {}
        for name in ('A', 'B'):
            print(f'Encoding {name}: {len(strategies[name])} inputs', flush=True)
            before = embedder.stats
            t = perf_counter()
            chunks = strategies[name]
            vectors[name] = embedder.embed_documents([c.text for c in chunks])
            ids = [c.chunk_id for c in chunks]
            pairs = store.validate_batch(name, chunks, vectors[name], vector_chunk_ids=ids,
                                        embedding_profile_id=PROFILE)
            snapshot, rows, ledger = store._prepare_snapshot(Namespace('day06-postgresql', PROFILE, name), context, pairs)
            snapshots[name] = snapshot
            report.setdefault('planned_snapshots', {})[name] = dict(snapshot_id=snapshot.snapshot_id,
                corpus_sha256=snapshot.corpus_sha256, chunkset_sha256=snapshot.chunkset_sha256,
                expected_count=snapshot.expected_count, namespace=snapshot.namespace.parameters,
                advisory_lock_key=snapshot.namespace.lock_key, persisted=False)
            norms = []
            for c, v in pairs:
                key = hashlib.sha256(('passage: '+c.text).encode()).hexdigest()
                cached = json.loads((cache_dir/(key+'.json')).read_text())
                assert validate_vector(v) == cached['vector']
                assert rows[c.chunk_id][-1] == v
                norm = math.sqrt(sum(x*x for x in v))
                assert len(v) == 384 and all(math.isfinite(x) for x in v) and abs(norm-1) <= 1e-5
                norms.append(norm)
                receipts.append(dict(strategy=name, position=len(receipts), chunk_id=c.chunk_id,
                    document_id=c.document_id, physical_page=c.page, section=c.metadata['section'],
                    start_char=c.metadata['_chunking']['start_char'], end_char=c.metadata['_chunking']['end_char'],
                    input_sha256=key, vector_sha256=cached['vector_sha256'],
                    token_length=int(lengths[len(receipts)]), dimension=len(v), norm=norm))
            after = embedder.stats
            report.setdefault('encoding', {})[name] = dict(wall_seconds=perf_counter()-t,
                encode_seconds=after['encode_seconds']-before['encode_seconds'],
                cache_hits=after['cache_hits']-before['cache_hits'],
                encoded_inputs=after['encoded_inputs']-before['encoded_inputs'],
                encode_batches=after['encode_batches']-before['encode_batches'],
                norm_min=min(norms), norm_max=max(norms))
        require_compatible(snapshots['A'], snapshots['B'])
        vectors['C'] = vectors['B']
        assert vectors['C'] is vectors['B'] and embedder.stats['calls'] == 2
        report['stats'] = embedder.stats
        report['receipts'] = receipts
        report['receipt_order_verified'] = [r['chunk_id'] for r in receipts] == [c.chunk_id for c in all_chunks]
        assert report['receipt_order_verified']
        assert all(sha(cache_dir/name) == checksum for name, checksum in cache_before.items())
        report['existing_cache_unchanged'] = True
        cache_after = sorted(cache_dir.glob('*.json'))
        report['new_cache_paths'] = [(p.relative_to(ROOT).as_posix()) for p in cache_after if p.name not in cache_before]
        report['cache'] = dict(entries_before=len(cache_before), entries_after=len(cache_after),
                              bytes_after=sum(p.stat().st_size for p in cache_after),
                              float32_payload_bytes=510*384*4)
        report['database_after'] = database_snapshot()
        assert report['database_before'] == report['database_after']
        report['database_unchanged'] = True
        report['C_rows'] = 0
        report['passed'] = True
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
    report['peak_process_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['total_seconds'] = perf_counter()-started
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('passed', 'errors', 'total_seconds', 'peak_process_rss_kib')}), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
