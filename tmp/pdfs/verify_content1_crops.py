"""Check source text bboxes carried by untouched raster crops."""
from pathlib import Path
import sys

import pdfplumber
import pypdfium2 as pdfium
from pypdf import PdfReader

from build_content1 import build, load_json, picture_boxes, text_bands
from verify_content1_format import overlaps


def audit(n):
    tag = f'제{n:02}회'
    doc = load_json(Path('scripts/content1') / f'{tag}.json')
    parts = doc['parts']
    source = PdfReader(doc['source'])
    w, h = map(float, (source.pages[0].mediabox.width, source.pages[0].mediabox.height))
    example_keys = ('L3', 'R1', 'R3')
    answers = [parts[key]['example']['answer'] for key in example_keys]
    stems = [tuple((v['hanzi'], v['pinyin']) for v in parts[key]['example']['stem'])
             for key in example_keys]
    with pdfium.PdfDocument(doc['source']) as rendered:
        _, plans = build(n, w, h, lambda p: text_bands(rendered[p-1]),
                         lambda p: picture_boxes(source.pages[p-1], 15 if p == 2 else 6),
                         answers, (stems[0], stems[1][0], stems[2][0]))
    new_path = Path('output') / f'HSK3.0_1급_{tag}_문제지.pdf'
    with pdfplumber.open(doc['source']) as original, pdfplumber.open(new_path) as final:
        problems = []
        total = 0
        for page, clips in zip(final.pages[1:], plans):
            crop_lines = []
            for slot, (i, (l, t, r, b), x, y, k, photo) in enumerate(clips):
                if photo:
                    continue
                part = {3: 'L2', 5: 'L4', 6: 'R1', 7: 'R2', 8: 'R3', 9: 'R4'}[i]
                row = slot - sum(c[-1] for c in clips[:slot]) - (i == 8)
                if (i != 7 or row % 2 == 0) and row >= 0:
                    if i == 7:
                        row //= 2
                    if i == 9 and page.page_number == 12:
                        row += 3
                    if 'original' in parts[part]['items'][row]:
                        continue
                p = original.pages[i-1]
                sx, sy = p.width / 382, p.height / 540
                fx, fy = w / 382, h / 540
                lines = {}
                for c in p.chars:
                    if not c['text'].strip() or not (
                        l < (c['x0']+c['x1'])/2/sx < r and t < (c['top']+c['bottom'])/2/sy < b
                    ):
                        continue
                    box = dict(text=c['text'], x0=(x+(max(l,c['x0']/sx)-l)*k)*fx,
                               x1=(x+(min(r,c['x1']/sx)-l)*k)*fx,
                               top=(y+(max(t,c['top']/sy)-t)*k)*fy,
                               bottom=(y+(min(b,c['bottom']/sy)-t)*k)*fy)
                    lines.setdefault(round(c['matrix'][5], 1), []).append(box)
                crop_lines.extend(lines.values())
            vector_lines = {}
            for c in page.chars:
                if c['text'].strip():
                    vector_lines.setdefault(round(c['matrix'][5], 1), []).append(c)
            all_lines = sorted([*crop_lines, *vector_lines.values()], key=lambda line: min(c['top'] for c in line))
            total += len(all_lines)
            for j, upper in enumerate(all_lines):
                bottom = max(c['bottom'] for c in upper)
                for lower in all_lines[j+1:]:
                    if min(c['top'] for c in lower) >= bottom:
                        break
                    for a in upper:
                        for b in lower:
                            if overlaps(a, b, 'x0', 'x1') and overlaps(a, b, 'top', 'bottom'):
                                problems.append((page.page_number, a['text'], b['text'], round(min(a['bottom'], b['bottom']) - max(a['top'], b['top']), 2)))
        print(tag, total, len(problems), problems[:15])
        assert not problems


for n in map(int, sys.argv[1:]):
    if n not in (1, 4, 5):
        raise SystemExit('This audit covers Level 1 sets 01, 04 and 05.')
    audit(n)
