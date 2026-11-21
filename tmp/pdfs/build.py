"""Approved problem booklet layout, in normalized 382 × 540 coordinates."""
from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PARTS = ['第一部分','第二部分','第三部分','第四部分']


def build(set_number, W, H, bands, pictures, unused, example):
    X, Y = W / 382, H / 540
    for name, filename in [('CN','simhei.ttf'),('Latin','arial.ttf'),('KR','malgun.ttf')]:
        pdfmetrics.registerFont(TTFont(name, 'C:/Windows/Fonts/' + filename))
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(W,H))
    plans = []
    page_no = 0
    parts = PARTS
    listening_example, reading_example, word_example = example
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

    def crop(n,box,x,y,k=1,photo=False):
        plans[-1].append((n,box,x,y,k,photo))

    def begin(title='',part='',first=None,continuation=False):
        nonlocal page_no
        page_no += 1
        plans.append([])
        c.saveState()
        c.scale(X,Y)
        text(27,24,f'HSK 3.0  •  1급 제{set_number}회 모의고사',8,'KR')
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

    def options(n,ys,start):
        for i,(y,(top,bottom)) in enumerate(zip(ys, bands(n))):
            number(32,y+15,start+i)
            crop(n,(44,top,354,bottom),44,y)

    def image_grid(n,y,k):
        for i,box in enumerate(pictures(n)):
            col,row=i%2,i//2
            x=87+col*146
            text(x-16,y+row*77+13,'ABCDEF'[i],9,'Latin')
            crop(n,box,x,y+row*77,k,photo=True)

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
    text(40,411,'全部考试约40分钟（含填写个人信息时间5分钟）。',10)
    text(40,451,'듣기 음원에는 각 부분의 예시가 포함되어 있습니다.',9,'KR')
    text(40,469,'표지 QR을 스캔해 전체 듣기 또는 부분별 듣기를 재생하세요.',9,'KR')
    end()

    # Listening 1 - five source rows plus an illustrated example.
    begin('一、听力',parts[0],1)
    text(32,114,'听录音，选择正确的图片。',9)
    text(32,126,'例句：这是一把伞。',9)
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
    listen_one = pictures(2)
    for i in range(5):
        y=ys[i+1]
        number(43,y+31,1+i)
        for j,box in enumerate(listen_one[i*3:i*3+3]):
            left,top,right,bottom = box
            x = 114+94*j
            crop(2,box,x-(right-left)*.69/2,y+1.3,.69,photo=True)
            text(x, y+1.3+(bottom-top)*.69+9.4, 'ABC'[j], 8, 'Latin', center=True)
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
    image_grid(4,117,.72)
    text(32,356,'例如',9)
    for y, (han, py) in zip((344, 371), listening_example):
        pair(65,y,han,py)
    rect(328,367,16,16)
    text(336,379,unused[0],10,'Latin',center=True)
    for i in range(5):
        y=407+i*19
        number(32,y,11+i)
        rect(328,y-11,16,15)
    text(54,494,f'A–F 중 고르세요. 예시의 {unused[0]}는 본문 정답에 포함되지 않습니다.',7.6,'KR')
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
    image_grid(6,125,.81)
    text(32,367,'例如',9)
    pair(65,355,*reading_example)
    rect(329,351,15,15)
    text(337,362,unused[1],10,'Latin',center=True)
    for i,(top,bottom) in enumerate(bands(6)):
        y=379+i*24
        number(32,y+15,21+i)
        crop(6,(45,top,319,bottom),58,y,.92)
        rect(329,y+2,15,15)
    end()

    # Reading 2
    begin(part=parts[1],first=26)
    text(32,109,'选择与问题相应的回答。',9)
    text(32,148,'例如',9)
    pair(65,136,'你叫什么名字？','Nǐ jiào shénme míngzi?')
    rect(185,137,15,15)
    text(192.5,148,'F',10,'Latin',center=True)
    for i,(top,bottom) in enumerate(bands(7)):
        y=200+i*49
        number(32,y+15,26+i)
        crop(7,(41,top,170,bottom),52,y)
        rect(185,y+3,15,15)
        crop(7,(203,top,349,bottom),219,y)
    pair(234,445,'我叫王明。','Wǒ jiào Wáng Míng.')
    text(220,457,'F',8,'Latin')
    end()

    # Reading 3
    begin(part=parts[2],first=31)
    text(32,110,'选择合适的词语填空。',9)
    crop(8,(26,105,356,145),26,124)
    text(32,196,'例如',9)
    pair(65,184,*word_example)
    for i,(top,bottom) in enumerate(bands(8)):
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
    reading_bands=bands(9)
    for i,y in enumerate([226,314,402]):
        number(32,y+15,36+i)
        crop(9,(44,reading_bands[i][0],354,reading_bands[i][1]),48,y)
    end()

    begin(part=parts[3],first=36,continuation=True)
    for i,y in enumerate([119,222],start=3):
        number(32,y+15,36+i)
        crop(9,(44,reading_bands[i][0],354,reading_bands[i][1]),48,y)
    end()
    c.save()
    return buffer, plans


if __name__ == '__main__':
    from split_print import main
    main()
