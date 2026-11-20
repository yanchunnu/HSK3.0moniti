from pathlib import Path
from copy import copy
from io import BytesIO
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pypdfium2 as pdfium

root = Path('output')
preview = root / 'preview'
preview.mkdir(parents=True, exist_ok=True)
work = Path('tmp/pdfs')
source_path = next(Path('input/sets').glob('*01*.pdf'))
source = PdfReader(source_path)
W, H = map(float, (source.pages[0].mediabox.width, source.pages[0].mediabox.height))
X, Y = W / 382, H / 540
for name, filename in [('CN','simhei.ttf'),('Latin','arial.ttf'),('KR','malgun.ttf')]:
    pdfmetrics.registerFont(TTFont(name, 'C:/Windows/Fonts/' + filename))

buffer = BytesIO()
c = canvas.Canvas(buffer, pagesize=(W,H))
plans = []
page_no = 0

def text(x,y,value,size=10,font='CN',center=False,color='#17212c'):
    c.setFillColor(color)
    c.setFont(font,size)
    (c.drawCentredString if center else c.drawString)(x,540-y,value)

def line(x1,y1,x2,y2,color='#a1abb5',width=.55):
    c.setStrokeColor(color)
    c.setLineWidth(width)
    c.line(x1,540-y1,x2,540-y2)

def rect(x,y,w,h,color='#536173'):
    c.setStrokeColor(color)
    c.setLineWidth(.65)
    c.rect(x,540-y-h,w,h,stroke=1,fill=0)

def mark(x,y):
    line(x,y,x+3,y+4,'#17513c',1.2)
    line(x+3,y+4,x+9,y-4,'#17513c',1.2)

def pair(x,y,han,pinyin,size=10):
    text(x,y,pinyin,7,'Latin',color='#4e5e70')
    text(x,y+12,han,size)

def number(x,y,n):
    text(x,y,str(n)+'.',9,'Latin')

def crop(n,box,x,y,k=1):
    plans[-1].append((n,box,x,y,k))

def begin(title='',part='',first=None,continuation=False):
    global page_no
    page_no += 1
    plans.append([])
    c.saveState()
    c.scale(X,Y)
    text(27,24,'HSK 3.0  •  1급 제1회 모의고사',8,'KR')
    line(27,31,355,31)
    if title:
        text(191,63,title,20,center=True)
    if part:
        text(191,83 if title else 65,part,13,center=True)
    if first:
        text(32,101 if title else 91,f'第{first}–{first+4}题' + ('（续）' if continuation else ''),11)
    line(27,509,355,509)
    text(191,525,str(page_no),8,'Latin',center=True)

def end():
    c.restoreState()
    c.showPage()

def choice_row(y,values,answer):
    for x,(i,(han,py)) in zip([61,162,264],enumerate(values)):
        text(x-15,y+12,'ABC'[i],8,'Latin')
        pair(x,y,han,py)
        if i==answer:
            mark(x+43,y+7)

def options(n,ys,start,step=68):
    for i,y in enumerate(ys):
        old_y=119+i*step
        number(32,y+15,start+i)
        crop(n,(44,old_y-1,354,old_y+21),44,y)

def image_grid(n,boxes,y,k=.84):
    for i,box in enumerate(boxes):
        col,row=i%2,i//2
        x=87+col*146
        text(x-16,y+row*77+13,'ABCDEF'[i],9,'Latin')
        crop(n,box,x,y+row*77,k)

# Exam structure
begin('考试结构')
text(191,90,'HSK 3.0（一级）',13,center=True)
xs=[40,110,184,235,342]
ys=[117]+[142+24*i for i in range(10)]
for y in ys: line(xs[0],y,xs[-1],y)
for x in xs: line(x,ys[0],x,ys[-1])
for x,label in zip([75,147,209,288],['题型','部分','题量','考试时间']):
    text(x,133,label,10,center=True)
parts=['第一部分','第二部分','第三部分','第四部分']
for i in range(8):
    for x,label in zip([75,147,209,288],['听力' if i<4 else '阅读',parts[i%4],'5',('约12分钟（共）' if i==0 else '20分钟（共）' if i==4 else '')]):
        text(x,158+i*24,label,9,center=True)
for x,label in zip([75,147,209,288],['总计','八个部分','40','约40分钟']):
    text(x,350,label,10,center=True)
text(40,391,'听力结束后，有3分钟填写答题卡。',10)
text(40,411,'全部考试约40分钟（含填写个人信息时间5分钟）。',10)
text(40,451,'듣기 각 파트의 예시는 인쇄용입니다.',9,'KR')
text(40,469,'QR 음원을 재생하면 번호가 있는 문항부터 풀이하세요.',9,'KR')
end()

# Listening 1 - five source rows plus an illustrated example.
begin('一、听力',parts[0],1)
text(32,114,'听录音，选择正确的图片。',9)
text(32,126,'例句：这是一把伞。',9)
text(350,117,'사진 AI 생성',7,'KR',center=True)
xs=[30,67,161,255,352]
ys=[129+i*58 for i in range(7)]
for x in xs: line(x,ys[0],x,ys[-1])
for y in ys: line(xs[0],y,xs[-1],y)
text(40,159,'例如',9)
for i,icon in enumerate(['书','杯子','伞']):
    x=114+94*i
    y=152
    c.setStrokeColor('#38506b')
    c.setLineWidth(1.5)
    if i==0:
        c.roundRect(x-14,540-y-11,28,23,2,stroke=1,fill=0)
        line(x-7,y-11,x-7,y+11,'#38506b',1.4)
        line(x-2,y-4,x+9,y-4,'#38506b',1.1)
    elif i==1:
        c.roundRect(x-11,540-y-11,22,23,3,stroke=1,fill=0)
        c.arc(x+6,540-y-4,x+21,540-y+8,-90,180)
    else:
        c.arc(x-16,540-y-11,x+16,540-y+15,0,180)
        line(x-16,y-2,x+16,y-2,'#38506b',1.3)
        line(x,y-14,x,y+11,'#38506b',1.3)
        c.arc(x-7,540-y-14,x,540-y-7,180,180)
    text(x,180,'ABC'[i],8,'Latin',center=True)
mark(315,177)
for i in range(5):
    y=ys[i+1]
    number(43,y+31,1+i)
    for j,(a,b) in enumerate([(62,139),(165,244),(270,348)]):
        top=98+i*79
        crop(2,(a,top,b,top+66),87+94*j,y+1.3,.69)
        # Allow about 5 pt between the image and the top of the label.
        text(114+94*j,y+55.7,'ABC'[j],8,'Latin',center=True)
end()

# Listening 2
begin(part=parts[1],first=6)
text(32,109,'听问题，选择正确的回答。',9)
text(32,140,'例如',9)
pair(62,130,'你想喝什么？','Nǐ xiǎng hē shénme?')
choice_row(164,[('我想喝茶。','Wǒ xiǎng hē chá.'),('我是老师。','Wǒ shì lǎoshī.'),('今天星期一。','Jīntiān xīngqīyī.')],0)
options(3,[226,281,336,391,446],6)
end()

# Listening 3
begin(part=parts[2],first=11)
text(32,108,'听对话，选择相应的图片。',9)
listen_images=[(47,114,137,203),(152,114,243,203),(258,114,350,203),
               (47,222,137,313),(152,222,243,313),(258,222,350,313)]
image_grid(4,listen_images,117,.72)
text(32,356,'例如',9)
pair(65,344,'女：你在喝茶吗？','Nǚ: Nǐ zài hē chá ma?')
pair(65,371,'男：是的，我在喝茶。','Nán: Shì de, wǒ zài hē chá.')
rect(328,367,16,16)
text(336,379,'B',10,'Latin',center=True)
for i in range(5):
    y=407+i*19
    number(32,y,11+i)
    rect(328,y-11,16,15)
text(54,494,'A–F 중 고르세요. 예시의 B는 본문 정답에 포함되지 않습니다.',7.6,'KR')
end()

# Listening 4
begin(part=parts[3],first=16)
text(32,109,'听句子和问题，选择正确的答案。',9)
text(32,139,'例如',9)
pair(62,128,'我明天去学校。','Wǒ míngtiān qù xuéxiào.')
pair(62,153,'问：他什么时候去学校？','Wèn: Tā shénme shíhou qù xuéxiào?')
choice_row(179,[('今天','Jīntiān'),('明天','Míngtiān'),('星期五','Xīngqīwǔ')],1)
options(5,[233,288,343,398,453],16)
end()

begin()
line(47,205,335,205)
text(191,246,'下面是阅读部分',23,center=True)
text(191,281,'请在阅读考试开始后作答',19,center=True)
line(47,310,335,310)
end()

# Reading 1
begin('二、阅读',parts[0],21)
text(32,117,'选择与句子相符的图片。',9)
reading_images=[(46,108,124,187),(152,108,230,187),(259,108,338,187),
                (46,205,124,285),(152,205,230,285),(259,205,338,285)]
image_grid(6,reading_images,125,.81)
text(32,367,'例如',9)
pair(65,355,'老师在上课。','Lǎoshī zài shàngkè.')
rect(329,351,15,15)
text(337,362,'F',10,'Latin',center=True)
for i in range(5):
    old_y=313+32.7*i
    y=379+i*24
    number(32,y+15,21+i)
    crop(6,(45,old_y,319,old_y+23),58,y,.92)
    rect(329,y+2,15,15)
end()

# Reading 2
begin(part=parts[1],first=26)
text(32,109,'选择与问题相应的回答。',9)
text(32,148,'例如',9)
pair(65,136,'你叫什么名字？','Nǐ jiào shénme míngzi?')
rect(185,137,15,15)
text(192.5,148,'F',10,'Latin',center=True)
for i in range(5):
    old_y=121+66.4*i
    y=200+i*49
    number(32,y+15,26+i)
    crop(7,(41,old_y,170,old_y+24),52,y)
    rect(185,y+3,15,15)
    crop(7,(203,old_y,349,old_y+24),219,y)
pair(234,445,'我叫王明。','Wǒ jiào Wáng Míng.')
text(220,457,'F',8,'Latin')
end()

# Reading 3
begin(part=parts[2],first=31)
text(32,110,'选择合适的词语填空。',9)
crop(8,(26,105,356,145),26,124)
text(32,196,'例如',9)
pair(65,184,'我（F）学校。','Wǒ (F) xuéxiào.')
for i,(top,bottom) in enumerate([(163,185),(223,248),(285,336),(347,371),(408,460)]):
    y=[227,273,319,386,431][i]
    number(32,y+14,31+i)
    crop(8,(44,top,355,bottom),51,y)
end()

# Reading 4
begin(part=parts[3],first=36)
text(32,109,'阅读短文，选择正确的答案。',9)
text(32,140,'例如',9)
pair(62,130,'我妹妹今年七岁。','Wǒ mèimei jīnnián qī suì.')
pair(62,155,'★ 我妹妹几岁？','Wǒ mèimei jǐ suì?')
choice_row(184,[('五岁','Wǔ suì'),('七岁','Qī suì'),('九岁','Jiǔ suì')],1)
bands=[(98,166),(176,245),(255,325),(334,405),(413,485)]
for i,y in enumerate([226,314,402]):
    number(32,y+15,36+i)
    crop(9,(44,bands[i][0],354,bands[i][1]),48,y)
end()

begin(part=parts[3],first=36,continuation=True)
for i,y in enumerate([119,222],start=3):
    number(32,y+15,36+i)
    crop(9,(44,bands[i][0],354,bands[i][1]),48,y)
end()

# Answer sheet and globally numbered answer key
keys=['ABCBA','CABCB','EAFCD','BCABC','BEACD','CEABD','DCBEA','BACBA']
begin('答题卡')
text(35,96,'姓名 ____________________    日期 ____________________',11)
for x,title in [(38,'听力  1–20'),(210,'阅读  21–40')]:
    text(x,123,title,13)
for base in (0,20):
    x=38 if base==0 else 210
    for i in range(20):
        y=157+i*16.4
        n=base+i+1
        number(x,y,n)
        for j,letter in enumerate('ABCDEF' if n in range(11,16) or n in range(21,36) else 'ABC'):
            xx=x+26+j*19
            c.setStrokeColor('#566478')
            c.setLineWidth(.5)
            c.circle(xx,540-y+3,5.8,stroke=1,fill=0)
            text(xx,y-.5,letter,6,'Latin',center=True)
end()

begin()
# Korean title uses its own font over the default title region.
c.setFillColor('#ffffff')
c.rect(75,540-72,232,32,stroke=0,fill=1)
text(191,63,'정답 및 해설',20,'KR',center=True)
for i,key in enumerate(keys):
    y=114+i*39
    if i==4:
        line(36,y-23,346,y-23)
    text(37,y,('듣기 ' if i<4 else '독해 ')+str(i%4+1)+'부',10,'KR')
    for j,answer in enumerate(key):
        text(118+j*47,y,f'{5*i+j+1}  {answer}',10,'Latin')
text(36,450,'뒤쪽 원본 해설의 각 부 1–5번은 위 연속 번호에 대응합니다.',8.5,'KR')
text(36,470,'예시는 채점 대상에서 제외합니다.',8.5,'KR')
end()

c.save()
base = PdfReader(buffer)
writer = PdfWriter()
writer.add_page(source.pages[0])
for page,clips in zip(base.pages,plans):
    page = writer.add_page(page)
    for n,(left,top,right,bottom),x,y,k in clips:
        patch = copy(source.pages[n-1])
        m=patch.mediabox
        sx,sy=float(m.width)/382,float(m.height)/540
        box=RectangleObject([left*sx,(540-bottom)*sy,right*sx,(540-top)*sy])
        patch.cropbox=box
        patch.trimbox=box
        transform=(Transformation().translate(-left*sx,-(540-top)*sy)
                   .scale(k*X/sx,k*Y/sy).translate(x*X,(540-y)*Y))
        page.merge_transformed_page(patch,transform)
    page.compress_content_streams()
for p in source.pages[9:]:
    writer.add_page(p)
writer.add_metadata({'/Title':'HSK 3.0 1급 제01회 모의고사 재배열'})
writer.compress_identical_objects(remove_duplicates=True,remove_unreferenced=True)
target=root/'HSK3.0_1급_제01회_재배열.pdf'
with target.open('wb') as f:
    writer.write(f)

pdf=pdfium.PdfDocument(target)
assert len(pdf)==1+len(plans)+13
for i,page in enumerate(pdf):
    im=page.render(scale=1.38).to_pil()
    im.save(work/f'final-{i+1:02}.png')
for i,name in [(0,'표지'),(2,'듣기'),(7,'독해')]:
    pdf[i].render(scale=2.2).to_pil().save(preview/f'{name}.png')

