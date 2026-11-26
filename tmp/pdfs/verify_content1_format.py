"""Check a rebuilt Level 1 booklet and render it alongside approved set 02."""
import argparse
from contextlib import closing
from pathlib import Path
import re

import pdfplumber
from PIL import Image
import pypdfium2 as pdfium
from pypdf import PdfReader

from build_content1 import PART_ORDER, PLAY, load_json, preview


def overlaps(a, b, first, last):
    return min(a[last], b[last]) - max(a[first], b[first]) > .02


def check_lines(page):
    # PDF font boxes include ascenders and descenders even for short glyphs.
    # Group by baseline; compare glyph boxes across baselines only where the
    # horizontal extents intersect, so adjacent columns stay independent.
    lines = {}
    for char in page.chars:
        if char['text'].strip():
            lines.setdefault(round(char['matrix'][5], 1), []).append(char)
    ink_lines = sorted(lines.values(), key=lambda line: min(c['top'] for c in line))
    for i, upper in enumerate(ink_lines):
        bottom = max(c['bottom'] for c in upper)
        for lower in ink_lines[i+1:]:
            if min(c['top'] for c in lower) >= bottom:
                break
            for a in upper:
                for b in lower:
                    assert not (overlaps(a, b, 'x0', 'x1') and
                                overlaps(a, b, 'top', 'bottom')), (
                                    page.page_number, a['text'], b['text'], a['top'], b['top'])
    if page.page_number in (3, 5, 8):
        for photo in page.images:
            for char in page.chars:
                assert not (overlaps(photo, char, 'x0', 'x1') and
                            overlaps(photo, char, 'top', 'bottom')), page.page_number


def rows(page, top, bottom, left):
    scale = page.height / 540
    return [row for row in page.filter(
        lambda obj: obj['object_type'] == 'char' and
        top*scale <= obj['top'] < bottom*scale and obj['x0'] >= left*scale
    ).extract_text_lines(x_tolerance=2, y_tolerance=4) if row['text'].strip()]


def choice_gaps(pinyin, hanzi):
    labels = [c for c in hanzi['chars'] if c['text'] in 'ABC']
    assert [c['text'] for c in labels] == list('ABC'), hanzi['text']
    for left, right in zip(labels, labels[1:]):
        end = max(c['x1'] for c in pinyin['chars'] + hanzi['chars']
                  if c['text'].strip() and left['x0'] <= c['x0'] < right['x0'])
        yield right['x0'] - end


def check_items(pdf, data):
    gaps, leading, block_gaps = [], [], []
    locations = {
        'L2': (4, [226, 281, 336, 391, 446], 501, 46),
        'L4': (6, [233, 288, 343, 398, 453], 508, 46),
        'R1': (8, [379, 403, 427, 451, 475], 505, 49),
        'R2': (9, [200, 249, 298, 347, 396], 436, 49),
        'R3': (10, [227, 273, 319, 386, 431], 505, 49),
        'R4': (11, [226, 314, 402, 119, 222], 509, 49),
    }
    compact = lambda value: re.sub(r'\s+', '', value)
    for part, (page_no, starts, end, left) in locations.items():
        previous = None
        for i, (top, item) in enumerate(zip(starts, data[part]['items'])):
            if 'original' not in item:
                previous = None
                continue
            continued = part == 'R4' and i >= 3
            page = pdf.pages[page_no-1+continued]
            bottom = starts[i+1] if i+1 < len(starts) and starts[i+1] > top else end
            lines = rows(page, top, bottom, left)
            assert lines, (part, i)
            assert len(lines) % 2 == 0, (part, i, [line['text'] for line in lines])
            if previous and previous[0] == page.page_number:
                leading.append(lines[0]['top'] - previous[1])
            previous = (page.page_number, lines[-1]['bottom'])
            for j in range(0, len(lines), 2):
                pinyin, hanzi = lines[j:j+2]
                assert hanzi['top'] >= pinyin['bottom'], (part, i, j)
                if j:
                    leading.append(pinyin['top'] - lines[j-1]['bottom'])
            if lines:
                block_gaps.append(bottom * page.height / 540 - lines[-1]['bottom'])
            if part in ('R1', 'R2'):
                box_left, box_right = (329, 344) if part == 'R1' else (185, 200)
                scale = page.width / 382
                assert all(c['x1'] <= box_left*scale or c['x0'] >= box_right*scale
                           for line in lines for c in line['chars']), (part, i)
            if part in ('L2', 'L4', 'R4'):
                pinyin, hanzi = lines[-2:]
                gaps.extend(choice_gaps(pinyin, hanzi))
                assert compact(hanzi['text']) == ''.join(
                    key + compact(item['choices'][key]['hanzi']) for key in 'ABC')
                assert compact(pinyin['text']) == ''.join(
                    compact(item['choices'][key]['pinyin']) for key in 'ABC')
                if part in ('L2', 'L4'):
                    assert len(lines) == 2, (part, i)
                else:
                    assert len(lines) in (6, 8), (part, i)
                    assert compact(''.join(line['text'] for line in lines[1:-2:2])) == compact(
                        ''.join(pair['hanzi'] for pair in item['stem']))
    assert min(gaps, default=20) >= 20, gaps
    assert min(leading, default=3) >= 3, leading
    assert min(block_gaps, default=3) >= 3, block_gaps
    print(f'A/B/C min {min(gaps, default=0):.2f} pt; '
          f'Hanzi to next pinyin min {min(leading, default=0):.2f} pt; '
          f'clearance to next block or bottom rule min {min(block_gaps, default=0):.2f} pt')


def check_answer(path, parts):
    pages = PdfReader(path).pages
    assert len(pages) == 3
    keys = [item['answer'] for part in PART_ORDER for item in parts[part]['items']]
    assert re.findall(r'(\d+)\s+([A-F])', pages[0].extract_text()) == [
        (str(i), key) for i, key in enumerate(keys, 1)]
    for i, page in enumerate(pages[1:]):
        body = '\n'.join(page.extract_text().splitlines()[1:])
        expected = [line['hanzi'] for part in PART_ORDER[i*2:i*2+2]
                    for item in [parts[part]['example'], *parts[part]['items']]
                    for line in item['stem']]
        assert re.findall(r'[\u4e00-\u9fff：，、。？！]+[。？！]', body) == expected
        assert not re.search(r'[A-Za-zÀ-ž\uac00-\ud7af]', body)


def compare(problem, reference, directory, tag):
    with pdfium.PdfDocument(reference) as approved:
        for i, page in enumerate(approved, 1):
            with closing(page.render(scale=2.2)) as bitmap, Image.open(
                directory/f'{tag}_문제지-{i:02}.png'
            ) as actual:
                left = bitmap.to_pil()
                joined = Image.new('RGB', (left.width+actual.width+16, left.height), '#c0c0c0')
                joined.paste(left, (0, 0))
                joined.paste(actual, (left.width+16, 0))
                joined.save(directory/f'비교_{tag}-{i:02}.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('set_number', type=int)
    parser.add_argument('--output-dir', type=Path, default=Path('output'))
    parser.add_argument('--reference-dir', type=Path, default=Path('output'))
    parser.add_argument('--answer-dir', type=Path, default=Path('output'))
    args = parser.parse_args()
    tag = f'제{args.set_number:02}회'
    stem = f'HSK3.0_1급_{tag}_'
    parts = load_json(Path('scripts/content1')/f'{tag}.json')['parts']
    problem = args.output_dir/(stem+'문제지.pdf')
    answer = args.answer_dir/(stem+'정답및해설.pdf')
    directory = args.output_dir/'preview'
    directory.mkdir(exist_ok=True)
    with pdfplumber.open(problem) as pdf:
        assert len(pdf.pages) == 12 and problem.stat().st_size < 5_000_000
        for page in pdf.pages:
            check_lines(page)
        check_items(pdf, parts)
    check_answer(answer, parts)
    preview(problem, directory, tag+'_문제지', PLAY+str(args.set_number))
    preview(answer, directory, tag+'_정답및해설')
    compare(problem, args.reference_dir/'HSK3.0_1급_제02회_문제지.pdf', directory, tag)
    print('12 problem pages, 3 answer pages; JSON answers and transcripts match; one cover QR.')


if __name__ == '__main__':
    main()
