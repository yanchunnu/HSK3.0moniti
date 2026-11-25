"""Build one HSK 2 sample booklet and answer booklet from the numbered source.

The writing section uses pypinyin to split the source's joined pinyin.
"""
import argparse
import json
from pathlib import Path
import re
import unicodedata
from io import BytesIO

from PIL import Image
import pymupdf as fitz
from pypdf import PdfReader
from pypinyin import Style, pinyin
from pypinyin.seg.mmseg import seg
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas



import zxingcpp

PARTS = ('第一部分','第二部分','第三部分','第四部分')
NAMES = '一二三四五六七八九十'
LISTENING1_EXAMPLE = '这是一辆自行车。'
EXAMPLE3 = ['甲：你今天怎么来学校？','乙：我坐公共汽车来的。','问：他怎么来学校？']
SAMPLE_EXAMPLES = {
    'listening2': ['甲：你在这儿等什么？','乙：我在等公共汽车。'],
    'reading1': '花园里的花开了。',
    'reading2': ['我想喝一杯（D）。','Wǒ xiǎng hē yì bēi (D).'],
    'reading3': ['你最喜欢什么颜色？','Nǐ zuì xǐhuan shénme yánsè?'],
}
SECTIONS = [('听力', [5,10,10], '约17分钟'), ('阅读',[5,5,10,5],'25分钟'),
            ('书写',[5,5],'10分钟')]
BODY_SIZE = 10
PINYIN_SIZE = 7
NUMBER_SIZE = 9
RUBY_OFFSET = 11
ROW_STEP = 24
CELL_WIDTH = 28 / (595.276 / 382)
OPTION_LEFT = 39
OPTION_RIGHT = 352
OPTION_COLUMN = (OPTION_RIGHT - OPTION_LEFT) / 3
OPTION_INSET = 15
RUBY_SCALE = 0.73
HALF_PUNCTUATION = '，。？！、：；（）,.?!:;'
CLOSING_PUNCTUATION = '，。？！、：；）,.?!:;'
HAN = r'[\u3400-\u9fff]'
# The pinyin phrase dictionary omits some compounds whose readings are unambiguous.
COMMON_WORDS = re.compile(r'(昨天|今天|明天|后天|每天|七点半|出门|起床|学校|'
                          r'喜欢|准备|饭馆|经常|周末|上课|学习|星期[一二三四五六日天]|'
                          r'汉语|医生|学生|老师|朋友|什么|怎么|时候|公共汽车)')
PAGE_RANGES = [(1,5),(6,10),(11,15),(16,20),(21,25),(26,30),(31,35),
               (36,40),(41,45),(46,48),(49,50),(51,55),(56,60)]
SECTION_HEADERS = {2: ((6,15),False), 3: ((6,15),True),
                   4: ((16,25),False), 5: ((16,25),True),
                   8: ((36,45),False), 9: ((36,45),True)}

def range_title(question_range,continued=False):
    first,last = question_range
    return f'第{first} - {last}题' + ('（续）' if continued else '')

def answers(source):
    page = source[15].get_text()
    keys = {int(n):a for n,a in re.findall(r'(?<!\d)(\d{2})\s+([A-F])\b', page)}
    writing = page[page.index('56'):page.index('51-55')]
    for n,b in re.findall(r'(5[6-9]|60)(.*?)(?=5[6-9]|60|\Z)',writing,re.S):
        keys[int(n)] = ''.join(re.findall(HAN,b))
    finished = page.split('51-55번 완성 한자:')[1].split('한자 위에는')[0]
    for n,b in re.findall(r'(5[1-5])(.*?)(?=5[1-5]|\Z)',finished,re.S):
        keys[int(n)] += ' / '+''.join(re.findall(HAN,b))
    assert sorted(keys) == list(range(1,61)) and all(keys.values())
    scripts = {}
    for page in source[16:23]:
        content = page.get_text()
        for n,a,b in re.findall(r'(?ms)^(\d+)\.\s*정답\s+([A-F])[^\n]*\n(.*?)(?=^\d+\.\s*정답|\Z)',content):
            n = int(n)
            assert a == keys[n], (n,a,keys[n])
            # Translation follows the transcript. Stop before Korean text or explanatory options.
            b = re.split(r'[가-힣]',b,maxsplit=1)[0]
            clean = ''.join(re.findall(r'[\u3400-\u9fff：，、。？！；]',b))
            if n >= 16:
                clean = clean[re.search(r'[甲乙男女]：',clean).start():]
            scripts[n] = re.findall(r'(?:[甲乙男女问]：)?[^：]+?(?=(?:[甲乙男女问]：)|$)',clean)
            assert scripts[n] and all(line[-1] in '。？！' for line in scripts[n]), (n,clean)
    assert list(scripts) == list(range(1,26)), scripts
    return keys,scripts

def photos(raw,page):
    ops = raw.pages[page].get_contents().operations
    height = float(raw.pages[page].mediabox.height)
    for i in range(len(ops)-5):
        if [op for _,op in ops[i:i+6]] == [b're',b'W*',b'n',b'q',b'cm',b'Do']:
            x,y,w,h = map(float,ops[i][0])
            yield fitz.Rect(x,height-y-h,x+w,height-y)

class Layout:
    def __init__(self,set_number):
        self.set = set_number
        self.buf = BytesIO()
        self.c = canvas.Canvas(self.buf,pagesize=(595.276,841.89))
        self.pages = 0
        self.clips = []
        for name,file in [('CN','simhei.ttf'),('Latin','arial.ttf'),('KR','malgun.ttf')]:
            pdfmetrics.registerFont(TTFont(name,str(Path('C:/Windows/Fonts')/file)))

    def text(self,x,y,value,size=10,font='CN',center=False,color='#17212c'):
        self.c.setFillColor(color)
        self.c.setFont(font,size)
        draw = self.c.drawCentredString if center else self.c.drawString
        draw(x,540-y,value)

    def line(self,x1,y1,x2,y2):
        self.c.setStrokeColor('#a1abb5')
        self.c.setLineWidth(.55)
        self.c.line(x1,540-y1,x2,540-y2)

    def box(self,x,y,w=15,h=15):
        self.c.setStrokeColor('#536173')
        self.c.setLineWidth(.65)
        self.c.rect(x,540-y-h,w,h,stroke=1,fill=0)

    def mark(self,x,y):
        self.c.setStrokeColor('#17513c')
        self.c.setLineWidth(1.2)
        self.c.line(x,540-y,x+3,540-y-3)
        self.c.line(x+3,540-y-3,x+9,540-y+4)

    def begin(self,title='',part='',question_range=None,subheader=None,cover=False,continued=False):
        self.pages += 1
        self.c.saveState()
        self.c.scale(595.276/382,841.89/540)
        if cover:
            return
        if subheader:
            self.text(35,31,subheader,8)
        else:
            self.text(27,24,f'HSK 3.0  •  2급 제{self.set}회 모의고사',8,'KR')
        self.line(27,37 if subheader else 31,355,37 if subheader else 31)
        if title:
            self.text(191,67,title,20,center=True)
        if part:
            self.text(191,89 if title else 65,part,13,center=True)
        if question_range:
            self.text(32,106 if title else 91,range_title(question_range,continued),10)
        self.line(27,509,355,509)
        self.text(191,525,str(self.pages if subheader else self.pages-1),8,'Latin',True)

    def end(self):
        self.c.restoreState()
        self.c.showPage()

    def syllable(self,x,y,value):
        width = pdfmetrics.stringWidth(value,'Latin',PINYIN_SIZE)*RUBY_SCALE
        assert width <= CELL_WIDTH-0.6, (value,width)
        self.c.saveState()
        text = self.c.beginText(x-width/2,540-y)
        text.setFont('Latin',PINYIN_SIZE)
        text.setHorizScale(RUBY_SCALE*100)
        text.setFillColor('#4e5e70')
        text.textOut(value)
        self.c.drawText(text)
        self.c.restoreState()

    def image(self,source,page,clip,x,y,w,h):
        scale = min(w/clip.width,h/clip.height)
        pix = source[page].get_pixmap(matrix=fitz.Matrix(2,2),clip=clip,alpha=False)
        im = Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        im.thumbnail((1200,1200))
        encoded = BytesIO()
        im.save(encoded,'JPEG',quality=85,optimize=True)
        encoded.seek(0)
        self.c.drawImage(ImageReader(encoded),x+(w-clip.width*scale)/2,
                         540-y-(h+clip.height*scale)/2,clip.width*scale,clip.height*scale)

    def save(self,path,source=None):
        self.c.save()
        with fitz.open(stream=self.buf.getvalue(),filetype='pdf') as pdf:
            for target,page,clip,rect in self.clips:
                pdf[target].show_pdf_page(rect,source,page,clip=clip)
            pdf.save(path,garbage=4,deflate=True)

def source_rows(page, start=149, stop=788):
    """Read the source's separately positioned Han and pinyin spans by baseline."""
    baselines = {}
    for block in page.get_text('dict',flags=fitz.TEXTFLAGS_TEXT)['blocks']:
        for line in block['lines']:
            for span in line['spans']:
                x,y = span['origin']
                if start < y < stop and 37 <= x < 558:
                    baselines.setdefault(round(y,1),[]).append(span)
    return [(y,sorted(spans,key=lambda span: span['origin'][0]))
            for y,spans in sorted(baselines.items())]

def source_cells(page, start=149, stop=788, blanks=()):
    ruby = []
    for _,spans in source_rows(page,start,stop):
        if all(span['size'] < 9 for span in spans):
            ruby = spans
            continue
        groups = []
        for span in spans:
            value = span['text']
            x = span['origin'][0]
            if re.fullmatch(r'(?:[A-F]|[0-9]{2}\.)',value.strip()):
                groups.append((value.strip(),[]))
            else:
                if not groups:
                    groups.append(('',[]))
                groups[-1][1].append((x,value if value.strip() else '    '))
        if blanks:
            cells = groups[0][1]
            for blank in blanks:
                if abs(blank.y0-spans[0]['origin'][1]-2) < .2:
                    cells.append((blank.x0,'____'))
            cells.sort()
        syllables = iter(span['text'].strip() for span in ruby)
        for _,cells in groups:
            for index,(x,value) in enumerate(cells):
                syllable = next(syllables) if re.search(HAN,value) or value=='____' else ''
                cells[index] = (value,syllable)
        assert next(syllables,None) is None, (page.number,groups)
        yield groups
        ruby = []

def writing_syllables(word, ruby):
    """Split the printed pinyin at the answer's character boundaries."""
    def plain(value):
        return ''.join(char for char in unicodedata.normalize('NFD',value.lower())
                       if char not in '\u0300\u0301\u0304\u030c')

    remaining = ruby
    syllables = []
    for spellings in pinyin(word,style=Style.NORMAL,heteronym=True,v_to_u=True):
        normalized = {plain(spelling) for spelling in spellings}
        for width in sorted({len(spelling) for spelling in spellings},reverse=True):
            chunk = remaining[:width]
            if plain(chunk) in normalized:
                remaining = remaining[width:]
                if remaining.startswith(("'",'’')):
                    chunk += remaining[0]
                    remaining = remaining[1:]
                syllables.append(chunk)
                remaining = remaining.lstrip()
                break
        else:
            raise ValueError(f'Cannot align {ruby!r} with {word!r}')
    if remaining:
        raise ValueError(f'Extra pinyin in {ruby!r} for {word!r}')
    return syllables

def segment_ruby(run):
    text = ''.join(han[0] for han,_ in run)
    words = []
    for index,part in enumerate(COMMON_WORDS.split(text)):
        if index%2:
            words.append(part)
        else:
            words.extend(seg.cut(part))
    offset = 0
    for word in words:
        end = offset+len(word)
        cells = run[offset:end]
        yield cells
        offset = end

def example_cells(han, ruby=None):
    if ruby is None:
        readings = [part[0] for part in pinyin(han, style=Style.TONE, errors="ignore")]
    else:
        ruby = re.sub(r'[(（][A-F][)）]','',ruby)
        ruby = ''.join(char for char in ruby if char.isalpha() or char in "'’")
        readings = writing_syllables(''.join(re.findall(HAN,han)),ruby)
    syllables = iter(readings)
    return [(char,next(syllables) if re.fullmatch(HAN,char) else '') for char in han]


def grid_words(cells,writing_answer):
    """Keep dictionary words together where possible, preserving source syllables."""
    run = []
    words = []
    for han,py in cells:
        if py and re.fullmatch(HAN+r'[，。？！、：；]*',han):
            run.append((han,py))
            if len(han)==1:
                continue
            words.extend(segment_ruby(run))
            run = []
        else:
            words.extend(segment_ruby(run))
            run = []
            words.append([(han,py)])
    words.extend(segment_ruby(run))

    units = []
    for word in words:
        token = []
        for han,py in word:
            if han == '____':
                token.extend((char,syllable,2,True)
                             for char,syllable in zip(writing_answer,writing_syllables(writing_answer,py)))
                continue
            if not han.strip():
                token.append(('', '', 2, False))
                continue
            # The source prints erhua as one syllable across two Han characters.
            syllables = iter((py[:-1],py[-1:]) if re.match(HAN+'儿',han) and py.endswith('r') else (py,))
            for char in han:
                if char.isspace():
                    continue
                cell = (char,next(syllables,'') if re.fullmatch(HAN,char) else '',
                        1 if char in HALF_PUNCTUATION else 2,False)
                if char in CLOSING_PUNCTUATION and not token and units:
                    units[-1].append(cell)
                else:
                    token.append(cell)
        if token:
            units.append(token)
    return units


def grid_lines(cells,width,writing_answer=''):
    capacity = int(width/(CELL_WIDTH/2)+1e-6)
    lines = [[]]
    used = 0
    for word in grid_words(cells,writing_answer):
        size = sum(cell[2] for cell in word)
        if used and used+size > capacity:
            lines.append([])
            used = 0
        clusters = []
        for cell in word:
            if clusters and cell[0] in CLOSING_PUNCTUATION:
                clusters[-1].append(cell)
            else:
                clusters.append([cell])
        for cluster in clusters:
            size = sum(cell[2] for cell in cluster)
            if used+size > capacity:
                lines.append([])
                used = 0
            lines[-1].extend(cluster)
            used += size
    return lines


def draw_grid(layout,x,y,line,show_answer=False):
    for han,py,units,box in line:
        width = units*CELL_WIDTH/2
        center = x+width/2
        if box:
            layout.box(center-7.5,y-12,15,15)
            if show_answer:
                layout.text(center,y,han,BODY_SIZE,center=True)
        elif han:
            layout.text(center,y,han,BODY_SIZE,center=True)
        if py:
            layout.syllable(center,y-(15 if box else RUBY_OFFSET),py)
        x += width


def draw_cells(layout,x,y,cells,right,writing_answer='',show_answer=False,step=ROW_STEP):
    for index,line in enumerate(grid_lines(cells,right-x,writing_answer)):
        draw_grid(layout,x,y+index*step,line,show_answer)
    return y+index*step


def group_plan(groups,answer_box=False,writing_answer='',*,checked=None):
    if [label for label,_ in groups] == list('ABC'):
        return [(label,OPTION_LEFT+column*OPTION_COLUMN,0,
                 grid_lines(cells,OPTION_COLUMN-OPTION_INSET-(16 if label==checked else 4)))
                for column,(label,cells) in enumerate(groups)]
    if len(groups)>1:
        plan = []
        row = 0
        x = OPTION_LEFT
        for label,cells in groups:
            lines = grid_lines(cells,OPTION_RIGHT-OPTION_LEFT-OPTION_INSET)
            width = max(sum(cell[2] for cell in line) for line in lines)*CELL_WIDTH/2
            if x+OPTION_INSET+width > OPTION_RIGHT:
                row = max(offset+len(lines) for _,_,offset,lines in plan)
                x = OPTION_LEFT
            plan.append((label,x,row,lines))
            x += OPTION_INSET+width+18
        return plan
    label,cells = groups[0]
    return [(label,32,0,grid_lines(cells,(321 if answer_box else 352)-62,writing_answer))]


def draw_groups(layout,y,groups,answer_box=False,step=ROW_STEP):
    return draw_plan(layout,y,group_plan(groups,answer_box),answer_box,step)


def draw_plan(layout,y,plan,answer_box,step):
    for label,x,offset,lines in plan:
        baseline = y+offset*step
        if label:
            layout.text(x,baseline,label,NUMBER_SIZE,'Latin')
        if answer_box:
            layout.box(329,baseline-12)
        for i,line in enumerate(lines):
            draw_grid(layout,62 if x==32 else x+OPTION_INSET,baseline+i*step,line)
    return y+(plan_height(plan)-1)*step


def plan_height(plan):
    return max(offset+len(lines) for _,_,offset,lines in plan)


def draw_checked_options(layout,y,groups,checked):
    plan = group_plan(groups,checked=checked)
    last_y = draw_plan(layout,y,plan,False,ROW_STEP)
    _,x,offset,lines = next(item for item in plan if item[0]==checked)
    used = sum(cell[2] for cell in lines[-1])*CELL_WIDTH/2
    # Leave a grid cell after the last glyph where the column permits it.
    mark_x = min(x+OPTION_INSET+used+CELL_WIDTH-4,x+OPTION_COLUMN-13)
    layout.mark(mark_x,y+(offset+len(lines)-1)*ROW_STEP-3)
    return last_y


def question_blocks(rows):
    block = []
    for groups in rows:
        if groups[0][0].endswith('.') and block:
            yield block
            block = []
        block.append(groups)
    if block:
        yield block


def draw_question_blocks(layout,rows,y,part,heading,*,step=ROW_STEP,gap=0,
                         answer_box=False,writing_keys=None):
    for block in question_blocks(rows):
        plans = []
        for groups in block:
            label = groups[0][0]
            blank = answer_box and label.endswith('.')
            answer = writing_keys[int(label[:-1])] if writing_keys else ''
            plans.append((group_plan(groups,blank,answer),blank))
        height = sum(plan_height(plan) for plan,_ in plans)*step
        if y+height-step > 495:
            layout.end()
            layout.begin(part=part,question_range=heading,continued=True)
            y = 124
        assert y+height-step <= 495, block
        for plan,blank in plans:
            y = draw_plan(layout,y,plan,blank,step)+step
        y += gap


def draw_components(layout,page,y):
    rows = source_rows(page)
    starts = [i-1 for i,(_,row) in enumerate(rows)
              if len(row)==1 and re.fullmatch(r'5[1-5]\.',row[0]['text'])]
    assert len(starts)==5, (page.number,starts)
    for start,stop in zip(starts,starts[1:]+[len(rows)]):
        (_,hint),(baseline,number),(_,ruby),*diagram = rows[start:stop]
        spans = [span for _,row in diagram for span in row if span['text'].strip()]
        choices = sorted((span for span in spans if 170 < span['origin'][0] < 400),
                         key=lambda span: span['origin'][0])
        inside = [span for span in spans if span['origin'][0] < 150]
        arrow, = [span for span in spans if span['text']=='→']
        layout.text(32,y,number[0]['text'],NUMBER_SIZE,'Latin')
        diagram_x = 97
        x = diagram_x
        for span in hint:
            value = span['text']
            font = 'KR' if 'Malgun' in span['font'] else 'Latin'
            size = PINYIN_SIZE if font=='Latin' else NUMBER_SIZE
            layout.text(x,y-4,value,size,font)
            x += pdfmetrics.stringWidth(value,font,size)
        layout.box(diagram_x,y+1,45,32)
        for span in inside:
            sx,sy = span['origin']
            value = span['text']
            font = 'Latin' if value=='?' else 'CN'
            layout.text(diagram_x+5+(sx-84)*.60,y+(sy-baseline)*.49,value,BODY_SIZE,font)
        layout.text(224,y+23,arrow['text'],BODY_SIZE)
        layout.box(316,y+1,35,32)
        groups = [(choices[2*i]['text'].strip(),[(choices[2*i+1]['text'],ruby[i]['text'])])
                  for i in range(3)]
        bottom = draw_groups(layout,y+48,groups)
        y = bottom+20
    assert bottom < 509

def draw_listening1_example(layout):
    c = layout.c
    c.saveState()
    c.setStrokeColor('#38506b')
    c.setLineWidth(1.3)

    # A: clock
    c.circle(114,375,13,stroke=1,fill=0)
    c.line(114,375,114,383)
    c.line(114,375,121,375)

    # B: bicycle
    c.circle(195,370,8,stroke=1,fill=0)
    c.circle(223,370,8,stroke=1,fill=0)
    frame = c.beginPath()
    frame.moveTo(195,370)
    frame.lineTo(202,382)
    frame.lineTo(218,382)
    frame.lineTo(207,370)
    frame.close()
    c.drawPath(frame)
    c.line(207,370,201,386)
    c.line(197,386,205,386)
    c.line(223,370,216,388)
    c.line(216,388,221,388)

    # C: mobile phone
    c.roundRect(294,362,20,27,3,stroke=1,fill=0)
    c.rect(297,369,14,16,stroke=1,fill=0)
    c.line(302,365,306,365)
    c.restoreState()

    for x,label in zip((114,209,304),'ABC'):
        layout.text(x,192,label,NUMBER_SIZE,'Latin',True)
    layout.mark(225,188)

def booklet(source,raw,keys,set_number,output,examples):
    layout = Layout(set_number)
    t,ln = layout.text,layout.line
    url = f'https://yanchunnu.github.io/-/hsk-listening.html?level=2&set={set_number}'
    layout.begin(cover=True)
    # The supplied cover shares the Level 1 design.
    cover = source[0]
    text_hit = cover.search_for('문제 · 정답 · 듣기 대본 · 한국어 해설')
    assert len(text_hit) == 1
    # Cover uses the same trimmed source as the approved Level 1 production.
    layout.clips.append((0,0,cover.rect,cover.rect))
    layout.end()

    layout.begin('考试结构')
    t(191,91,'HSK 3.0（二级）',13,center=True)
    cols = [35,96,167,219,267,347]
    row = 0
    for y in range(117,382,24):
        ln(cols[0],y,cols[-1],y)
    for x in cols:
        ln(x,117,x,381)
    def table_line(y,labels):
        for left,right,label in zip(cols,cols[1:],labels):
            t((left+right)/2,y,str(label),9,center=True)
    table_line(133,['题型','部分','题量','合计','时长'])
    for title,counts,time in SECTIONS:
        for part,count in enumerate(counts):
            table_line(157+24*row,[title,PARTS[part],count,sum(counts) if not part else '',time if not part else ''])
            row += 1
    table_line(373,['总计','九个部分',60,60,'约60分钟'])
    t(35,421,'听力结束后有3分钟填写答题卡。')
    t(35,445,'全部考试约60分钟（含填写个人信息时间5分钟）。')
    layout.end()

    for page,(first,last) in enumerate(PAGE_RANGES,1):
        if page == 6:
            layout.begin()
            ln(47,205,335,205)
            t(191,246,'下面是阅读部分',23,center=True)
            t(191,281,'请在阅读考试开始后作答',19,center=True)
            ln(47,310,335,310)
            layout.end()
        group = 0 if page<=5 else 1 if page<=11 else 2
        part = [0,1,1,2,2,0,1,2,2,3,3,0,1][page-1]
        initial = page in (1,6,12)
        heading,continued = SECTION_HEADERS.get(page,((first,last),False))
        layout.begin(('一、听力','二、阅读','三、书写')[group] if initial else '',
                     PARTS[part],heading,continued=continued)
        if page == 1:
            t(32,119,'听一句话，选择正确图片。',9)
            t(32,131,'例句：'+LISTENING1_EXAMPLE,BODY_SIZE)
            xs = [30,67,162,257,352]
            for x in xs:
                ln(x,137,x,497)
            for y in range(137,498,60):
                ln(xs[0],y,xs[-1],y)
            t(39,168,'例',9)
            draw_listening1_example(layout)
            boxes = list(photos(raw,page))
            assert len(boxes)==15
            for i,clip in enumerate(boxes):
                row,col = divmod(i,3)
                y = 197+row*60
                if col == 0:
                    t(43,y+29,f'{row+1}.',9,'Latin')
                layout.image(source,page,clip,74+95*col,y+2,80,45)
                t(114+95*col,y+56,'ABC'[col],NUMBER_SIZE,'Latin',True)
        elif page in (2,3,6):
            t(32,118 if initial else 107,'选择与句子相符的图片。' if page==6 else '听对话，选择最匹配的图片。',9)
            boxes=list(photos(raw,page))
            assert len(boxes)==6
            for i,clip in enumerate(boxes):
                row,col=divmod(i,2)
                x,y=52+151*col,128+72*row
                layout.image(source,page,clip,x,y,125,57)
                t(x+62,y+65,'ABCDEF'[i],NUMBER_SIZE,'Latin',True)
            unused = (set('ABCDEF')-{keys[i] for i in range(first,last+1)})
            assert len(unused)==1
            if page in (2,6):
                t(32,356,'例',9)
                if page==2:
                    t(62,356,examples['listening2'][0],10)
                    t(62,374,examples['listening2'][1],10)
                else:
                    draw_cells(layout,62,356,example_cells(examples['reading1']),321)
                layout.box(329,343)
                t(336.5,354,unused.pop(),9,'Latin',True)
            if page==6:
                draw_question_blocks(layout,source_cells(source[page],start=442,stop=676),
                                     386,PARTS[part],heading,step=26,answer_box=True)
            else:
                for i,n in enumerate(range(first,last+1)):
                    y=395+i*23
                    t(35,y+11,f'{n}.',9,'Latin')
                    layout.box(329,y)
        else:
            instruction = {4:'听对话和问题，选择正确答案。',5:'听对话和问题，选择正确答案。',
                7:'选择合适的词语填空。',8:'选择与句子相应的回答。',9:'选择与句子相应的回答。',
                10:'阅读短文，选择正确答案。',11:'阅读短文，选择正确答案。',
                12:'选择合适的汉字部件，写出完整的汉字。',13:'根据拼音写出正确的词语。'}
            t(32,120 if initial else 107,instruction[page],9)
            y=135
            if page==4:
                t(32,130,'例',9)
                for i,line in enumerate(EXAMPLE3):
                    t(62,130+i*17,line)
                draw_checked_options(layout,183,[(label,[(han,'')]) for label,han in
                                     zip('ABC',('公共汽车','自行车','地铁'))],'A')
                y=211
            elif page==7:
                y=135
                for groups in source_cells(source[page],stop=232):
                    y = draw_groups(layout,y,groups)+27
                t(32,y,'例',NUMBER_SIZE)
                choice = next(iter(set('ABCDEF')-{keys[i] for i in range(31,36)}))
                assert f'（{choice}）' in examples['reading2'][0]
                y = draw_cells(layout,62,y,example_cells(*examples['reading2']),352)
                y += 34
            elif page==8:
                y=135
                for groups in source_cells(source[page],stop=377):
                    y = draw_groups(layout,y,groups)+ROW_STEP
                unused = set('ABCDEF')-{keys[i] for i in range(36,41)}
                assert len(unused)==1
                t(32,y,'例',NUMBER_SIZE)
                y = draw_cells(layout,62,y,example_cells(*examples['reading3']),321)
                layout.box(329,y-12)
                t(336.5,y-1,unused.pop(),NUMBER_SIZE,'Latin',True)
                y += 31
            elif page==10:
                t(32,133,'例',NUMBER_SIZE)
                example = [
                    [('',list(zip('小李明天坐火车去北京。','Xiǎo Lǐ míng tiān zuò huǒ chē qù Běi jīng'.split()+[''])))],
                    [('',[('问：','wèn'),*zip('小李什么时候去北京？','Xiǎo Lǐ shén me shí hou qù Běi jīng'.split()+[''])])],
                    [(label,list(zip(han,py.split()))) for label,han,py in
                     [('A','今天','jīn tiān'),('B','明天','míng tiān'),('C','后天','hòu tiān')]],
                ]
                for y,groups in zip((133,157),example):
                    draw_groups(layout,y,groups)
                y = draw_checked_options(layout,181,example[-1],'B')+27
            elif page==12:
                t(32,145,'例',NUMBER_SIZE)
                prefix = '日 ＋（月）→ '
                t(62,145,prefix,BODY_SIZE)
                draw_cells(layout,62+pdfmetrics.stringWidth(prefix,'CN',BODY_SIZE),145,[('明','míng')],316)
                layout.box(316,128,35,32)
                t(333.5,148,'明',BODY_SIZE,center=True)
                draw_components(layout,source[page],177)
            elif page==13:
                t(32,146,'例',NUMBER_SIZE)
                draw_cells(layout,62,146,[('____','xuéxiào'),*zip('离我家很近。','lí wǒ jiā hěn jìn'.split()+[''])],
                           352,writing_answer='学校',show_answer=True)
                y=195
            if page in (4,5,7,8,9,10,11,13):
                start = {7:235,8:377}.get(page,149)
                blanks = [d['rect'] for d in source[page].get_drawings()
                          if d['rect'].width>45 and d['rect'].height==0] if page==13 else []
                rows = source_cells(source[page],start=start,blanks=blanks)
                draw_question_blocks(layout,rows,y,PARTS[part],heading,
                                     step=21 if page==10 else ROW_STEP,
                                     gap=31 if page==13 else 7 if page in (4,5,10,11) else 0,
                                     answer_box=page in (8,9),writing_keys=keys if page==13 else None)
        layout.end()

    intermediate = output.with_suffix('.tmp.pdf')
    layout.save(intermediate,source)
    with fitz.open(intermediate) as doc:
        # Redact the obsolete subtitle from the source itself before importing the cover.
        target = doc[0]
        hits=target.search_for('문제 · 정답 · 듣기 대본 · 한국어 해설')
        assert len(hits)==1
        target.add_redact_annot(hits[0],fill=(1,1,1))
        target.apply_redactions(images=0,graphics=0)
        codes = zxingcpp.read_barcodes(Image.frombytes('RGB',
            ((pix:=target.get_pixmap()).width,pix.height),pix.samples))
        if [code.text for code in codes] != [url]:
            raise ValueError([code.text for code in codes])
        found = codes[0].position
        target.insert_link({'kind':fitz.LINK_URI,'uri':url,'from':fitz.Rect(
            found.top_left.x,found.top_left.y,found.bottom_right.x,found.bottom_right.y)})
        doc.save(output,garbage=4,deflate=True)
    intermediate.unlink()
    assert output.stat().st_size <= 5_000_000

def answer_booklet(keys,scripts,set_number,path,examples):
    layout=Layout(set_number)
    t=layout.text
    head=f'HSK 3.0  /  二级  /  第{NAMES[set_number-1]}套'
    layout.begin('答案表',subheader=head)
    n=1
    y=96
    for title,counts,_ in SECTIONS:
        t(35,y,title,13)
        y+=20
        for i,count in enumerate(counts):
            remaining=count
            while remaining:
                t(37,y,PARTS[i] if remaining==count else '',8)
                for x in range(min(remaining,5)):
                    t(99+x*51,y,f'{n:02}  {keys[n]}',8 if 51<=n<=55 else 9)
                    n+=1
                layout.line(35,y+5,347,y+5)
                y+=21
                remaining-=min(remaining,5)
        y+=8
    layout.end()
    chunks = [[0,*range(1,6),-1,*range(6,11)],list(range(11,16)),
              [-1,*range(16,21)],list(range(21,26))]
    for part,numbers in zip([0,1,2,2],chunks):
        layout.begin('听力原文',PARTS[part],subheader=head)
        y=116
        for n in numbers:
            if n==0:
                lines=[LISTENING1_EXAMPLE]
            elif n==-1:
                lines=examples['listening2'] if part==0 else EXAMPLE3
                if part==0:
                    t(35,y,PARTS[1],13)
                    y+=23
            else:
                lines=scripts[n]
            t(36,y,f'{n}.' if n>0 else '例',9)
            for line in lines:
                for start in range(0,len(line),32):
                    t(62,y,line[start:start+32])
                    y+=15
            y+=8
        assert y<510
        layout.end()
    layout.save(path)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('set_number',type=int,choices=range(1,11))
    parser.add_argument('--examples',type=Path,help='JSON with set-specific examples for the unused options')
    args=parser.parse_args()
    if args.set_number != 1 and args.examples is None:
        parser.error('supply --examples for the selected source photos and options')
    examples=json.loads(args.examples.read_text(encoding='utf8')) if args.examples else SAMPLE_EXAMPLES
    n=args.set_number
    stem=f'HSK3.0_2급_제{n:02}회_'
    source_path=Path('input/sets')/(stem+'표지통일_전체듣기QR.pdf')
    out=Path('output')
    preview=out/'preview'
    preview.mkdir(parents=True,exist_ok=True)
    problem=out/(stem+'문제지.pdf')
    answer=out/(stem+'정답및해설.pdf')
    with fitz.open(source_path) as source:
        keys,scripts=answers(source)
        booklet(source,PdfReader(source_path),keys,n,problem,examples)
        answer_booklet(keys,scripts,n,answer,examples)
    for path in (problem,answer):
        with fitz.open(path) as pdf:
            print(path,len(pdf),path.stat().st_size)
            assert path.stat().st_size <= 5_000_000
            for i,page in enumerate(pdf,1):
                pixels=page.get_pixmap(matrix=fitz.Matrix(1.65,1.65))
                label = '문제지' if path==problem else '정답및해설'
                pixels.save(preview/f'제{n:02}회_{label}-{i:02}.png')
                if path==problem:
                    image=Image.frombytes('RGB',(pixels.width,pixels.height),pixels.samples)
                    assert len(zxingcpp.read_barcodes(image))==(1 if i==1 else 0)

if __name__=='__main__':
    main()
