"""Build a Level 1 booklet with approved JSON text and replacement photographs."""
import argparse
from contextlib import closing
from io import BytesIO
import json
from pathlib import Path
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw
import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from split_print import build, picture_boxes, text_bands, write_answer

PART_ORDER = ('L1', 'L2', 'L3', 'L4', 'R1', 'R2', 'R3', 'R4')
PLAY = 'https://yanchunnu.github.io/-/hsk-listening.html?level=1&set='


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def text(pdf, x, y, value, font, size, color):
    pdf.setFont(font, size)
    pdf.setFillColor(color)
    pdf.drawString(x, 540-y, value)


def width(pair):
    return max(pdfmetrics.stringWidth(pair['pinyin'], 'Latin', 7),
               pdfmetrics.stringWidth(pair['hanzi'], 'CN', 10))


def paired(pdf, x, y, pair, right=354):
    assert x + width(pair) <= right, (x, right, pair)
    pinyin = pair['pinyin']
    py_x = x
    if pinyin.startswith('★ '):
        text(pdf, x, y, '★', 'CN', 7, '#4e5e70')
        py_x += pdfmetrics.stringWidth('★', 'CN', 7) + 2
        pinyin = pinyin[2:]
    text(pdf, py_x, y, pinyin, 'Latin', 7, '#4e5e70')
    text(pdf, x, y+10, pair['hanzi'], 'CN', 10, '#17212c')


def choices(pdf, y, values, labels, x, right, scale):
    widths = [12+width(values[label]) for label in labels]
    starts = [x, x+104, x+208]
    gaps = [b-a-span for a, b, span in zip(starts, starts[1:], widths)]
    if min(gaps)*scale < 20 or starts[-1]+widths[-1] > right:
        gap = (right-x-sum(widths))/(len(labels)-1)
        starts = [x, x+widths[0]+gap, x+sum(widths[:2])+2*gap]
        gaps = [gap, gap]
    assert min(gaps)*scale >= 20, (labels, values, gaps)
    for label, left in zip(labels, starts):
        text(pdf, left, y+10, label, 'Latin', 8, '#17212c')
        paired(pdf, left+12, y, values[label], right)
    return min(gaps)*scale


def draw_item(pdf, part, item, x, y, scale):
    right = {'R1': 326, 'R2': 183}.get(part, 354)
    if part in ('L2', 'L4'):
        x += 5
    for pair in item['stem']:
        if part == 'R4' and width(pair) > right-x:
            han = re.split(r'(?<=[。！？])(?=.)', pair['hanzi'], maxsplit=1)
            py = re.split(r'(?<=[.!?])\s+(?=.)', pair['pinyin'], maxsplit=1)
            assert len(han) == len(py) == 2, pair
            lines = [dict(hanzi=h, pinyin=p) for h, p in zip(han, py)]
        else:
            lines = [pair]
        for line in lines:
            paired(pdf, x, y, line, right)
            y += 17
    if part in ('L2', 'L4', 'R4'):
        return choices(pdf, y+(part != 'L4'), item['choices'], 'ABC', x, 354, scale)
    return None


def replacement_photos(parts, requests):
    groups = {2: [item['choices'][key] for item in parts['L1']['items'] for key in 'ABC'],
              4: [parts['L3']['choices'][k] for k in 'ABCDEF'],
              6: [parts['R1']['choices'][k] for k in 'ABCDEF']}
    return {n: [Path('tmp/newimages1')/requests[v['image_request_id']]['filename']
                if 'image_request_id' in v else None for v in images]
            for n, images in groups.items()}


def draw_crop(pdf, rendered, clip, image_path, erase=()):
    n, (left, top, right, bottom), x, y, k, photo = clip
    w, h = right-left, bottom-top
    if image_path:
        with Image.open(image_path) as image:
            assert abs(image.width/image.height - w/h) / (w/h) < .03, image_path
        image = str(image_path)
    else:
        with closing(rendered[n-1]) as original:
            sx, sy = original.get_width()/382, original.get_height()/540
            bounds = (left*sx, (540-bottom)*sy, (382-right)*sx, top*sy)
            scale = 1200/max(w*sx, h*sy) if photo else 2.5
            with closing(original.render(scale=scale, crop=bounds)) as bitmap:
                image = bitmap.to_pil().copy()
        for start, end in erase:
            a = round((start-left)*image.width/w)
            b = round((end-left)*image.width/w)
            top_px = round(6*image.height/h)
            bottom_px = round(30*image.height/h)
            fill = image.getpixel((a, top_px))
            ImageDraw.Draw(image).rectangle((a, top_px, b, bottom_px), fill=fill)
        if photo:
            encoded = BytesIO()
            image.convert('RGB').save(encoded, format='JPEG', quality=85, optimize=True)
            encoded.seek(0)
            image = encoded
    pdf.drawImage(ImageReader(image), x, 540-y-h*k, w*k, h*k)


def draw_page(pdf, rendered, clips, parts, photos, page_no, scale, gaps):
    photo_slot = 0
    for index, clip in enumerate(clips):
        n, _, x, y, _, photo = clip
        if photo:
            draw_crop(pdf, rendered, clip, photos[n][photo_slot])
            photo_slot += 1
            continue
        part = {3: 'L2', 5: 'L4', 6: 'R1', 7: 'R2', 8: 'R3', 9: 'R4'}[n]
        data = parts[part]
        if n == 8 and index == 0:
            values, original = data['choices'], data.get('original_choices', {})
            changed = [(45+slot*53.25, values[label]) for slot, label in enumerate('ABCDEF')
                       if values[label] != original.get(label, values[label])]
            draw_crop(pdf, rendered, clip, None, [(left, left+39) for left, _ in changed])
            for left, value in changed:
                paired(pdf, left+1, y+15, value, left+39)
            continue
        row = index-photo_slot-(n == 8)
        if n == 7:
            row, side = divmod(row, 2)
            if side:
                label = 'ABCDE'[row]
                if data['choices'][label] == data.get('original_choices', data['choices'])[label]:
                    draw_crop(pdf, rendered, clip, None)
                else:
                    text(pdf, x, y+17, label, 'Latin', 8, '#17212c')
                    paired(pdf, x+14, y+7, data['choices'][label])
                continue
        if n == 9 and page_no == 12:
            row += 3
        item = data['items'][row]
        if 'original' not in item:
            draw_crop(pdf, rendered, clip, None)
        else:
            gap = draw_item(pdf, part, item, x, y+6, scale)
            if gap is not None:
                gaps.append(gap)


def write_problem(doc, source, rendered, sizes, photos, target):
    parts = doc['parts']
    n = doc['set']
    W, H = sizes
    unused = [parts[part]['example']['answer'] for part in ('L3', 'R1', 'R3')]
    examples = [tuple((v['hanzi'], v['pinyin']) for v in parts[part]['example']['stem'])
                for part in ('L3', 'R1', 'R3')]
    overlay, plans = build(n, W, H, lambda p: text_bands(rendered[p-1]),
                           lambda p: picture_boxes(source.pages[p-1], 15 if p==2 else 6),
                           unused, (examples[0], examples[1][0], examples[2][0]))
    writer = PdfWriter()
    cover = writer.add_page(source.pages[0])
    assert '문제 · 정답 · 듣기 대본 · 한국어 해설' in cover.extract_text()
    contents = cover.get_contents()
    assert contents.operations[46][1] == b'Tj'
    del contents.operations[46]
    cover.replace_contents(contents)
    assert [a.get_object()['/A']['/URI'] for a in cover['/Annots']] == [PLAY+str(n)]
    gaps = []
    for number, (base, clips) in enumerate(zip(PdfReader(overlay).pages, plans), 2):
        page = writer.add_page(base)
        if clips:
            stream = BytesIO()
            pdf = canvas.Canvas(stream, pagesize=sizes)
            pdf.scale(W/382, H/540)
            draw_page(pdf, rendered, clips, parts, photos, number, W/382, gaps)
            pdf.save()
            page.merge_page(PdfReader(stream).pages[0])
    writer.add_metadata({'/Title': f'HSK 3.0 1급 제{n:02}회 문제지'})
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    writer.write(target)
    assert target.stat().st_size < 5_000_000
    assert len(PdfReader(target).pages) == 12
    return min(gaps, default=None)


def preview(path, directory, prefix, cover_url=None):
    detector = cv2.QRCodeDetector()
    with pdfium.PdfDocument(path) as result:
        for i, page in enumerate(result, 1):
            with closing(page.render(scale=2.2)) as bitmap:
                image = bitmap.to_pil().copy()
            image.save(directory/f'{prefix}-{i:02}.png')
            found, values, _, _ = detector.detectAndDecodeMulti(np.asarray(image.convert('L')))
            if cover_url and i == 1:
                assert found and list(values) == [cover_url], values
            else:
                assert not found, (prefix, i, values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('set_number', type=int, choices=range(1, 11))
    parser.add_argument('--output-dir', type=Path, default=Path('output'))
    args = parser.parse_args()
    n, out = args.set_number, args.output_dir
    tag = f'제{n:02}회'
    doc = load_json(Path('scripts/content1')/f'{tag}.json')
    parts = doc['parts']
    assert any('original' in item for part in parts.values() for item in part['items'])
    photos = replacement_photos(parts, {r['id']: r for r in load_json('tmp/image_requests1.json')})
    source = PdfReader(doc['source'])
    sizes = tuple(map(float, (source.pages[0].mediabox.width, source.pages[0].mediabox.height)))
    stem = f'HSK3.0_1급_{tag}_'
    previews = out/'preview'
    previews.mkdir(parents=True, exist_ok=True)
    problem = out/(stem+'문제지.pdf')
    with pdfium.PdfDocument(doc['source']) as rendered:
        gap = write_problem(doc, source, rendered, sizes, photos, problem)
    keys = [''.join(item['answer'] for item in parts[p]['items']) for p in PART_ORDER]
    scripts = [[line['hanzi'] for line in item['stem']]
               for p in PART_ORDER[:4] for item in parts[p]['items']]
    examples = [[line['hanzi'] for line in parts[p]['example']['stem']] for p in PART_ORDER[:4]]
    write_answer(out, stem, n, *sizes, keys, scripts, examples)
    preview(problem, previews, tag+'_문제지', PLAY+str(n))
    preview(out/(stem+'정답및해설.pdf'), previews, tag+'_정답및해설')
    print(f'{tag}: {problem.stat().st_size:,} B')
    if gap is not None:
        print(f'Minimum A–C gap: {gap:.2f} pt')


if __name__ == '__main__':
    main()
