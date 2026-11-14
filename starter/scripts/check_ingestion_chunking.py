"""Run the ingestion/chunking audit only; no embedding, database or benchmark."""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from starter.src.corpus import load_manifest_pages
from starter.src.preparation import audit_chunks, build_strategies


def _ranges(numbers):
    groups = []
    for number in sorted(set(numbers)):
        if groups and groups[-1][-1] + 1 == number:
            groups[-1].append(number)
        else:
            groups.append([number])
    return ', '.join(str(g[0]) if len(g) == 1 else f'{g[0]}–{g[-1]}' for g in groups)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/manifest.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'results')
    parser.add_argument('--chunks-dir', type=Path, default=ROOT / 'data/local/stage3/chunks')
    args = parser.parse_args(argv)
    report = {'passed': False, 'errors': [], 'warnings': [], 'strategies': {}}
    started = perf_counter()
    output = args.output_dir.resolve()
    chunks_dir = args.chunks_dir.resolve()
    if not output.is_relative_to(ROOT) or not chunks_dir.is_relative_to((ROOT / 'data/local').resolve()):
        parser.error('reports must stay in repository; chunk text must stay in data/local')
    try:
        ingestion_start = perf_counter()
        result = load_manifest_pages(args.manifest)
        report.update(manifest_sha256=result.manifest_sha256, selected_pages=len(result.pages),
                      skipped_pages=result.skipped_pages, sources=result.sources,
                      ingestion_seconds=round(perf_counter() - ingestion_start, 3))
        if len(result.pages) != 40:
            raise ValueError(f'Expected exactly 40 approved corpus pages; got {len(result.pages)}')
        chunk_start = perf_counter()
        strategies = build_strategies(result.pages)
        repeated = build_strategies(result.pages)
        deterministic = all(strategies[s] == repeated[s] for s in strategies)
        shared = strategies['C'] is strategies['B']
        report.update(deterministic_ids=deterministic, c_reuses_b=shared)
        if not deterministic or not shared:
            report['errors'].append('determinism or B/C identity check failed')
        for name, chunks in strategies.items():
            metrics = audit_chunks(result.pages, chunks, name)
            report['strategies'][name] = metrics
            report['errors'].extend(metrics['errors'])
        report['chunking_and_repeat_audit_seconds'] = round(perf_counter() - chunk_start, 3)
        if not any('\n\n' in page.text for page in result.pages):
            report['warnings'].append('Selected pypdf text has no blank-line paragraph delimiters; B uses sentence/line/word boundaries without changing normalized text.')
        splits = report['strategies']['B']['sql_split_boundaries']
        if splits:
            report['warnings'].append(f'B has {splits} boundaries inside detected SQL spans longer than 500 characters or continuing to the page end; inspect local chunks. SQL detection is heuristic.')
        report['pages'] = []
        for page in result.pages:
            report['pages'].append({'source_id': page.document_id, 'physical_page': page.page,
                                    'printed_page_label': page.metadata['printed_page_label'],
                                    'section': page.metadata['section'], 'characters': len(page.text),
                                    'A_chunks': sum(c.document_id == page.document_id and c.page == page.page for c in strategies['A']),
                                    'B_chunks': sum(c.document_id == page.document_id and c.page == page.page for c in strategies['B'])})
        if hashlib.sha256(args.manifest.read_bytes()).hexdigest() != result.manifest_sha256:
            report['errors'].append('manifest changed during run')
        report['passed'] = not report['errors']
        if report['passed']:
            chunks_dir.mkdir(parents=True, exist_ok=True)
            for name in ['A', 'B']:
                with (chunks_dir / f'{name}.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
                    for chunk in strategies[name]:
                        stream.write(json.dumps(asdict(chunk), ensure_ascii=False, sort_keys=True) + '\n')
            report['chunk_artifacts'] = {'A': (chunks_dir / 'A.jsonl').relative_to(ROOT).as_posix(),
                                         'B': (chunks_dir / 'B.jsonl').relative_to(ROOT).as_posix(),
                                         'C': 'same objects/IDs/text/metadata as B; no separate chunking or artifact'}
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
    report['elapsed_seconds'] = round(perf_counter() - started, 3)
    report['checked_at'] = datetime.now(timezone.utc).isoformat()
    report['environment'] = {'python': sys.version.split()[0], 'pypdf': version('pypdf'),
                             'jsonschema': version('jsonschema')}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'ingestion_chunking.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# Kiểm tra Document Ingestion & Chunking', '', f"Kết quả: {'PASS' if report['passed'] else 'FAIL'}", '',
             f"Trang được đọc: {report.get('selected_pages', 0)}; trang bỏ qua: {len(report.get('skipped_pages', []))}.",
             f"Lỗi: {len(report['errors'])}; cảnh báo: {len(report['warnings'])}.", '',
             '| Cấu hình | Số chunk | Min | Mean | Max | Ký tự nguồn được phủ |',
             '|---|---:|---:|---:|---:|---:|']
    for name, metrics in report['strategies'].items():
        lines.append(f"| {name} | {metrics['chunks']} | {metrics['min_chars']} | {metrics['mean_chars']} | {metrics['max_chars']} | {metrics['covered_characters']}/{metrics['source_characters']} |")
    lines += ['', 'A: fixed_size(size=500, overlap=50); B: by_paragraph(max_size=500). Đơn vị: ký tự Unicode.',
              f"ID ổn định khi chạy lại: {report.get('deterministic_ids', False)}; C dùng chính danh sách B: {report.get('c_reuses_b', False)}.",
              'C chưa áp dụng filter vì chưa triển khai retrieval. Không có embedding, database ingestion hoặc benchmark.',
              '', '## Trang được chọn', '', '| PDF page | Printed label | Section | Characters | A chunks | B chunks |',
              '|---:|---|---|---:|---:|---:|']
    for page in report.get('pages', []):
        lines.append(f"| {page['physical_page']} | {page['printed_page_label']} | {page['section']} | {page['characters']} | {page['A_chunks']} | {page['B_chunks']} |")
    lines += ['', '## Trang bỏ qua', '']
    for reason, count in Counter(p['reason'] for p in report.get('skipped_pages', [])).items():
        numbers = [p['physical_page'] for p in report['skipped_pages'] if p['reason'] == reason]
        lines.append(f'- {reason}: {count} trang; số vật lý {_ranges(numbers)}.')
    lines += ['', '## Lỗi', ''] + (['- ' + e for e in report['errors']] or ['- Không có.'])
    lines += ['', '## Cảnh báo và giới hạn', ''] + (['- ' + w for w in report['warnings']] or ['- Không có cảnh báo tự động.'])
    lines += ['- Không ghép qua trang vật lý; SQL đã bị ngắt tại ranh giới trang không được tự nối.',
              '- Giữ nguyên text chuẩn hóa, kể cả header/footer và whitespace; không tự khôi phục paragraph hoặc sửa checksum.',
              '- Coverage kiểm tra lát cắt và mọi ký tự, không phải điểm coherence/grounding.',
              '', f"Thời điểm: {report['checked_at']}; thời gian chạy: {report['elapsed_seconds']} giây.",
              f"Môi trường: {report['environment']}.", f"Manifest SHA-256: `{report.get('manifest_sha256', 'unavailable')}`.",
              'Chunk chứa text chỉ lưu trong data/local/stage3/chunks/.']
    (output / 'ingestion_chunking.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"{'PASS' if report['passed'] else 'FAIL'}: {report.get('selected_pages', 0)} pages; {len(report['errors'])} errors")
    for name, metrics in report['strategies'].items():
        print(f"{name}: {metrics['chunks']} chunks; min/mean/max={metrics['min_chars']}/{metrics['mean_chars']}/{metrics['max_chars']}")
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
