"""Build the A3 review drawing pack from saved CAD projections and verified previews.
First run export_drawing_geometry.py with FreeCAD Python; this script uses ReportLab.
No CAD geometry is edited. The output is a design review pack, not shop drawings.
"""
import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageChops
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'tmp/pdfs'
MODEL=ROOT/'hardware/model'
PDF=MODEL/'CyberTrack-assembly-and-service.pdf'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
meta=json.loads((DATA/'dimensions.json').read_text())
report=json.loads((MODEL/'readback.json').read_text())
assert sha(MODEL/'CyberTrack.FCStd')==meta['source_sha256'], 'Stale CAD projections'
# A stale PNG must never silently be packaged with a newer CAD drawing.
for rel,digest in report['files_sha256'].items():
    path=ROOT/rel
    if not path.exists(): path=MODEL/Path(rel).name
    assert sha(path)==digest, f'Stale model artifact: {path}'
assert report['design_revision']=='0.8', 'Review annotations for a new model revision'
# Guard dimension callouts that describe named features, not just overall extents.
expected = {
    'PowerBank': [-60,-96,33,60,-23,64.5],
    'ElectronicsTray': [-59,-74,144.5,59,10,145.5],
    'WaterFillPlug': [-30.8,42.2,124.3,-17.2,55.8,128],
    'WaterFillSeal': [-33,40,127.6,-15,58,128],
}
for name, values in expected.items():
    assert all(abs(a-b)<1e-5 for a,b in zip(meta['objects'][name]['bbox'],values)), name
for prefix, xs, ys in [('BatteryScrew',[-63.5,63.5],[-85,-34]),
                       ('CrownScrew',[-64,64],[-52,7]),
                       ('TrayScrew',[-55,55],[-30,0])]:
    centres=[]
    for name,obj in meta['objects'].items():
        if name.startswith(prefix):
            b=obj['bbox'];centres.append(((b[0]+b[3])/2,(b[1]+b[4])/2))
    assert len(centres)==4 and all(any(abs(x-ex)<1e-6 and abs(y-ey)<1e-6
        for ex in xs for ey in ys) for x,y in centres), prefix
font='/System/Library/Fonts/STHeiti Light.ttc'
pdfmetrics.registerFont(TTFont('ZH',font,subfontIndex=0))
pdfmetrics.registerFont(TTFont('ZHB','/System/Library/Fonts/STHeiti Medium.ttc',subfontIndex=0))
U=72/25.4
INK='#1E303B'; MUTED='#536673'; ACCENT='#DF632B'; PALE='#EAF0F2'; BLUE='#287E96'
c=canvas.Canvas(str(PDF),pagesize=(420*U,297*U),pageCompression=1)
c.setTitle('CyberTrack 0.8 模型与装配图纸')
c.setAuthor('CyberTrack')
c.setSubject('A3 design review drawings; dimensions in mm; not manufacturing release')
page=0

def text(x,y,s,size=10,color=INK,bold=False,align='left'):
    c.setFillColor(color);c.setFont('ZHB' if bold else 'ZH',size)
    getattr(c,{'left':'drawString','center':'drawCentredString','right':'drawRightString'}[align])(x*U,y*U,s)
def line(x1,y1,x2,y2,color=INK,width=.4,dash=None):
    c.setStrokeColor(color);c.setLineWidth(width)
    c.setDash(dash or [])
    c.line(x1*U,y1*U,x2*U,y2*U);c.setDash([])
def box(x,y,w,h,fill=None):
    c.setStrokeColor('#CAD5DB');c.setLineWidth(.4)
    if fill:c.setFillColor(fill)
    c.rect(x*U,y*U,w*U,h*U,stroke=1,fill=bool(fill))
def para(x,y,s,width=105,size=10,leading=6):
    current=''
    for ch in s:
        if ch=='\n' or pdfmetrics.stringWidth(current+ch,'ZH',size)>width*U:
            text(x,y,current,size);y-=leading;current=''
        if ch!='\n':current+=ch
    if current:text(x,y,current,size);y-=leading
    return y

def header(title,subtitle):
    global page
    page+=1
    c.setFillColor(INK);c.rect(0,278*U,420*U,19*U,fill=1,stroke=0)
    text(14,285,'CYBERTRACK',18,'#FFFFFF',True)
    text(405,285,f'CT-08 / {page:02d}',11,'#FFFFFF',align='right')
    text(14,265,title,21,bold=True);text(14,256,subtitle,10,MUTED)
    line(14,250,406,250,'#CAD5DB',.6)
    line(14,20,406,20,'#CAD5DB',.6)
    text(14,13,'模型与装配评审图 | Rev 0.8 | 2026-10-23 | 单位：mm',9,MUTED)
    text(406,13,f'未制造放行 · A3 横向 · {page} / 9',9,MUTED,align='right')
def end():c.showPage()
def title(x,y,s,sub=''):
    text(x,y,s,12,bold=True)
    if sub:text(x,y-7,sub,9,MUTED)
def note(x,y,s):return para(x,y,s,180,9,5)

def picture(name,x,y,w,h):
    im=Image.open(MODEL/name).convert('RGB')
    crop=ImageChops.difference(im,Image.new('RGB',im.size,'white')).getbbox()
    im=im.crop(crop)
    ratio=min(w/im.width,h/im.height)
    dw,dh=im.width*ratio,im.height*ratio
    ox,oy=x+(w-dw)/2,y+(h-dh)/2
    c.drawImage(ImageReader(im),ox*U,oy*U,dw*U,dh*U)
    # Return a mapping for callouts referenced to the original, verified image.
    return lambda px,py:(ox+(px-crop[0])*ratio,oy+(crop[3]-py)*ratio)

def drawing(key,cx,cy,scale=1):
    d=json.loads((DATA/f'{key}.json').read_text())
    assert d['source_sha256']==meta['source_sha256'] and d['projection_revision']==2, f'Stale projection: {key}'
    b=d['bounds']
    mx,my=(b[0]+b[2])/2,(b[1]+b[3])/2
    def pt(x,y):return (cx+(x-mx)*scale,cy+(y-my)*scale)
    c.setStrokeColor(INK);c.setLineWidth(.35)
    for path in d['paths']:
        if len(path)<2:continue
        p=c.beginPath();x,y=pt(*path[0]);p.moveTo(x*U,y*U)
        for v in path[1:]:
            x,y=pt(*v);p.lineTo(x*U,y*U)
        c.drawPath(p)
    return pt,b

def arrow(x,y,angle,color=BLUE):
    a=math.radians(angle);r=1.7
    line(x,y,x-r*math.cos(a-.4),y-r*math.sin(a-.4),color,.55)
    line(x,y,x-r*math.cos(a+.4),y-r*math.sin(a+.4),color,.55)
def hdim(p,x1,x2,y1,y2,yd,label):
    a,b=p(x1,y1),p(x2,y2);dy=p(0,yd)[1]
    line(a[0],a[1],a[0],dy+2,BLUE,.3);line(b[0],b[1],b[0],dy+2,BLUE,.3)
    line(a[0],dy,b[0],dy,BLUE);arrow(a[0],dy,180);arrow(b[0],dy,0)
    text((a[0]+b[0])/2,dy+1.7,label,9,BLUE,align='center')
def vdim(p,y1,y2,x1,x2,xd,label):
    a,b=p(x1,y1),p(x2,y2);dx=p(xd,0)[0]
    line(a[0],a[1],dx-2,a[1],BLUE,.3);line(b[0],b[1],dx-2,b[1],BLUE,.3)
    line(dx,a[1],dx,b[1],BLUE);arrow(dx,a[1],270);arrow(dx,b[1],90)
    c.saveState();c.translate((dx-1.8)*U,((a[1]+b[1])/2)*U);c.rotate(90)
    text(0,0,label,9,BLUE,align='center');c.restoreState()
def leader(point,x,y,label):
    px,py=point;line(px,py,x-2,y-1,ACCENT,.6)
    c.setFillColor(ACCENT);c.circle(px*U,py*U,.8*U,fill=1,stroke=0)
    text(x,y,label,10,INK)
def badge(point,n):
    x,y=point;c.setFillColor(ACCENT);c.circle(x*U,y*U,3.4*U,fill=1,stroke=0)
    text(x,y-1.2,str(n),10,'#FFFFFF',True,'center')
def bbox(name):return meta['objects'][name]['bbox']
def dim(name,axis):
    b=bbox(name);return b[axis+3]-b[axis]
def f(v):return f'{v:.2f}'.rstrip('0').rstrip('.')

header('模型总览与图纸索引','保留已认可的机甲造型、头身比例与低位电源布局；以保存的原生模型为几何依据。')
picture('assembly.png',12,79,192,167)
picture('rear-assembly.png',214,79,192,167)
text(108,72,'前方轴测 / 前方为 -Y',11,align='center');text(310,72,'后方轴测 / 背包与补液盖',11,align='center')
box(14,29,392,33,PALE)
text(20,51,'228 × 202.5 × 203',20,bold=True)
text(20,37,'整机宽 × 长 × 高；模型几何外包络',9,MUTED)
text(143,52,'图纸内容',11,bold=True)
para(143,44,'02 正面 / 背面　03 左右侧视　04 俯视 / 底视　05 电源检修\n06 头舱检修　07 补液结构　08 总装爆炸　09 走线与装配',250,9,6)
end()

header('正面与背面 · 主要外形尺寸','各视图独立标识观察方向；尺寸为模型几何值。矢量线稿使用遮挡线消隐，未显示隐藏线。')
p,b=drawing('front',111,160,2/3)
title(28,239,'正面','沿 +Y 观察；右侧为 +X / 机体左侧；比例 1:1.5')
hdim(p,b[0],b[2],b[1],b[1],b[1]-15,f(b[2]-b[0]))
vdim(p,b[1],b[3],b[0],b[0],b[0]-14,f(b[3]-b[1]))
hdim(p,-89.5,89.5,168,168,222,'179 含侧耳')
p,b=drawing('rear',310,160,2/3)
title(227,239,'背面','沿 -Y 观察；左侧为 +X / 机体左侧；比例 1:1.5')
hdim(p,b[0],b[2],b[1],b[1],b[1]-15,f(b[2]-b[0]))
leader(p(-24,131),232,165,'左舱补液盖')
leader(p(24,131),350,165,'右舱补液盖')
box(14,29,392,38,PALE)
para(20,56,'尺寸依据：整机最大宽度 228；整体高度 203；两侧耳部总宽 179。\n这些数值描述当前 CAD 外形，不含制造公差、线缆外伸、真实接头或变形。',210,10,7)
para(247,56,'坐标：+X 向左，+Y 向后，+Z 向上。\nZ=0 为当前履带最低几何平面。\n颈架为固定结构；圆形装饰不代表活动关节。',150,9,6)
end()

header('左右侧视 · 布局比例','保持前下方平放电源，头部与背包的外形比例沿用当前模型。')
p,b=drawing('side',110,157,2/3)
title(28,239,'左侧视图','沿 -X 观察；前方在左；比例 1:1.5')
hdim(p,b[0],b[2],b[1],b[1],b[1]-16,f(b[2]-b[0]))
vdim(p,b[1],b[3],b[2],b[2],b[2]+15,f(b[3]-b[1]))
# Exact allocated battery silhouette, dashed because it is inside the shell.
ps=bbox('PowerBank');pts=[p(ps[1],ps[2]),p(ps[4],ps[2]),p(ps[4],ps[5]),p(ps[1],ps[5])]
for a,bb in zip(pts,pts[1:]+pts[:1]):line(*a,*bb,ACCENT,.65,[3,2])
leader(p(-60,49),35,82,'充电宝低位包络（虚线）')
p,b=drawing('right',312,157,2/3)
title(228,239,'右侧视图','沿 +X 观察；前方在右；比例 1:1.5')
hdim(p,b[0],b[2],b[1],b[1],b[1]-15,f(b[2]-b[0]))
vdim(p,b[1],b[3],b[2],b[2],b[2]+15,f(b[3]-b[1]))
box(14,29,392,35,PALE)
para(20,53,'电源定位：X = -60…60；Y = -96…-23；Z = 33…64.5。\n120 沿 X、73 沿 Y、31.5 沿 Z；包络几何中心高度 48.75，不是实测质心。',240,10,7)
para(278,53,'头部壳体最大宽 164。\n底部前舱下部宽 132。\n全图以尺寸数字为准，禁止量图加工。',120,9,6)
end()

header('俯视与底视 · 装配位置','六向视图采用相同坐标基准；俯视与底视的左右方向不同，前方均位于图面下方。')
p,b=drawing('top',110,159,2/3)
title(28,239,'俯视图','沿 -Z 观察；+X 在右；比例 1:1.5')
hdim(p,b[0],b[2],b[1],b[1],b[1]-15,f(b[2]-b[0]))
vdim(p,b[1],b[3],b[2],b[2],b[2]+15,f(b[3]-b[1]))
p,b=drawing('bottom',312,159,2/3)
title(230,239,'底视图','沿 +Z 观察；+X 在左；比例 1:1.5')
hdim(p,b[0],b[2],b[1],b[1],b[1]-15,f(b[2]-b[0]))
vdim(p,b[1],b[3],b[2],b[2],b[2]+15,f(b[3]-b[1]))
box(14,29,392,35,PALE)
para(21,53,'俯视：后方两个补液盖独立拆卸；中部冠盖与顶甲整体上取。\n底视：前部大托盖承托电源；中部小检修盖用于先断开电源插头。',240,10,7)
para(279,53,'整机宽 228；长 202.5。\n底部维护前须垫高并托住电源。\n维护动作与固定点见后续详图。',120,9,6)
end()

header('电源托盖与底部检修','充电宝：用户提供 120 × 73 × 31.5；长侧面的输出口在设计中朝后（+Y），具体端口位置待实测。')
title(24,239,'底视总装','沿 +Z 观察；后方在上；比例 1:2')
p,b=drawing('bottom',85,169,.5)
leader(p(0,-59),18,104,'A 电源托盖：4 处紧固')
leader(p(0,0),115,223,'B 插头检修小盖')
title(185,239,'托盖与电源包络','底视，前方在下；比例 1:1')
p,b=drawing('battery',278,181,1)
pts=[p(-60,-96),p(60,-96),p(60,-23),p(-60,-23)]
for a,bb in zip(pts,pts[1:]+pts[:1]):line(*a,*bb,ACCENT,.55,[3,2])
hdim(p,-60,60,-96,-96,-110,'120 电源')
vdim(p,-96,-23,60,60,76,'73 电源')
hdim(p,-63.5,63.5,-34,-34,-14,'127 孔距')
vdim(p,-85,-34,-63.5,-63.5,-78,'51 孔距')
text(211,117,'4 孔中心：X±63.5；Y=-85 / -34；虚线为电源',9,MUTED)
title(25,87,'拆装顺序')
para(25,76,'1. 断电并垫高整机；先拆 B 的 2 颗螺钉。\n2. 经检修口拔下电源线，再托住电源和托盖。\n3. 拆 A 的 4 颗螺钉，将整组向下移出 60。\n4. 装回后检查拉带、线缆夹持与螺钉紧固。',160,10,7)
box(198,29,208,72,PALE)
para(205,90,'检修开口：30 × 33；后隔板连接窗口：40 × 23。\n电源托盖厚 3；四个承托垫将电源支承在 Z=33。\n向下 60 为已采样的移出位移，托盖最低达到 Z=-32；\n实际垫高还须增加手部、工具和安全承托空间。\n螺钉、嵌件、孔径和拉带均为候选，未作加工放行。\n插头窗口居中仅为假设，需实物确认可达与拔插。',194,9,7)
end()

header('头舱冠盖与电子托板','整体冠盖上取；中央顶甲随冠盖拆装。真实板卡孔位、绝缘柱、天线与插头净空仍待整合。')
title(25,239,'整体冠盖俯视','4 处紧固；比例 1:1')
p,b=drawing('crown',109,165,1)
hdim(p,-64,64,7,7,39,'128 孔距')
vdim(p,-52,7,64,64,94,'59 孔距')
text(29,94,'孔中心：X±64；Y=-52 / 7',9,MUTED)
title(249,239,'共用托板俯视','4 处紧固；比例 1:1')
p,b=drawing('tray',316,165,1)
hdim(p,-59,59,-39,-39,-88,f(dim('ElectronicsTray',0))+' 外宽')
hdim(p,-55,55,0,0,28,'110 孔距')
vdim(p,-30,0,55,55,72,'30 孔距')
text(253,94,'孔中心：X±55；Y=-30 / 0；板厚 1',9,MUTED)
box(14,29,392,54,PALE)
para(21,72,'冠盖：卸下 4 颗顶面螺钉，整组上提 65；外壳分缝为 Z181…181.25，间隙 0.25。\n托板：先移去冠盖，断开线束与邻近软管，再卸下 4 颗螺钉，上提 85。',376,10,7)
para(21,50,'电子区 100 × 45 × 34、音频区 72 × 36 × 21 均为空间分配，不是实测设备外形。\n冠盖饰片在 CAD 中分对象表达，一体成形或定位固定工艺未定；头部造型不在本图纸中重设计。',376,9,7)
end()

header('背包补液结构 · 局部分解','两侧独立补液；以右侧喷水舱展示层次，左侧泡泡舱采用对应结构。示意分解间距不代表装配高度。')
# Individual parts are drawn at true scale, independently spaced for legibility.
entries=[('fill_lid',49,220,'01 外盖与把手'),('fill_plug',49,174,'02 导向塞'),('fill_seal',49,143,'03 端面密封垫'),('fill_cap',49,103,'04 内舱盖与补液孔')]
for key,cx,cy,label in entries:
    p,b=drawing(key,102,cy,1.7)
    text(155,cy,label,11,bold=True)
    line(143,cy,153,cy,ACCENT,.6)
    if key=='fill_plug':hdim(p,42.2,55.8,124.3,124.3,119.5,'Ø13.6 候选')
    if key=='fill_cap':hdim(p,29,69,122,122,115,'Ø40 内舱盖')
line(102,86,102,239,BLUE,.3,[4,3])
box(249,122,157,120,PALE)
text(257,230,'补液盖拆卸路径',13,bold=True)
para(257,217,'卸下对应外盖的 2 颗螺钉后：\n① 向上 +Z 6\n② 向后 +Y 12\n③ 再向上 34，总抬升 40\n此路径用于避开后脑装甲。\n盖、塞、密封垫作为维护组移动；\n左图仅为结构分解，不是逐件拆卸顺序。',140,11,9)
para(249,108,'补液孔 Ø14；密封垫外径 Ø18、内径 Ø14、厚 0.4，均为设计候选。每盖 2 处螺钉，中心间距 24；固定点 Y=69。\n断电补液，擦干外部再复装。密封压缩率、最低点排液、漏斗空间和商品模块可拆分性尚未验证。',157,10,7)
p,b=drawing('fill_cap_top',185,61,1)
text(185,87,'内舱盖俯视 1:1',9,MUTED,align='center')
leader(p(-17,49),212,66,'Ø14')
text(25,29,'局部侧投影：比例 1.7:1；各零件保持原形，分解间距仅用于读图。',9,MUTED)
end()

header('总装爆炸与维护分组','按当前模型的维护组件分解；螺钉与柔性路线在主图中隐藏，以突出装配层次。')
mappt=picture('service.png',15,28,240,214)
for n,px,py in [(1,750,270),(2,745,457),(3,984,432),(4,655,1015),(5,845,685)]:badge(mappt(px,py),n)
items=[('01 整体冠盖','4 颗紧固；上提 65。顶甲、脊翼、前后眉甲随盖移动。'),('02 电子 / 音频托板','4 颗紧固；断开线管后上提 85。图中仅错开 35，以便看清层次。'),('03 两个补液盖组','各 2 颗紧固；上 6、后 12、再上 34。左图一侧盖被部分遮挡。'),('04 电源 / 托盖 / 拉带','4 颗紧固；先拆底部插头小盖并拔线，再托住整组下移 60。'),('05 固定头舱 / 颈架 / 底座','保持组装；履带和驱动来源部件不在本次维护爆炸中分解。')]
y=236
for heading,body in items:
    text(268,y,heading,12,bold=True);y=para(268,y-8,body,132,10,6)-10
para(268,58,'紧固件共 18 处 M2.5 级占位：电源 4、插头盖 2、冠盖 4、托板 4、补液盖 4。无螺纹，采购长度和标准未定。',132,9,6)
end()

header('内部路线、装配顺序与验证边界','黄色为电源线 / 插头包络；青色为喷水软管路线。两者为设计分配，不是完整接线或已验收液路。')
picture('routing.png',14,91,205,151)
title(23,78,'路线与维修关系')
para(23,67,'电源线候选 Ø6，从中央干区经过固定颈架进入头舱。\n喷水管候选 Ø4，独立侧路进入头舱至偏置喷口。\n拆托板前先断开相关线管；未表达高压接线。',190,10,7)
y=238
for h,s in [('装配次序','动力与底座 → 电源托盖和插头检修 → 冠盖定位与设备托板 → 两液体舱单独试验 → 布线后复查维护动作。'),('当前 CAD 证据','219 个几何对象回读有效；460 对包络相交对象的布尔检查无超阈值重叠；6 组维护动作共 80 个离散姿态无超阈值重叠。'),('尺寸与图纸等级','蓝色尺寸为当前 CAD 设计值；充电宝 120 × 73 × 31.5 为用户提供。尺寸不含制造公差。未实测接口与紧固件只用于结构评审。'),('尚待实物确认','端口位置、手指与工具空间、连续拆卸路径、线管弯曲、真实设备固定、承载、密封排液和供电。未通过制造、电气或儿童使用验收。')]:
    text(235,y,h,12,bold=True);y=para(235,y-8,s,167,10,6)-9
box(14,25,392,16,PALE)
text(20,35,'几何源：hardware/model/CyberTrack.FCStd · 图纸生成时核对原生模型及全部 10 张预览图哈希。',9)
text(20,29,'SHA-256：'+meta['source_sha256'],8,MUTED)
end()
c.save()
print(PDF)
print('Pages:',page)
