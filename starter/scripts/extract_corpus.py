"""Re-extract the approved PostgreSQL snapshot; never download or invent reviews.

Requires an existing reviewed manifest. Only writes text under data/local/.
"""
import argparse
import json
from pathlib import Path
import sys
from pypdf import PdfReader
from check_corpus import ROOT, digest, local_path, normalize_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/manifest.json')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    for source in manifest['sources']:
        pdf = local_path(source['local_path'], ROOT)
        if digest(pdf.read_bytes()) != source['sha256']:
            raise ValueError('PDF snapshot checksum mismatch; refusing extraction')
        reader = PdfReader(pdf)
        if len(reader.pages) != source['physical_page_count']:
            raise ValueError('physical page count mismatch')
        for record in source['pages']:
            try:
                text = normalize_text(reader.pages[record['physical_page'] - 1].extract_text() or '')
                status = 'ok' if text else 'empty'
            except Exception:
                text, status = '', 'error'
            data = text.encode('utf-8')
            if (digest(data) != record['text_sha256'] or len(text) != record['normalized_char_count']
                    or status != record['extraction_status']):
                raise ValueError(f"Extraction differs at {record['page_id']}; review extractor/snapshot")
            target = local_path(record['text_path'], ROOT)
            if not target.is_relative_to((ROOT / 'data/local/normalized').resolve()):
                raise ValueError('normalized output must stay under data/local/normalized')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if source['source_id'] == 'postgresql-16.16-a4' and record['physical_page'] == 2:
                target.with_name('NOTICE.txt').write_bytes(data)
        print(f"Extracted {len(source['pages'])} physical pages for {source['source_id']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
