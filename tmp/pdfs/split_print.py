from pathlib import Path
import hashlib
import re
from io import BytesIO
from PIL import Image, ImageOps, ImageDraw
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import pypdfium2 as pdfium

out = Path('output')
work = Path('tmp/pdfs')
stem = 'HSK3.0_1급_제01회_'
original_hashes = {p: hashlib.sha256(p.read_bytes()).digest() for p in Path('input').rglob('*.pdf')}
original = next(Path('input/sets').glob('*01*.pdf'))
src_render = pdfium.PdfDocument(original)
build = (work / 'build.py').read_text(encoding='utf-8-sig').split('# Answer sheet and globally numbered answer key')[0]
build = '\n'.join(row for row in build.splitlines() if "'사진 AI 생성'" not in row and '填写答题卡' not in row)
# Rebuild existing overlays and embed only the visible source regions.
exec(build)
assert len(plans) == 11
c.save()
overlay_reader = PdfReader(buffer)
writer = PdfWriter()
cover = writer.add_page(source.pages[0])
assert '문제 · 정답 · 듣기 대본 · 한국어 해설' in cover.extract_text()
contents = cover.get_contents()
assert contents.operations[46][1] == b'Tj'
del contents.operations[46]
cover.replace_contents(contents)
assert '한국어 해설' not in cover.extract_text()
for overlay, clips in zip(overlay_reader.pages, plans):
    page = writer.add_page(overlay)
    if not clips:
        continue
    patch_bytes = BytesIO()
    patch_canvas = canvas.Canvas(patch_bytes, pagesize=(W,H))
    for n, (left, top, right, bottom), x, y, k in clips:
        source_page = src_render[n-1]
        sx, sy = source_page.get_width()/382, source_page.get_height()/540
        clip = source_page.render(scale=5, crop=(left*sx, (540-bottom)*sy, (382-right)*sx, top*sy)).to_pil()
        patch_canvas.drawImage(ImageReader(clip), x*X, (540-y-(bottom-top)*k)*Y,
                               (right-left)*k*X, (bottom-top)*k*Y)
    patch_canvas.save()
    page.merge_page(PdfReader(patch_bytes).pages[0])
writer.add_metadata({'/Title': 'HSK 3.0 1급 제01회 문제지'})
problem = out / (stem + '문제지.pdf')
writer.write(problem)

key_text = source.pages[9].extract_text().replace('\n','')
keys = re.findall(r'第[一二三四]部分([A-F]{5})', key_text)
assert keys == 'ABCBA CABCB EAFCD BCABC BEACD CEABD DCBEA BACBA'.split()
scripts = []
for idx in range(10,16):
    flat = source.pages[idx].extract_text().replace('\n','')
    chunks = re.split(r'([1-5]) +정답 +([A-F])', flat)[1:]
    for local, answer, block in zip(chunks[::3], chunks[1::3], chunks[2::3]):
        pos = len(scripts)
        assert int(local) == pos % 5 + 1 and answer == ''.join(keys)[pos]
        lines = re.findall(r'[\u4e00-\u9fff：，、。？！]+[。？！]', block)
        assert len(lines) == (1 if pos < 10 else 2)
        scripts.append(lines)
assert len(scripts) == 20
examples = [
    ['这是一把伞。'], ['你想喝什么？'],
    ['女：你在喝茶吗？','男：是的，我在喝茶。'],
    ['我明天去学校。','问：他什么时候去学校？'],
]
answer_path = out / (stem + '정답및해설.pdf')
a = canvas.Canvas(str(answer_path), pagesize=(W,H))
a.setTitle('HSK 3.0 1급 제01회 정답 및 해설')

def write(x, y, content, size=14, font='CN'):
    a.setFillColor('#171717')
    a.setFont(font,size)
    a.drawString(x,H-y,content)

def rule(y, color='#b9b9b9'):
    a.setStrokeColor(color)
    a.setLineWidth(.55)
    a.line(54,H-y,W-54,H-y)

def header(title, page):
    write(54,48,'HSK 3.0  /  一级  /  第一套',11)
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

p = PdfReader(problem)
assert len(p.pages) == 12
for page in p.pages:
    flat = ''.join(page.extract_text().split())
    assert not re.search(r'사진[:：]?AI생성|答题卡|답안카드|한국어해설',flat)
assert not p.get_fields()
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
assert all(hashlib.sha256(p.read_bytes()).digest()==digest for p,digest in original_hashes.items())

preview = out / 'preview'
for path, label in [(problem,'문제지'),(answer_path,'정답및해설')]:
    doc = pdfium.PdfDocument(path)
    for i,page in enumerate(doc,1):
        page.render(scale=2.2).to_pil().save(preview / f'{label}-{i:02}.png')

def sheet(files, name, cols, thumb):
    rows = (len(files)+cols-1)//cols
    w,h = thumb
    sheet = Image.new('RGB',(cols*(w+8),rows*(h+24)),'#dddddd')
    draw = ImageDraw.Draw(sheet)
    for i,f in enumerate(files):
        x,y = i%cols*(w+8),i//cols*(h+24)
        with Image.open(f) as img:
            sheet.paste(ImageOps.contain(img,thumb),(x,y+18))
        draw.text((x+2,y+3),str(i+1),fill='black')
    sheet.save(work / name)
sheet(sorted(preview.glob('문제지-*.png'))[:6],'check-problem-1.png',3,(385,544))
sheet(sorted(preview.glob('문제지-*.png'))[6:],'check-problem-2.png',3,(385,544))
sheet(sorted(preview.glob('정답및해설-*.png')),'check-answer.png',3,(460,651))

