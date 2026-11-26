"""Measure Level 3 option gaps from Poppler word boxes."""

import argparse
from collections import defaultdict
from pathlib import Path
import re
import subprocess
from xml.etree import ElementTree as ET


# PDF page numbers include the cover.
COUNTS = {5: 6, 6: 6, 7: 11, 13: 4, 14: 4, 15: 3}


def measure(path, pdftotext, validate=True):
    process = subprocess.run(
        [pdftotext, '-enc', 'UTF-8', '-bbox', '-', '-'],
        input=path.read_bytes(), capture_output=True, check=True,
    )
    pages = ET.fromstring(process.stdout).findall('.//{*}page')
    assert len(pages) == 21 and path.stat().st_size <= 5_000_000, path
    gaps, stacked = [], set()
    for page_number in (*COUNTS, 9, 10, 11, 12):
        rows = defaultdict(list)
        for word in pages[page_number-1].findall('{*}word'):
            x, y, right = (float(word.get(attr)) for attr in ('xMin', 'yMin', 'xMax'))
            rows[round(y, 2)].append((x, right, word.text or ''))
        groups = {}
        question = '例'
        columns = {}
        for y, words in sorted(rows.items()):
            words.sort()
            if re.fullmatch(r'\d+\.', words[0][2]):
                question = words[0][2][:-1]
            labels = [i for i, (_, _, value) in enumerate(words) if re.fullmatch(r'[A-F]\.?', value)]
            if not labels:
                continue
            letters = ''.join(words[i][2][0] for i in labels)
            if page_number in COUNTS:
                groups.setdefault(question, []).append((letters, [words[i][0] for i in labels]))
            for i in labels:
                if validate and len(labels) > 1:
                    letter = words[i][2]
                    assert abs(columns.setdefault(letter, words[i][0]) - words[i][0]) < .01, (path, page_number, y)
            for previous, current in zip(labels, labels[1:]):
                assert previous + 1 < current, (path, page_number, y)
                gap = words[current][0] - words[current-1][1]
                if validate:
                    assert gap >= 20, (path, page_number, question, gap)
                gaps.append(gap)
        if page_number in COUNTS:
            assert len(groups) == COUNTS[page_number], (path, page_number, groups)
            for item, lines in groups.items():
                letters = [line[0] for line in lines]
                if letters == ['A', 'B', 'C']:
                    if validate:
                        assert max(line[1][0] for line in lines) - min(line[1][0] for line in lines) < .01
                    stacked.add((page_number, item))
                else:
                    assert letters == ['ABC'], (path, page_number, item, letters)
        if page_number in (9, 10, 11, 12):
            labels = [value[0] for words in rows.values() for _, _, value in sorted(words)
                      if re.fullmatch(r'[A-F]\.?', value)]
            assert ''.join(labels) == ('ABCDEF' if page_number in (9, 11) else 'ABCDE'), (path, page_number, labels)
    return min(gaps), stacked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdftotext', default='pdftotext')
    parser.add_argument('--original', type=Path, help='directory of original question PDFs')
    args = parser.parse_args()
    print('| 회차 | 쪽수 | 바이트 | 최소 간격(pt) | 새로 세로 배치 (PDF 쪽/문항) |')
    print('|---|---:|---:|---:|---|')
    for number in range(1, 11):
        path = Path('output') / f'HSK3.0_3급_제{number:02}회_문제지.pdf'
        gap, stacked = measure(path, args.pdftotext)
        if args.original:
            _, original = measure(args.original / path.name, args.pdftotext, validate=False)
            stacked -= original
        items = ', '.join(f'{page}/{item}' for page, item in sorted(
            stacked, key=lambda entry: (entry[0], int(entry[1]) if entry[1].isdigit() else 0)
        )) or '없음'
        print(f'| {number:02} | 21 | {path.stat().st_size:,} | {gap:.3f} | {items} |')


if __name__ == '__main__':
    main()
