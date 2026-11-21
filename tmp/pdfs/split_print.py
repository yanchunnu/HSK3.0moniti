"""Rearrange a source set and write separate printable problem and answer PDFs."""
import argparse
from io import BytesIO
from contextlib import closing
from pathlib import Path
import re

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from reportlab import rl_config
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from build import PARTS, build

rl_config.useA85 = False

SET_NAMES = '一二三四五六七八九十'
# The original picture/word unused by the scored questions varies by set.
# For sets 2 and 6 the doctor in the picture is the woman.
DOCTOR = ('男：你是医生吗？', 'Nán: Nǐ shì yīshēng ma?',
          '女：是的，我是医生。', 'Nǚ: Shì de, wǒ shì yīshēng.')
RICE = ('女：你想吃米饭吗？', 'Nǚ: Nǐ xiǎng chī mǐfàn ma?',
        '男：是的，我想吃米饭。', 'Nán: Shì de, wǒ xiǎng chī mǐfàn.')
WRITING = ('她在写字。','Tā zài xiě zì.')
CAT = ('小猫在睡觉。','Xiǎomāo zài shuìjiào.')
BOOK = ('这是我的（F）。','Zhè shì wǒ de (F).')
EXAMPLES = [
    (('女：你在喝茶吗？','Nǚ: Nǐ zài hē chá ma？','男：是的，我在喝茶。','Nán: Shì de, wǒ zài hē chá.'),
     ('老师在上课。','Lǎoshī zài shàngkè.'), ('我（F）学校。','Wǒ (F) xuéxiào.')),
    (DOCTOR, WRITING, BOOK),
    (RICE, CAT, BOOK),
    (('男：你在做饭吗？','Nán: Nǐ zài zuò fàn ma?','女：是的，我在做饭。','Nǚ: Shì de, wǒ zài zuò fàn.'),
     ('他在睡觉。','Tā zài shuìjiào.'), ('我想（F）米饭。','Wǒ xiǎng (F) mǐfàn.')),
    (('男：你在看书吗？','Nán: Nǐ zài kàn shū ma?','女：是的，我在看书。','Nǚ: Shì de, wǒ zài kàn shū.'),
     ('她在看书。','Tā zài kàn shū.'), ('我家有一只（F）。','Wǒ jiā yǒu yì zhī (F).')),
    (DOCTOR, WRITING, BOOK),
    (RICE, CAT, BOOK),
    (('男：你在用电脑吗？','Nán: Nǐ zài yòng diànnǎo ma?','女：是的，我在用电脑。','Nǚ: Shì de, wǒ zài yòng diànnǎo.'),
     ('小猫在椅子上。','Xiǎomāo zài yǐzi shàng.'), ('今天很（F）。','Jīntiān hěn (F).')),
    (('女：他在做什么？','Nǚ: Tā zài zuò shénme?','男：他在睡觉。','Nán: Tā zài shuìjiào.'),
     ('她背着书包。','Tā bēizhe shūbāo.'), BOOK),
    (('男：您在做什么？','Nán: Nín zài zuò shénme?','女：我在倒茶。','Nǚ: Wǒ zài dào chá.'),
     ('火车来了。','Huǒchē lái le.'), ('我今年十（E）。','Wǒ jīnnián shí (E).')),
]
SENTENCE = r'[\u4e00-\u9fff：，、。？！；]+[。？！]'


def source_answers(source):
    key_text = re.sub(r'\s+', '', source.pages[9].extract_text())
    keys = re.findall(r'第[一二三四]部分([A-F]{5})', key_text)
    assert len(keys) == 8, keys
    scripts = []
    for page in source.pages[10:16]:
        chunks = re.split(r'([1-5])\s+정\s*답\s+([A-F])', page.extract_text().replace('\n',''))[1:]
        for local, answer, block in zip(chunks[::3], chunks[1::3], chunks[2::3]):
            pos = len(scripts)
            assert int(local) == pos % 5 + 1 and answer == ''.join(keys)[pos]
            lines = re.findall(SENTENCE, block)
            assert len(lines) == (1 if pos < 10 else 2), (pos, lines)
            scripts.append(lines)
    assert len(scripts) == 20
    return keys, scripts


def picture_boxes(page, expected):
    ops = page.get_contents().operations
    sx, sy = float(page.mediabox.width)/382, float(page.mediabox.height)/540
    boxes = []
    for i in range(5, len(ops)):
        if [op for _, op in ops[i-5:i+1]] == [b're', b'W*', b'n', b'q', b'cm', b'Do']:
            x,y,w,h = map(float, ops[i-5][0])
            boxes.append((x/sx, 540-(y+h)/sy, (x+w)/sx, 540-y/sy))
    assert len(boxes) == expected, boxes
    return boxes


def text_bands(page):
    sx, sy = page.get_width()/382, page.get_height()/540
    with closing(page.get_textpage()) as text:
        content = text.get_text_range()
        numbers = list(re.finditer(r'(?m)^[1-5]\.', content))
        assert [m[0] for m in numbers] == [f'{i}.' for i in range(1,6)]
        ends = [m.start() for m in numbers[1:]] + [content.rindex('HSK 1급')]
        bands = []
        for number, stop in zip(numbers, ends):
            boxes = [text.get_charbox(i) for i in range(number.end(),stop)
                     if not content[i].isspace()]
            boxes = [b for b in boxes if b[0]/sx >= 39 and 90 < 540-b[3]/sy < 498]
            bands.append((540-max(b[3] for b in boxes)/sy-2,
                          540-min(b[1] for b in boxes)/sy+2))
        return bands


def write_problem(source, rendered, set_number, sizes, unused, example, target):
    W,H = sizes
    X,Y = W/382,H/540
    overlay, plans = build(set_number, W, H, lambda n: text_bands(rendered[n-1]),
                           lambda n: picture_boxes(source.pages[n-1],15 if n==2 else 6),
                           unused, example)
    writer = PdfWriter()
    cover = writer.add_page(source.pages[0])
    assert '문제 · 정답 · 듣기 대본 · 한국어 해설' in cover.extract_text()
    contents = cover.get_contents()
    assert contents.operations[46][1] == b'Tj'
    del contents.operations[46]
    cover.replace_contents(contents)
    url = f'https://yanchunnu.github.io/-/hsk-listening.html?level=1&set={set_number}'
    assert [a.get_object()['/A']['/URI'] for a in cover['/Annots']] == [url]
    for overlay_page, clips in zip(PdfReader(overlay).pages, plans):
        page = writer.add_page(overlay_page)
        if not clips:
            continue
        patch_bytes = BytesIO()
        patch = canvas.Canvas(patch_bytes, pagesize=sizes)
        for n,(left,top,right,bottom),x,y,k,photo in clips:
            with closing(rendered[n-1]) as original:
                sx,sy = original.get_width()/382, original.get_height()/540
                bounds = (left*sx, (540-bottom)*sy, (382-right)*sx, top*sy)
                scale = 1200/max((right-left)*sx,(bottom-top)*sy) if photo else 2.5
                with closing(original.render(scale=scale,crop=bounds)) as bitmap:
                    image = bitmap.to_pil().copy()
            if photo:
                encoded = BytesIO()
                image.convert('RGB').save(encoded,format='JPEG',quality=85,optimize=True)
                encoded.seek(0)
                image = encoded
            patch.drawImage(ImageReader(image), x*X, (540-y-(bottom-top)*k)*Y,
                            (right-left)*k*X, (bottom-top)*k*Y)
        patch.save()
        page.merge_page(PdfReader(patch_bytes).pages[0])
    writer.add_metadata({'/Title':f'HSK 3.0 1급 제{set_number:02}회 문제지'})
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    writer.write(target)
    assert target.stat().st_size < 5_000_000
    result = PdfReader(target)
    assert len(result.pages) == 12 and not result.get_fields()
    for i,page in enumerate(result.pages):
        assert bool(page.get('/Annots')) == (i == 0)
        assert not re.search(r'사진[:：]?AI생성|答题卡|답안카드|한국어해설',
                             ''.join(page.extract_text().split()))


def write_answer(out, stem, set_number, W, H, keys, scripts, examples):
    parts = PARTS
    answer_path = out / (stem + '정답및해설.pdf')
    a = canvas.Canvas(str(answer_path), pagesize=(W,H))
    a.setTitle(f'HSK 3.0 1급 제{set_number:02}회 정답 및 해설')

    def write(x, y, content, size=14, font='CN'):
        a.setFillColor('#171717')
        a.setFont(font,size)
        a.drawString(x,H-y,content)

    def rule(y, color='#b9b9b9'):
        a.setStrokeColor(color)
        a.setLineWidth(.55)
        a.line(54,H-y,W-54,H-y)

    def header(title, page):
        write(54,48,f'HSK 3.0  /  一级  /  第{SET_NAMES[set_number-1]}套',11)
        rule(61)
        write(54,103,title,25)
        rule(H-54)
        write(W/2-3,H-33,str(page),9,'Latin')

    header('答案表',1)
    for section, section_title in enumerate(['听力','阅读']):
        top = 147 + section*278
        write(54,top,section_title,17)
        rule(top+15,'#5a5a5a')
        for row in range(4):
            idx = section*4+row
            y = top+45+row*47
            write(58,y,parts[row],12)
            for col, letter in enumerate(keys[idx]):
                xx = 152 + col*79
                write(xx,y,f'{idx*5+col+1:2}   {letter}',14,'Latin')
            rule(y+16)
    a.showPage()

    for page_idx in range(2):
        header('听力原文',page_idx+2)
        for section in range(2):
            i = page_idx*2+section
            top = 147 + section*320
            write(54,top,parts[i],17)
            rule(top+12,'#5a5a5a')
            y = top+38
            for n, lines in enumerate([examples[i], *scripts[i*5:i*5+5]]):
                if n:
                    write(58,y,str(i*5+n)+'.',11,'Latin')
                else:
                    write(58,y,'例',11)
                for j, sentence in enumerate(lines):
                    write(101,y+j*19,sentence)
                y += 46 if i >= 2 else 34
        a.showPage()
    a.save()

    q = PdfReader(answer_path)
    assert len(q.pages) == 3
    answers = re.findall(r'(\d+)\s+([A-F])',q.pages[0].extract_text())
    assert answers == [(str(i), letter) for i,letter in enumerate(''.join(keys),1)]
    for i, page in enumerate(q.pages[1:]):
        extracted = page.extract_text()
        assert re.findall(r'^\s*(\d+)\.', extracted, re.M) == [str(n) for n in range(i*10+1,i*10+11)]
        expected = []
        for part in range(i*2,i*2+2):
            expected.extend(examples[part])
            for lines in scripts[part*5:part*5+5]:
                expected.extend(lines)
        assert re.findall(r'[\u4e00-\u9fff：，、。？！]+[。？！]', extracted) == expected
        assert not re.search(r'[A-Za-zÀ-ž\uac00-\ud7af]', '\n'.join(extracted.splitlines()[1:]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('set_number',type=int,choices=range(1,11))
    parser.add_argument('--output-dir',type=Path,default=Path('output'))
    args = parser.parse_args()
    set_number, out = args.set_number, args.output_dir
    stem = f'HSK3.0_1급_제{set_number:02}회_'
    original = Path('input/sets') / (stem+'표지통일_전체듣기QR.pdf')
    source = PdfReader(original)
    sizes = tuple(map(float,(source.pages[0].mediabox.width,source.pages[0].mediabox.height)))
    keys, scripts = source_answers(source)
    unused = [sorted(set('ABCDEF')-set(keys[i])) for i in (2,4,6)]
    assert all(len(options) == 1 for options in unused)
    unused = [options[0] for options in unused]
    dialogue, reading, word = EXAMPLES[set_number-1]
    listening = [dialogue[:2], dialogue[2:]]
    examples = [['这是一把伞。'], ['你想喝什么？'], list(dialogue[::2]),
                ['我明天去学校。','问：他什么时候去学校？']]
    preview = out/'preview'
    preview.mkdir(parents=True,exist_ok=True)
    problem = out/(stem+'문제지.pdf')
    with pdfium.PdfDocument(original) as rendered:
        write_problem(source, rendered, set_number, sizes, unused, (listening,reading,word), problem)
    write_answer(out, stem, set_number, *sizes, keys, scripts, examples)
    with pdfium.PdfDocument(problem) as result:
        for i,page in enumerate(result,1):
            with closing(page.render(scale=2.2)) as bitmap:
                bitmap.to_pil().save(preview/f'제{set_number:02}회_문제지-{i:02}.png')
    print(set_number, ' '.join(keys), problem.stat().st_size)


if __name__ == '__main__':
    main()
