"""Audit exact and near-duplicate Chinese content within and across exam sets."""
import argparse
from collections import Counter
from difflib import SequenceMatcher
from itertools import combinations
import re
import unicodedata

from content_model4 import extract, read_content

MIN_LENGTH = 10
JACCARD_LIMIT = 0.60
RATIO_LIMIT = 0.75


def normalize(value):
    value = re.sub(r'（(?:5[89]|6[0-4])）_+|^[男女问][：:]|^[A-F]\s+', '', value.strip())
    return ''.join(ch for ch in value if not ch.isspace()
                   and unicodedata.category(ch)[0] != 'P')


def units(exam):
    for row in exam['items']:
        fields = []
        for field in ('transcript', 'passage', 'lines', 'prompt', 'question', 'options', 'models', 'model'):
            values = row.get(field, [])
            if isinstance(values, str):
                values = [values]
            if field == 'prompt':
                values = [v.removeprefix('请写一篇不少于80字的短文，') for v in values]
            if field == 'options':
                values = sorted(values, key=normalize)
            fields.extend(values)
        yield (exam['set'], row['number']), fields
    for (first, passage_options) in zip((58, 61), exam['sentence_banks']):
        passage, options = passage_options
        yield (exam['set'], first), [passage, *sorted(options, key=normalize)]
    for first, words in zip((33, 38), exam['word_banks']):
        yield (exam['set'], first), list(words)


def audit(exams):
    sentences, whole = {}, {}
    for exam in exams:
        item_fields = {}
        for coord, fields in units(exam):
            parts = [normalize(s) for v in fields for s in re.split(r'[。！？!?；;\n]+', v)]
            eligible = [p for p in parts if len(p) >= MIN_LENGTH]
            for p in eligible:
                sentences.setdefault(p, set()).add(coord)
            # Include short options in the full-item signature, but suppress a
            # full-item signature containing no substantial sentence.
            signature = ''.join(parts)
            if eligible:
                whole.setdefault(signature, set()).add(coord)
            item_fields.setdefault(coord, []).extend(parts)
        for row in exam['items']:
            start, end = row.get('scope', (0, 0))
            if row['number'] == start < end:
                coords = [(exam['set'], n) for n in range(start, end + 1)]
                signature = ''.join(part for coord in coords for part in item_fields[coord])
                if any(len(part) >= MIN_LENGTH for coord in coords for part in item_fields[coord]):
                    whole.setdefault(signature, set()).add(coords[0])

    hits = {}
    for label, index in [('sentence', sentences), ('item', whole)]:
        for value, coords in index.items():
            for pair in combinations(sorted(coords), 2):
                hits.setdefault(pair, {})[('exact', label)] = (value, value)
        features = [(s, coords, Counter(s), set(zip(s, s[1:]))) for s, coords in index.items()]
        for i, (a, ac, ca, ga) in enumerate(features):
            for j in range(i + 1, len(features)):
                b, bc, cb, gb = features[j]
                jac_possible = min(len(ga), len(gb)) >= JACCARD_LIMIT * max(len(ga), len(gb))
                ratio_possible = 2 * min(len(a), len(b)) >= RATIO_LIMIT * (len(a) + len(b))
                if not (jac_possible or ratio_possible) or (len(ac) == len(bc) == 1 and ac == bc):
                    continue
                common = len(ga & gb) if jac_possible else 0
                jac = common / (len(ga) + len(gb) - common)
                ratio = 0.0
                if jac < JACCARD_LIMIT and ratio_possible:
                    overlap = sum(min(count, cb[ch]) for ch, count in ca.items() if ch in cb)
                    if 2 * overlap >= RATIO_LIMIT * (len(a) + len(b)):
                        ratio = max(SequenceMatcher(None, a, b, autojunk=False).ratio(),
                                    SequenceMatcher(None, b, a, autojunk=False).ratio())
                if jac >= JACCARD_LIMIT or ratio >= RATIO_LIMIT:
                    for left in ac:
                        for right in bc:
                            if left != right:
                                hits.setdefault(tuple(sorted((left, right))), {})[
                                    ('near', label)] = (a, b)
    return hits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sets', type=int, nargs='+', default=range(1, 11))
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--original', action='store_true', help='extract and audit the source PDFs')
    source.add_argument('--finished', action='store_true', help='verify the content against the finished PDFs before auditing')
    args = parser.parse_args()
    if args.finished:
        from os import environ
        from verify4 import verify

        for n in args.sets:
            verify(4,n,environ.get('PDFTOTEXT','pdftotext'))
    read_exam = extract if args.original else read_content
    hits = audit(read_exam(n) for n in args.sets)
    for (left, right), reasons in sorted(hits.items()):
        print(left, right, reasons)
    exact = sum(any(kind == 'exact' for kind, _ in r) for r in hits.values())
    near = sum(any(kind == 'near' for kind, _ in r) for r in hits.values())
    print(f'exact={exact}, near={near}')
    if args.finished:
        cross = {pair: reasons for pair, reasons in hits.items() if pair[0][0] != pair[1][0]}
        print(f'cross-set={len(cross)}')
        return int(bool(cross))
    return int(bool(hits))


if __name__ == '__main__':
    raise SystemExit(main())
