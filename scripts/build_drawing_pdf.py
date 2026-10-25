"""Build the A3 review drawing pack from saved CAD projections and verified previews.
First run export_drawing_geometry.py with FreeCAD Python; this script uses ReportLab.
No CAD geometry is edited. The output is a design review pack, not shop drawings.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageChops
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--allow-review-conflicts', action='store_true', help='Export an explicitly marked review PDF even when CAD fit checks fail')
args=parser.parse_args()

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
assert report['design_revision']=='0.32', 'Review annotations for a new model revision'
cad_checks_passed=all(report[key]['passed'] for key in ('collision_check','service_paths','controller_clearance_check','water_gun_check','bubble_gun_check','ultrasonic_check','speaker_check','rear_armor_symmetry_check','top_feed_check','drive_mount_check')) and report['water_gun_check']['removal']['passed']
assert cad_checks_passed or args.allow_review_conflicts, 'CAD checks failed; use --allow-review-conflicts only for a marked conflict review PDF'
# Guard dimension callouts that describe named features, not just overall extents.
expected = {
    'BottomServiceCover': [-65.8,-96.8,26,65.8,40,28.8],
    'TrackMountL': [87,-32.5,33,98,32.5,71],
    'TrackMountR': [-98,-32.5,33,-87,32.5,71],
    'UltrasonicRingL': [5,-91.3,155,21,-81,171],
    'UltrasonicRingR': [-21,-91.3,155,-5,-81,171],
    'SensorStatusStrip': [-8,-81.5,172.5,8,-81,173.5],
    'PowerBank': [-60,-96,33,60,-23,64.5],
    'ElectronicsTray': [-52,-74,144.5,52,17,154],
    'ESP32Board': [-39.6,-23.1,163.6,24,5.1,176.8],
    'ControllerCarrier': [-44,-31,150,17.4,16,156],
    'CrownFinL': [43.5,-16,192,59.5,31,203],
    'CrownFinR': [-59.5,-16,192,-43.5,31,203],
    'CrownEffectInsetL': [47.5,-5,196,55.5,20,196.6],
    'ArcModuleL': [52.75,-66,143.75,78.25,4,169.25],
    'ArcModuleR': [-78.25,-66,143.75,-52.75,4,169.25],
    'WaterGunMaximumEnvelope': [38.4,-129,104.7,76.9,9.5,129.3],
    'BubbleGunInspectionEnvelope': [-72.9,-129,89.55,-37.1,-62,125.75],
    'BubbleGunMountingTab': [-58,-87,89.55,-52,-62,96.35],
    'BubbleGunFrontFoot': [-60,-106,89.55,-50,-87,96.35],
    'WaterFillPlug': [-30.8,42.2,124.3,-17.2,55.8,128],
    'WaterFillSeal': [-33,40,127.6,-15,58,128],
}
assert abs(report['water_gun_layout']['mount']['side_walls']['channel_width_mm']-34.4)<1e-6
assert report['water_gun_layout']['mount']['hose']['measured_od_mm']==5
assert report['water_gun_layout']['mount']['hose_support']['seat_diameter_mm']==5.6
assert report['water_gun_layout']['mount']['hose_support']['quantity']==2
assert report['water_gun_layout']['mount']['leads']['guide_integral_with_cradle']
assert report['water_gun_layout']['mount']['cap_screws']==0
assert report['water_gun_layout']['mount']['adhesive']['thickness_mm']==1
assert report['top_feed_check']['top_insertion_only']
assert report['top_feed_check']['former_rear_hole_missing_volume_mm3'] <= 1e-5
ultrasonic=report['ultrasonic_check']
assert ultrasonic['derived_center_spacing_mm']==26
assert ultrasonic['candidate_hole_diameter_mm']==16.6
assert ultrasonic['panel_datum_y_mm']==-81 and ultrasonic['datum_is_assumption']
pitch=report['gun_pitch']
assert pitch['elevation_degrees']==5 and pitch['rotation_about_X_degrees']==-5
assert report['bubble_gun_layout']['mount']['ring']['one_piece']
for name in ('WaterGunMaximumEnvelope','BubbleGunInspectionEnvelope','BubbleGunMountingTab','BubbleGunFrontFoot'):
    kind='water' if name.startswith('Water') else 'bubble'
    pivot=pitch['pivot_world_mm'][kind];offset=pitch['translation_world_mm'][kind]
    b=expected[name];angle=math.radians(-5);points=[]
    for x in (b[0],b[3]):
        for y in (b[1],b[4]):
            for z in (b[2],b[5]):
                dy=y-pivot[1];dz=z-pivot[2]
                points.append((x+offset[0],pivot[1]+dy*math.cos(angle)-dz*math.sin(angle)+offset[1],pivot[2]+dy*math.sin(angle)+dz*math.cos(angle)+offset[2]))
    expected[name]=[min(v[i] for v in points) for i in range(3)]+[max(v[i] for v in points) for i in range(3)]
for name, values in expected.items():
    assert all(abs(a-b)<1e-5 for a,b in zip(meta['objects'][name]['bbox'],values)), name
for prefix, xs, ys in [('BatteryScrew',[-63.5,63.5],[-85,-40]),
                       ('CrownScrew',[-64,64],[-52,7]),
                       ('TrayScrew',[-49.5,49.5],[-30,0])]:
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
c.setTitle('CyberTrack 0.32 模型与装配图纸')
c.setAuthor('CyberTrack')
c.setSubject('A3 design review drawings; dimensions in mm; not manufacturing release')
page=0
TOTAL_PAGES=27

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
    text(405,285,f'CT-32 / {page:02d}',11,'#FFFFFF',align='right')
    text(14,265,title,21,bold=True);text(14,256,subtitle,10,MUTED)
    if not cad_checks_passed:
        text(405,244,'尺寸修订待适配：静态／拆卸／USB 空间未通过',10,ACCENT,True,align='right')
    line(14,250,406,250,'#CAD5DB',.6)
    line(14,20,406,20,'#CAD5DB',.6)
    text(14,13,'模型与装配评审图 | Rev 0.32 | 图纸更新 2026-10-25 | 单位：mm',9,MUTED)
    text(406,13,f'未制造放行 · A3 横向 · {page} / {TOTAL_PAGES}',9,MUTED,align='right')
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
    assert d['source_sha256']==meta['source_sha256'] and d['projection_revision']==3, f'Stale projection: {key}'
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
def part_label(mapping, pixel, x, y, label, align='left'):
    """Named leader anchored to a pixel in the hash-verified CAD preview."""
    size=8.5
    width=pdfmetrics.stringWidth(label,'ZH',size)/U
    left=x-width if align=='right' else x
    px,py=mapping(*pixel)
    edge=left if px<left else left+width if px>left+width else max(left,min(px,left+width))
    line(px,py,edge,y+1,ACCENT,.5)
    c.setFillColor(ACCENT);c.circle(px*U,py*U,.6*U,fill=1,stroke=0)
    box(left-1,y-1,width+2,4.5,'#FFFFFF')
    text(left,y,label,size,INK)

def bbox(name):return meta['objects'][name]['bbox']
def dim(name,axis):
    b=bbox(name);return b[axis+3]-b[axis]
def f(v):return f'{v:.2f}'.rstrip('0').rstrip('.')

def labeled_picture(name,x,y,w,h,labels):
    """Keep labels in the PDF; preserve the hash-verified source render."""
    mapping=picture(name,x,y,w,h)
    for pixel,tx,ty,label,align in labels:
        part_label(mapping,pixel,tx,ty,label,align)
    return mapping

header('模型总览与图纸索引','保留已认可的机甲造型、头身比例与低位电源布局；以保存的原生模型为几何依据。')
labeled_picture('assembly.png',28,87,170,146,[
    ((715,305),18,239,'顶部效果护框／冠盖','left'),
    ((640,490),18,218,'超声波双探头','left'),
    ((468,620),18,180,'泡泡枪','left'),
    ((756,699),203,156,'水枪','right'),
    ((668,822),18,104,'前护甲／底座','left'),
    ((1080,876),203,88,'履带组件','right')])
labeled_picture('rear-assembly.png',229,87,170,146,[
    ((980,476),405,239,'后脑壳／饰板','right'),
    ((805,645),217,216,'固定颈架','left'),
    ((931,625),405,196,'两侧补液盖','right'),
    ((905,720),405,171,'背包液舱外壳','right'),
    ((1090,860),405,119,'后护甲','right'),
    ((1046,764),217,93,'中央脊甲','left')])
text(108,72,'前方轴测 / 前方为 -Y',11,align='center');text(310,72,'后方轴测 / 背包与补液盖',11,align='center')
box(14,29,392,33,PALE)
text(20,51,' × '.join(f(v) for v in report['assembly_size_xyz_mm']),20,bold=True)
text(20,37,'整机宽 × 长 × 高；模型几何外包络',9,MUTED)
text(143,55,'图纸内容',11,bold=True)
para(143,49,'02 彩色正背视　03 彩色左右视　04 正背尺寸　05 左右尺寸　06 俯视 / 底视\n07 电源　08 头舱　09 补液　10 爆炸　11 走线　12 双模块　13 顶部效果\n14 主控布局　15 主控检修　16 水枪尺寸　17 水枪固定　18 线管　19–20 泡泡枪\n21 双探头　22 后护甲　23 顶部供液　24 动力固定　25 接口尺寸　26 动力维护　27 简化底盘与一体电机座',250,9,6)
end()

header('正面与背面 · 彩色外观','当前保存模型的正交渲染图，用于查看装甲层次、配色和前后造型；不是实物照片，尺寸见第 4 页。')
labeled_picture('front.png',33,73,154,156,[
    ((800,373),20,239,'探头状态条（造型候选）','left'),
    ((620,413),20,209,'前脸面板／边框','left'),
    ((848,464),204,190,'下颌护甲／饰条','right')])
picture('rear.png',220,65,180,174)
text(110,54,'正面 / 沿 +Y 观察',12,bold=True,align='center')
text(310,54,'背面 / 沿 -Y 观察',12,bold=True,align='center')
text(110,42,'双探头 Ø16、中心距26；正面左泡泡、右水枪',10,MUTED,align='center')
text(310,42,'后护甲封闭且镜像对称；顶部吸管详见第23页',10,MUTED,align='center')
end()

header('左侧与右侧 · 彩色外观','当前保存模型的正交渲染图，展示头舱、固定颈架、底座与履带之间的关系；尺寸见第 5 页。')
labeled_picture('side.png',30,73,160,156,[
    ((733,405),20,238,'头部侧护罩／装饰耳','left'),
    ((852,509),203,214,'固定颈架侧盖','right'),
    ((662,631),20,137,'双枪承托肩梁','left'),
    ((748,756),203,80,'履带轮组／带体','right')])
picture('right.png',220,65,180,174)
text(110,54,'左侧 / 沿 -X 观察',12,bold=True,align='center')
text(310,54,'右侧 / 沿 +X 观察',12,bold=True,align='center')
text(110,42,'前方在左；+X 为机体左侧',10,MUTED,align='center')
text(310,42,'前方在右；-X 为机体右侧',10,MUTED,align='center')
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
p,b=drawing('side',110,157,.5)
title(28,239,'左侧视图','沿 -X 观察；前方在左；比例 1:2')
hdim(p,b[0],b[2],b[1],b[1],b[1]-16,f(b[2]-b[0]))
vdim(p,b[1],b[3],b[2],b[2],b[2]+15,f(b[3]-b[1]))
# Exact allocated battery silhouette, dashed because it is inside the shell.
ps=bbox('PowerBank');pts=[p(ps[1],ps[2]),p(ps[4],ps[2]),p(ps[4],ps[5]),p(ps[1],ps[5])]
for a,bb in zip(pts,pts[1:]+pts[:1]):line(*a,*bb,ACCENT,.65,[3,2])
leader(p(-60,49),35,82,'充电宝低位包络（虚线）')
p,b=drawing('right',312,157,.5)
title(228,239,'右侧视图','沿 +X 观察；前方在右；比例 1:2')
hdim(p,b[0],b[2],b[1],b[1],b[1]-15,f(b[2]-b[0]))
vdim(p,b[1],b[3],b[2],b[2],b[2]+15,f(b[3]-b[1]))
box(14,29,392,35,PALE)
para(20,53,'电源定位：X = -60…60；Y = -96…-23；Z = 33…64.5。\n120 沿 X、73 沿 Y、31.5 沿 Z；包络几何中心高度 48.75，不是实测质心。',240,10,7)
para(278,53,'头部壳体最大宽 164。\n底部前舱下部宽 132。\n全图以尺寸数字为准，禁止量图加工。',120,9,6)
end()

header('俯视与底视 · 装配位置','六向视图采用相同坐标基准；俯视与底视的左右方向不同，前方均位于图面下方。')
p,b=drawing('top',110,159,.5)
title(28,239,'俯视图','沿 -Z 观察；+X 在右；比例 1:2')
hdim(p,b[0],b[2],b[1],b[1],b[1]-15,f(b[2]-b[0]))
vdim(p,b[1],b[3],b[2],b[2],b[2]+15,f(b[3]-b[1]))
p,b=drawing('bottom',312,159,.5)
title(230,239,'底视图','沿 +Z 观察；+X 在左；比例 1:2')
hdim(p,b[0],b[2],b[1],b[1],b[1]-15,f(b[2]-b[0]))
vdim(p,b[1],b[3],b[2],b[2],b[2]+15,f(b[3]-b[1]))
box(14,29,392,35,PALE)
para(21,53,'俯视：先抽出两路顶部吸管，再独立拆补液盖；中部冠盖与顶甲整体上取。\n底视：六颗螺钉固定一体底盖；充电宝由内部独立托架承托。',240,10,7)
para(279,53,f"整机宽 {f(report['assembly_size_xyz_mm'][0])}；长 {f(report['assembly_size_xyz_mm'][1])}。\n底部维护前垫高；拆电源时另托住电源。\n维护动作与固定点见后续详图。",120,9,6)
end()

header('独立电源承托架与一体底盖','充电宝：用户提供 120 × 73 × 31.5；长侧面的输出口在设计中朝后（+Y），具体端口位置待实测。')
title(24,239,'底视总装','沿 +Z 观察；后方在上；比例 1:2')
p,b=drawing('bottom',85,169,.5)
leader(p(0,-59),18,104,'A 一体底盖：6 处紧固')
leader(p(0,0),115,223,'B 开盖后可达插头')
title(185,239,'内部托架与电源包络','底视，前方在下；比例 1:1')
p,b=drawing('battery',278,181,1)
pts=[p(-60,-96),p(60,-96),p(60,-23),p(-60,-23)]
for a,bb in zip(pts,pts[1:]+pts[:1]):line(*a,*bb,ACCENT,.55,[3,2])
hdim(p,-60,60,-96,-96,-110,'120 电源')
vdim(p,-96,-23,60,60,76,'73 电源')
hdim(p,-63.5,63.5,-40,-40,-14,'127 孔距')
vdim(p,-85,-40,-63.5,-63.5,-78,'45 孔距')
text(211,117,'4 孔中心：X±63.5；Y=-85 / -40；虚线为电源',9,MUTED)
title(25,87,'拆装顺序')
para(25,76,'1. 断电并垫高；拆一体底盖的6颗螺钉。\n2. 盖向下取出，充电宝留在内部承托架上。\n3. 更换电源或电机时拔线、托住电源，拆内部4颗螺钉。\n4. 托架连电源下取60；装回后复查线缆与紧固。',160,10,7)
box(198,29,208,72,PALE)
para(205,90,'电源原位保留：Z33…64.5；内托架Z31…32.8。\n四个0.2厚候选垫保持电源高度；底盖下表面Z26。\n电源整组下取60；更换电机前需先拆电源内托架，再移开本侧履带。\n实际垫高还须增加手部、工具和安全承托空间。\n螺钉、嵌件、孔径和拉带均为候选，未作加工放行。\n前隔板取消；实际插头与线缆仍需确认可达及拔插。',194,9,7)
end()

header('头舱冠盖与电子托板','整体冠盖上取；中央顶甲随冠盖拆装。主控小托架及服务空间见第 14–15 页；真实母座、插头和装配接口仍需核对。')
title(25,239,'整体冠盖俯视','4 处紧固；比例 1:1')
p,b=drawing('crown',109,165,1)
hdim(p,-64,64,7,7,39,'128 孔距')
vdim(p,-52,7,64,64,94,'59 孔距')
text(29,94,'孔中心：X±64；Y=-52 / 7',9,MUTED)
title(249,239,'共用托板俯视','4 处紧固；比例 1:1')
p,b=drawing('tray',316,165,1)
hdim(p,-52,52,-39,-39,-88,f(dim('ElectronicsTray',0))+' 外宽')
hdim(p,-49.5,49.5,0,0,28,'99 孔距')
vdim(p,-30,0,49.5,49.5,72,'30 孔距')
text(253,94,'孔中心：X±49.5；Y=-30 / 0；基础板厚 1；新增支柱',9,MUTED)
box(14,29,392,54,PALE)
para(21,72,'冠盖：卸下 4 颗顶面螺钉，整组上提 65；外壳分缝为 Z181…181.25，间隙 0.25。\n托板：先移去冠盖，断开线束与邻近软管，再卸下 4 颗螺钉，上提 85。',376,10,7)
para(21,50,'主控使用实测总外包络 63.6 × 28.2 × 13.2；前上方剩余电子区 70 × 25 × 13 仍是假设；扬声器按用户提供 69.5 × 31.5 × 16.5 占位，固定和声孔待定。\n冠盖饰片在 CAD 中分对象表达，一体成形或定位固定工艺未定；顶部效果护框与标识随冠盖移动，详见第 13 页。',376,9,7)
end()

header('背包补液结构 · 局部分解','先抽出两路顶部吸管后，两侧独立补液；以右侧喷水舱展示层次，左侧泡泡舱采用对应结构。示意分解间距不代表装配高度。')
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
para(257,217,'先抽出两路顶部吸管，再卸下该盖2颗螺钉：\n① 向上 +Z 6\n② 向后 +Y 12\n③ 再向上 34，总抬升 40\n此路径用于避开后脑装甲。\n盖、塞、密封垫作为维护组移动；\n左图仅为结构分解，不是逐件拆卸顺序。',140,11,9)
para(249,108,'顶部贯通吸管孔 Ø9；内舱补液孔 Ø14；密封垫外径 Ø18、内径 Ø14、厚 0.4，均为设计候选。每盖 2 处螺钉，中心间距 24；固定点 Y=69。\n断电补液，擦干外部再复装。吸管孔护套、通气及防溅、密封压缩率、最低点排液和实物拆洗尚未验证。',157,10,7)
p,b=drawing('fill_cap_top',185,61,1)
text(185,87,'内舱盖俯视 1:1',9,MUTED,align='center')
leader(p(-17,49),212,66,'Ø14')
text(25,29,'局部侧投影：比例 1.7:1；各零件保持原形，分解间距仅用于读图。',9,MUTED)
end()

header('总装爆炸与维护分组','按当前模型的维护组件分解；螺钉与柔性路线在主图中隐藏，以突出装配层次。')
mappt=picture('service.png',40,36,195,200)
for pixel,x,y,label,align in [
    ((850,315),19,236,'整体冠盖','left'),
    ((797,462),19,214,'电子／音频托板组','left'),
    ((1039,437),258,229,'补液盖组','right'),
    ((507,541),19,190,'泡泡枪主体','left'),
    ((575,621),19,165,'整体圆环／底槽','left'),
    ((786,718),19,137,'水枪主体','left'),
    ((1002,700),258,148,'水枪胶粘底托','right'),
    ((767,556),258,193,'固定头舱','right'),
    ((742,643),258,171,'固定颈架','right'),
    ((947,524),258,210,'电弧模块占位','right'),
    ((1070,872),258,108,'履带动力组件','right'),
    ((733,929),19,80,'充电宝','left'),
    ((844,1006),19,44,'电源内托架／拉带','left')]:
    part_label(mappt,pixel,x,y,label,align)
items=[('01 整体冠盖','4 颗紧固；上提 65。顶甲、效果护框与标识、前后眉甲随盖移动。'),('02 电子 / 音频托板','4 颗紧固；断开线管后上提 85。图中仅错开 35，以便看清层次。'),('03 两个补液盖组','先抽出两路吸管；各2颗紧固，上6、后12、再上34。左图一侧盖被部分遮挡。'),('04 一体底盖 / 电源内托架','先拆6颗底盖螺钉；电源仍留机内。更换电源时再拆内托架4颗螺钉，下移60。'),('05 固定头舱 / 颈架 / 底座','保持组装；履带和驱动来源部件不在本次维护爆炸中分解。'),('06 水枪与泡泡枪','水枪先脱胶、抬起再沿枪轴前抽；泡泡枪抬尾后退脱环、侧移取出。固定与拆装详见第17–20页。')]
y=236
for heading,body in items:
    text(268,y,heading,11,bold=True);y=para(268,y-8,body,132,9,5)-8
para(268,64,'电弧模块仅向内错开显示；取出前须先移去托板，详见第 12 页。',132,9,6)
para(268,44,'整机44处候选结构紧固点；不含动力参考包内部紧固件。底盖6颗；电机固定面与底盘一体，无端板锁紧螺钉。',132,8,5)
end()

header('内部路线、装配顺序与验证边界','黄色为电源线 / 插头包络；青色为喷水软管路线。另增主控 Ø3 尾线候选；路线均为设计分配，不是完整接线或已验收液路。')
labeled_picture('routing.png',30,102,173,130,[
    ((868,402),20,240,'ESP32-S3 主控','left'),
    ((885,566),219,221,'电源线／颈部导向','right'),
    ((1147,406),219,201,'泡泡液管（候选）','right'),
    ((672,620),20,180,'喷水管（Ø5实测）','left'),
    ((692,714),20,153,'水枪尾线插头占位','left'),
    ((925,789),219,141,'泡泡液体功能区','right'),
    ((1046,731),219,119,'喷水液体功能区','right'),
    ((555,733),20,103,'充电宝包络','left')])
title(23,78,'路线与维修关系')
para(23,67,'电源线候选 Ø6，从中央干区经过固定颈架进入头舱。\n两枪自吸（用户确认），液管从液舱顶部插入，经两侧接前枪；主控尾线Ø3。\n拆托板前先断开相关线管；未表达高压接线。',190,10,7)
y=238
for h,s in [('装配次序','动力与底座 → 电源内托架和一体底盖 → 冠盖定位与设备托板 → 两液体舱单独试验 → 布线后复查维护动作。'),('当前 CAD 证据',f"{len(report['objects'])} 个几何对象回读有效；{report['collision_check']['boolean_pairs_tested']} 对布尔检查发现 {len(report['collision_check']['overlaps'])} 对超阈值重叠；{len(report['service_paths']['scenarios'])} 组维护动作共 {sum(r['pose_count'] for r in report['service_paths']['scenarios'])} 个离散姿态，{sum(not r['passed'] for r in report['service_paths']['scenarios'])} 组未通过。"),('尺寸与图纸等级','蓝色尺寸为当前 CAD 设计值；充电宝 120 × 73 × 31.5 为用户提供。尺寸不含制造公差。未实测接口与紧固件只用于结构评审。'),('尚待实物确认','端口位置、手指与工具空间、连续拆卸路径、线管弯曲、真实设备固定、承载、密封排液和供电。未通过制造、电气或儿童使用验收。')]:
    text(235,y,h,12,bold=True);y=para(235,y-8,s,167,10,6)-9
box(14,25,392,16,PALE)
text(20,35,'几何源：hardware/model/CyberTrack.FCStd · 图纸生成时核对原生模型及全部 36 张预览图哈希。',9)
text(20,29,'SHA-256：'+meta['source_sha256'],8,MUTED)
end()
header('双电弧模块 · 头舱预装包络','按用户指定的暂定外形：2 × Ø25.5 × 70 mm；橙色圆柱仅代表机械占位，不是实测或通电集成。')
labeled_picture('arc-layout.png',27,116,174,118,[
    ((485,480),18,237,'右侧电弧模块占位','left'),
    ((1140,795),211,113,'左侧电弧模块占位','right')])
text(110,94,'头舱透明示意 / 两侧纵向放置',11,bold=True,align='center')
p,b=drawing('arc_plan',307,171,1)
text(307,239,'俯视布局 / 比例 1:1',12,bold=True,align='center')
vdim(p,-66,4,78.25,78.25,94,'70 用户给定长度')
hdim(p,52.75,78.25,-66,-66,-92,'25.5 用户给定直径')
leader(p(-65.5,-15),219,103,'右侧模块')
leader(p(65.5,-15),354,103,'左侧模块')
box(14,29,392,54,PALE)
para(21,72,'位置：轴线 X=±65.5、Z=156.5，Y=-66…4；每侧内移 3、下移 1.5。托板宽 104；四孔 X±49.5、Y=-30 / 0。\n拆卸候选：先取冠盖和托板，再抬升 2、内移 24.5、继续上提 83（总上提 85）；每侧 24 姿态及三段连续扫掠通过。',375,10,7)
para(21,50,'头壳、托板与 USB 线尾审查区无超阈值重叠；连续扫掠仅覆盖移去前置部件后的裸圆柱，不包含固定件、引线或工具。\n现有尺寸图和 STEP 仍以外观装配为主；两个模块及主控占位保存在 FCStd 中，默认隐藏，可单独显示。',375,9,7)
end()
header('顶部双电弧效果位 · 脊翼造型占位','后掠护框 + 封闭凹槽 + 橙色端部标识；仅表达预期效果位置，不含电极或规定放电间隙。')
labeled_picture('crown-effects.png',26,139,202,94,[
    ((734,340),20,240,'后掠效果护框','left'),
    ((1070,620),238,143,'橙色效果标识（非电极）','right'),
    ((784,535),20,134,'中央顶甲','left')])
text(124,122,'冠盖局部轴测 / 左右各一处效果位',11,bold=True,align='center')
p,b=drawing('crown_effect_plan',321,178,2.2)
text(321,239,'左侧效果护框 / 俯视 2.2:1',12,bold=True,align='center')
hdim(p,43.5,59.5,-16,-16,-23,'16 外宽')
vdim(p,-16,31,59.5,59.5,68,'47 外长')
leader(p(51.5,7.5),251,119,'封闭效果槽 8 × 25')
box(14,29,392,80,PALE)
para(21,97,'效果位置：两处中心线 X=±51.5，沿 Y 布置；位于原后掠脊翼区域，朝顶部开放。\n护框范围 Y=-16…31、Z=192…203；顶点保持 Z=203；水枪前伸后的整机长度见第 1 页。\n凹槽平面范围 X=中心线±4、Y=-5…20；槽底封闭，衬面 Z=196…196.6。',375,10,7)
para(21,70,'装配：护框、衬面和橙色端部标识归入冠盖维护组，随冠盖整体上取；固定孔位及内部双模块保持原位。\nCAD 分对象便于评审，不代表已经完成独立紧固、材料、加工或实物装配设计。',375,10,7)
para(21,49,'尺寸均为造型分配。橙色块是非通电视觉标识，不是电极；凹槽尺寸及标识间距不代表拉弧或绝缘间距。\n未建立高压引线、驱动、电极或与内部模块的功能连接；护框与封闭槽底未通过防护、绝缘或带液共存验收。',375,9,7)
end()
header('ESP32-S3 · 实测包络与主控托架','元件面朝 +Z，USB 朝 -X（机体右侧），天线朝 +X；实测总外形与假设内部层高分开表达。')
labeled_picture('speaker-layout.png',28,128,178,103,[
    ((845,479),219,236,'ESP32-S3 主控板','right'),
    ((750,405),18,241,'防脱压架','left'),
    ((662,580),18,217,'剩余电子预留区','left'),
    ((675,734),18,119,'扬声器包络','left'),
    ((949,627),219,130,'主控小托架／母座','right'),
    ((1130,740),219,113,'电弧模块占位','right')])
text(116,103,'去冠盖的头舱布局 / 外壳透明显示',11,bold=True,align='center')
p,b=drawing('controller_top',318,186,1.8)
title(253,239,'主控小托架俯视','比例 1.8:1；+X 在右，+Y 在上')
hdim(p,-39.6,24,-23.1,-23.1,-39,'63.6 实测总长')
vdim(p,-23.1,5.1,24,24,30,'28.2 实测宽')
leader(p(-39.6,-9),238,121,'USB 朝 -X')
leader(p(23,-9),354,121,'天线朝 +X')
text(318,184,'ESP32-S3',10,INK,True,align='center')
box(14,29,392,62,PALE)
para(21,80,'实测总包络：X=-39.6…24，Y=-23.1…5.1，Z=163.6…176.8；总高 13.2。\n图纸排针资料：两排中心距 25.4，首末针距 53.34（22 针）；未确认独立螺钉孔，不在开发板上增孔。\n候选固定：双排母座承接排针，小托架 4 处紧固，防脱压架 2 处紧固；压架与最高包络保留 0.5 间隙。',375,10,7)
para(21,54,'小托架平面 61.4 × 47、基础板厚 2，天线端悬出；主托板后缘局部延至 Y=17，小托架支柱原位不动；大托板四孔已改为 X±49.5。\nPCB 层高、针排条带、母座连续槽和插接高度均为设计假设；不能按简化槽直接加工或认定触点适配。\n原电子大占位已拆分：前上方另留 70 × 25 × 13 的待定区域，未证明驱动、升压及开关板全部可装入。',375,9,7)
end()
header('主控拆装、USB 插拔与天线预留','仅表达机械候选；USB 调试采用开冠盖方式，未增加外壳开口，也不表示两口可同时供电。')
mappt=picture('controller-service.png',36,128,146,108)
for pixel,x,y,label,align in [
    ((499,306),17,231,'防脱压架','left'),
    ((830,515),202,211,'ESP32-S3 板卡','right'),
    ((584,834),17,184,'双排母座','left'),
    ((934,980),202,147,'主控小托架','right'),
    ((398,841),17,151,'托架紧固螺钉','left')]:
    part_label(mappt,pixel,x,y,label,align)
text(109,116,'局部分解：板卡上移 20、压架上移 40',10,bold=True,align='center')
labeled_picture('controller-access.png',228,140,164,85,[
    ((520,420),215,239,'COM 直头插头预留','left'),
    ((520,520),215,129,'USB 直头插头预留','left'),
    ((1080,470),405,239,'天线净空审查区','right'),
    ((721,615),405,129,'尾线导向环','right')])
text(310,116,'黄色：开盖 USB 服务空间；青色：天线审查区',10,bold=True,align='center')
para(20,101,'主控拆装\n1. 断电、取冠盖、拔 USB 并断开主控尾线。\n2. 换板：卸压架 2 颗螺钉，压架上提，再沿 +Z 拔出板卡。\n3. 拆整组：卸小托架 4 颗螺钉，带母座和压架整体上提。\n图中错开距离仅供读图；板卡与整组各检查上提 65 的路径。',188,9,6)
para(218,101,'USB 与走线\n用户确认直头；插头 18 × 10 × 8、端口中心及线尾转向空间待实测。\n候选拔插：先沿 -X 退出 12，再向上移 35；两口分别检查。\nØ3 尾线沿托架下方转至导向环，绕开天线区；未定义 GPIO、连接器针序或供电接线。',183,9,6)
box(14,25,392,36,PALE)
para(21,51,'天线：假设末端 X17.6…24 为辐射区域；审查区 X17.6…39、Y=-38.1…20.1、Z154.2…185.8。\n参考乐鑫净空建议，朝外、两侧及上下各留 15；馈电侧保留原板。实物天线边界、RF 通路、壳体材料与整机通信性能待核对。\n母座插入深度、防脱载荷、端口位置、线缆弯曲和手指空间均未实测；两处 USB 线尾空间及天线审查通过几何检查；不构成实物装配或射频验收。',375,9,7)
text(21,29,'参考：乐鑫 ESP32-S3 硬件设计指南 · PCB Layout Design / Antenna clearance',8,MUTED)
c.linkURL(report['controller_layout']['rf_guideline'],(21*U,27*U,220*U,32*U),relative=0,thickness=0)
end()
header('拆出水枪 · 实测尺寸与候选布局','长 138.5、最粗处宽 33.2、厚 24.6、带管宽 38.5；喷嘴、接头和前段轮廓为示意，不是接口测量。')
picture('water-gun-component.png',14,140,185,99)
picture('water-gun-layout.png',208,117,198,125)
text(106,130,'独立总成 / 总尺寸实测，分段形状假设',10,bold=True,align='center')
text(307,106,'头舱下方、颈架左侧 / 前向上仰 5°',10,bold=True,align='center')
para(20,114,'0.18 喷嘴端中心 (55, -137.16, 122.61)。\n两枪均上仰5°；水枪旋转后前移10、下移4，避让头壳与底座。\n原完整尺寸包络随枪体刚性变换；接管仍朝+X。',180,10,7)
w=report['water_gun_check']
nearest=w['nearest_clearances'][0]
box(14,28,392,55,PALE)
para(21,72,f"0.25 保留左右定位挡板与底部双面软胶，外侧前后挡板均设上开口托管座，尾线导向鞍并入底托；无压盖和横向紧固。\n裸枪33.2宽检查挡板与整机，带管38.5宽检查夹具以外障碍；最近间距 {nearest['distance_mm']:.2f} mm（不含胶面）。\n粘接已解除且线管断开后，先沿底板法向抬起2，再沿枪轴向前150；裸枪、示意接头及外部带管包络连续扫掠通过。",375,9,7)
para(21,45,'胶厚暂按1；水枪位置及5°上仰保持。两块胶面与示意枪底接触，仅是几何接触核对。\n胶带型号、耐水、温度、脉冲载荷下保持力和脱胶方法未定；检查不构成粘接或实物拆卸验收。',375,9,6)
end()
header('水枪胶粘底托 · 底部双面软胶固定','按用户选择采用底部双面软胶；保留左右定位挡板、后挡和尾线导向；外侧双托管槽向上开放，尾线导向鞍与底托一体。')
picture('water-gun-mount.png',14,123,193,119)
mappt=picture('water-gun-service.png',222,140,174,85)
for pixel,x,y,label,align in [
    ((549,546),215,235,'水枪主体','left'),
    ((995,547),311,132,'胶粘底托','left'),
    ((883,570),311,242,'双面软胶×2','left'),
    ((1217,500),405,221,'一体尾线导向鞍','right'),
    ((1250,475),405,238,'尾线插头占位','right')]:
    part_label(mappt,pixel,x,y,label,align)
text(110,113,'左右挡板定位 / 顶部开放 / 外侧托管',11,bold=True,align='center')
text(309,113,'已解除粘接后的分解示意',11,bold=True,align='center')
para(20,99,'底托主板38.4×74×3；左右净宽34.4，单侧留0.6。\n两块双面软胶占位31.2×20，厚1，模块坐标中心Y=-62 / -10。\n两对挡板长12、高20、厚2；不设上压唇或侧垫。\n底托仍用2颗M3级候选螺钉连接左肩梁；孔位及枪位保持。\n双托管槽Ø5.6×6、间距52，紧贴挡板；尾鞍与底托一体。',183,9,6)
para(220,99,'拆装顺序\n1. 断电排液，断管后从双托座上提，断尾线并释放扎带。\n2. 先充分解除底部粘接；脱胶工艺和工具可达未验。\n3. 沿倾斜底板法向抬起2，再沿枪轴前方取出150。\n4. 若拆底托：卸基座2螺钉，沿底板法向抬2后外移60。',180,9,6)
box(14,27,392,32,PALE)
para(21,49,'双面软胶是当前保持方式；左右挡板与后挡仅用于定位，不代替胶粘保持力。基座螺钉固定底托，不直接锁住水枪。\n胶面按未压缩1厚占位，类型、实际厚度、表面处理、耐水与温度性能及重复拆装后的保持力待实测。\n枪体与空底托扫掠、6项线管／基座工具空间及两处局部管段上提10检查通过；未模拟剥离、手部或脱胶工具。',375,9,7)
end()
header('水管与尾部引线 · 路线及操作预留','青色为水管预留，黄色为线束、插头与工具预留；这些是空间假设，不是已选连接器或布线规格。')
labeled_picture('water-gun-spaces.png',29,97,197,132,[
    ((840,181),20,239,'顶部供液管／路线预留','left'),
    ((749,727),20,89,'接管拔出空间','left'),
    ((1051,581),241,217,'尾线插头／拔出空间','right'),
    ((936,565),241,113,'外侧双托管座','right')])
text(126,72,'半透明体为审查空间，实体接触按操作步骤区分',10,bold=True,align='center')
para(251,236,'水管\n用户实测外径5；中心R8为假设，另留Ø8路线空间。\n液舱顶部贯通孔候选Ø9；枪侧接管沿+X拔30，操作包络Ø16。\n前后双托槽Ø5.6×6、间距52；沿外侧接顶部吸管，无后护甲穿管。',151,10,7)
para(251,174,'尾部引线\n模块坐标枪尾Y=9.5；Ø3线束随枪体倾斜后转至外侧；中心弯曲半径 8，路线预留 Ø8。\n插头候选 16×10×10，沿 +X 拔出 16；尾线导向鞍与扎带槽并入底托；扎带与抗拉待选。',151,10,7)
para(251,112,'工具\n水枪取消压盖及对应工具空间。\n基座螺钉：先脱胶并取出枪体，再用朝前操作的短臂内六角；端部Ø3、杆部Ø6、前伸臂40。\n仅检查基座工具杆，不包括手掌、把手转动或脱胶工具。',151,9,6)
box(14,27,392,31,PALE)
para(21,48,'Ø8水管审查区仅在托管座处允许重叠；实际Ø5管与托座另检，间隙0.3。尾线导向鞍同样单独检查实际线束。\n软管压力、最小允许弯曲半径、线尾抗拉、插头保持力和带液工作未测；先核实实物与胶粘保持性能，再确定材料和加工公差。',375,9,7)
end()
header('前置双枪 · 上仰5°与整体圆环','正面看左泡泡、右水枪；5°为设计候选。新薄片部件独立保存，原始模型与照片保留。')
picture('front.png',14,126,190,114)
labeled_picture('bubble-gun-mount.png',226,137,167,91,[
    ((500,428),215,239,'整体前圆环','left'),
    ((1010,717),405,130,'两段底槽／支架底座','right')])
text(109,115,'双枪微微上仰 / 水枪前移10、下移4',11,bold=True,align='center')
text(309,115,'前圆环无分缝 / 后部两段底槽',11,bold=True,align='center')
para(21,102,'泡泡枪口中心(-55,-126.65,115.75)。\n水枪口中心(55,-137.16,122.61)；两轴同为上仰5°。\n泡泡平放基准：圆底离平面4.7，薄片6×25×6.8。\n31.5+4.7=36.2与原总高35.8的0.4差异仍待核对。',184,9,7)
para(220,102,'整体环孔34／外径39／厚3；径向间隙1.25。\n无前环螺钉；仅2颗M3级基座紧固候选。\n底槽名义后6宽×25长、前10宽，净宽6.4／10.4。\n前段长19为假设；槽端导入斜面、前后止挡与0.6底垫。',181,9,7)
box(14,28,392,36,PALE)
para(21,54,'用户拟用热熔胶／胶水辅助固定；圆环、阶梯槽与前后止挡定位。胶材、用量、粘接兼容性及保持力未确定。\n胶点需可接近清除，避开内部运动件；拆卸先清胶。前止挡依赖假设的前底轮廓，实物试配后再确定。\n5°不代表允许工作倾角；上仰时出泡、喷水、滴液／倒流、固定保持和真实拆装仍需实物验证。',375,9,7)
end()
header('泡泡枪拆装 · 整体环穿装与线管空间','主体含转动步骤，采用102个离散姿态检查；不宣称转动段已做连续扫掠。尺寸以模块自身坐标表达。')
mappt=picture('bubble-gun-service.png',32,143,155,85)
for pixel,x,y,label,align in [
    ((475,457),17,237,'前筒壳体','left'),
    ((377,535),17,218,'出泡转轮','left'),
    ((598,433),201,238,'电机示意','right'),
    ((713,474),201,222,'后部壳体','right'),
    ((620,540),201,205,'后底薄片','right'),
    ((560,578),17,197,'前底承托部（假设）','left'),
    ((730,750),17,173,'整体前圆环','left'),
    ((1039,832),201,183,'两段固定槽／止挡','right'),
    ((1200,870),201,147,'支架底座','right'),
    ((1115,910),201,132,'基座紧固／嵌件','right')]:
    part_label(mappt,pixel,x,y,label,align)
labeled_picture('bubble-gun-spaces.png',227,143,166,84,[
    ((553,480),215,240,'尾线插头预留','left'),
    ((1030,326),405,237,'泡泡液管／路线预留','right'),
    ((600,634),215,131,'基座工具空间','left'),
    ((1080,700),405,131,'泡泡液舱吸管','right'),
    ((730,550),405,192,'本地停止按钮／指端空间','right'),
    ((950,590),405,157,'相邻喷水管','right')])
text(110,119,'抬尾15°，后退脱环，再向外取出',11,bold=True,align='center')
text(310,119,'线管和基座工具预留 / 非实际接线',11,bold=True,align='center')
para(21,105,'1 断电排液、清除辅助胶，先拔插头移开尾线，再断管。\n2 围绕圆环中心抬尾15°，沿模块后方退10，脱离圆环。\n3 沿模块上方抬3，再向车体右侧(-X)移90；安装反向。\n4 空托架卸2颗基座螺钉，沿底板法向抬6、向-X移90。',183,9,7)
para(220,105,'泡泡管顶部插入液舱，沿侧面接前枪；Ø4管／Ø3尾线、中心R8及Ø8预留均为候选。\n接管沿模块后方拔25；16×10×10插头向-X拔16。\n前圆环为整体，不设分缝、衬垫或前环工具空间。\n基座工具在主体取出后使用；不包含整手与把手。',181,9,7)
box(14,27,392,36,PALE)
para(21,53,'主体每0.5°转动、每0.5后退／抬升、每2侧移检查示意实体；实物外形和采样之间的连续空间尚未证明。\n空托架、基座螺钉另做保守连续扫掠；前向Ø36×50通道随枪轴上仰。停止按钮保留前方Ø12指端空间。\n宽度、薄片偏置、前槽长度与前底轮廓待实测；胶粘保持、线管防磨、防拉脱、排液及制造均未验收。',375,9,7)
end()
header('超声波双探头 · 实测尺寸与前脸候选','圆柱尺寸来自用户；中心距为推导；Y=-81面板基准、Ø16.6开孔和端面分色均为设计假设。')
title(26,235,'正面双探头','沿 +Y 观察；比例 2:1；中心 Z163')
p,b=drawing('ultrasonic_front',110,190,2)
hdim(p,-13,13,163,163,180,'26 中心距（推导）')
hdim(p,-21,21,155,155,149,'42 外沿总宽')
vdim(p,155,171,-21,-21,-29,'Ø16')
title(235,235,'侧面突出高度','沿 -X 观察；比例 2:1；前方在左')
p,b=drawing('ultrasonic_side',310,190,2)
hdim(p,-91.3,-81,171,171,181,'10.3 离面板高度')
leader(p(-81,155),337,158,'面板外表面 Y=-81（暂定）')
picture('ultrasonic-layout.png',21,62,176,77)
text(109,53,'前脸候选 / 非实物安装照片',10,MUTED,align='center')
para(221,130,'输入：两圆柱Ø16、总宽42、离面板高10.3。\n推导：中心距26、圆柱净距10；中心X±13。\n面板：原孔补回，改为双Ø16.6贯穿候选孔。\n单边0.3间隙仅为设计值；PCB与背部空间未建模。\n状态色条移至探头上方，避免与圆柱相交。',178,10,8)
box(14,27,392,19,PALE)
para(21,39,'CAD检查使用完整实心圆柱包络，包含实体与预留空间。未确认的面板基准、整板／孔位／接头及声学性能仍需实物核对。',376,9,6)
end()
header('后护甲单体 · 镜像对称核对','底座斜面后护甲／背包下支座；仅显示 RearBaseArmor，排除相邻脊甲、饰条、背包与透视遮挡。')
p,b=drawing('rear_armor_rear',110,170,1.8)
title(25,239,'单体背视','沿 -Y 观察；比例 1.8:1；虚线为 X=0 镜像面')
line(*p(0,30),*p(0,101),BLUE,.5,[3,2])
hdim(p,-47,47,34,34,24,'94 最大宽度')
vdim(p,34,97,-47,-47,-53,'63 最大高度')
p,b=drawing('rear_armor_side',306,170,1.8)
title(245,239,'单体侧视','沿 -X 观察；比例 1.8:1')
hdim(p,74,82,34,40,24,'8 前后深度')
para(333,196,'前截面 Y74\n最大宽94、高63\n后截面 Y82\n最大宽84、高53\n轮廓及斜面由\n单侧参数镜像生成',72,9,7)
box(14,29,392,58,PALE)
check=report['rear_armor_symmetry_check']
para(21,75,f"保存回读核对：实际后护甲已封回全部液管孔，直接对完整实体关于 X=0 镜像。\n实体双向差集 {check['solid_symmetric_difference_mm3']:.6f} mm³；{len(check['face_pairs'])} 个完整表面逐一匹配（含斜面及中央脊甲座），面积差均≤0.00001 mm²。\n顶点镜像最大偏差 {check['maximum_mirrored_vertex_distance_mm']:.6f} mm；实际模型无单侧功能孔，轮廓和全部斜面统一镜像。\n这是名义CAD几何核对，不是加工公差、强度或实物验收。",375,10,10)
end()
header('双枪供液 · 全部从顶部插入','水枪和泡泡枪可自吸：用户于2026-10-24确认。后护甲和液舱侧壁均不设液管孔；以下为管路候选。')
p,b=drawing('top_feed_top',111,170,0.75)
title(21,240,'俯视 · 两路在顶部错开','沿 -Z 观察；比例 0.75:1；前方在下')
leader(p(-24,49),21,225,'喷水入口 X−24／Y49')
leader(p(24,49),132,212,'泡泡入口 X24／Y49')
p,b=drawing('top_feed_side',305,170,0.8)
title(223,240,'侧视 · 吸管伸入液舱','沿 -X 观察；比例 0.8:1；两舱投影重合')
line(*p(49,45),*p(49,135),BLUE,.6,[3,2])
text(331,132,'虚线：舱内吸管轴线',9,MUTED)
part_label(lambda x,y:(x,y),p(49,45),264,109,'管端 Z45，距原舱底基准5')
box(14,29,392,62,PALE)
para(21,80,'两舱顶部贯通孔Ø9；喷水管Ø5为实测，泡泡管Ø4、中心弯曲R8及Ø8路线预留为候选。\n吸管沿舱轴垂直插入；喷水上段Z149，泡泡上段Z161，经两侧接前置枪体，不绕后护甲。\n开任一补液盖前：断电、处理残液、先抽出两路吸管，再拆对应盖；柔性抽管过程尚未验证。\n自吸能力不等于本布置已验收：实际吸程、首次引液、漏气、通气防溅、管口固定与离底距离需实测。',375,10,10)
end()
header('底盘动力固定 · 一体电机座与开放干舱','0.32：左右动力各外移14、下部前后132等宽；固定接口保留，取消独立端板及其锁紧螺钉。')
picture('drive-mount.png',20,83,235,157)
title(270,237,'保留的动力接口')
para(270,223,'电机端面：X±73，板厚4，与底盘一体。\n电机壳体中心Y0、Z50；轴中心Z57。\n孔分度圆Ø31，通孔Ø3.4；每侧4个完整座。\n履带安装面X±87，孔距56.2、中心Z37.4。\n电机、轴、联轴器及履带位置不变。\n删除前干舱隔板、电源上隔板及跨舱横梁。\n后湿舱隔板及电源独立承托保留。\n电机维护改为移开本侧履带后向下取出。',132,10,9)
box(14,28,392,39,PALE)
para(21,56,'电机固定面、侧壁和顶梁融合进同一底盘实体；不再存在独立端板、厚脚、止挡配合或4颗端板锁紧螺钉。\n一体底盖及电源内托架保留；内部必要承托不随跨舱横梁一起删除。\n材料、打印方向、薄壁变形、螺纹及实际承载仍待验证；几何一体不等于制造放行。',375,10,8)
end()
header('动力接口详图 · 一体电机固定面与底盖','左侧实际BRep投影；右侧镜像。原孔位及轴线保持；固定面周围材料与底盘相连。')
p,b=drawing('drive_face',116,170,2.5)
title(22,240,'电机与履带固定面','沿 -X 观察；截取X73.3…87.01；比例2.5:1')
hdim(p,-28.1,28.1,37.4,37.4,23,'56.2 履带孔距')
hdim(p,-6.5,6.5,50,50,80,'13 下开槽 / 顶弧Ø13')
leader(p(15.5,50),188,181,'Ø3.4 / PCD31')
p,b=drawing('drive_cover',314,170,.9)
title(253,240,'一体底盖底视','沿 +Z 观察；比例0.9:1；前方在下')
text(247,100,'X±65.8；Y−96.8…40；厚2.8',9,MUTED)
box(14,28,392,65,PALE)
para(21,81,'用户提供输出端Ø11.9；槽宽13、顶弧Ø13保持。\n总名义间隙1.1；居中单边0.55，未扣打印误差。\n开口用于避让／下取；4颗端面螺钉负责固定。\n下方两个开口孔不作完整座；先移开本侧履带。\n前履带螺钉需先拆电源；实际打印配合待试装。',191,10,9)
para(220,81,'六处底盖紧固：X±63，Y−75／−55／37。\nØ2.8通孔、Ø4.8头部沉孔；M2.5级示意螺钉。\n底盖不承托电源或履带；内电源托架另有4处固定。\n电机、履带及底盖螺纹、长度、公差均待实物确认。',180,9,9)
end()
header('动力维护顺序 · 先移开本侧履带，再下取电机','图中电源、本侧履带及电机端面螺钉已移去；电机沿原XY位置向下取出，另一侧动力保留。')
picture('drive-service.png',20,88,235,153)
title(266,237,'单侧拆卸；装配反向执行')
para(266,223,'1. 断电、排液并垫高；托住待拆组件。\n2. 拆6颗底盖螺钉，整块底盖向下取出。\n3. 断开电源线；拆4颗内托架螺钉，\n   电源连托架向下取出60。\n4. 断电机线、解除联轴器锁定。\n5. 本侧2颗履带螺钉内移35.5、下取80；\n   本侧完整履带、支架及联轴器外移60。\n6. 4颗电机端面螺钉向外退出25。\n7. 电机连轴沿原XY位置向下取出80。',136,10,8)
box(14,28,392,43,PALE)
para(21,60,'连续保守扫掠覆盖底盖、盖螺钉、履带螺钉、端面螺钉及两侧电机下取；履带总成外移按1 mm间隔采样。\n不再沿用0.31的端板内退28路径，也不再声明换电机时保留充电宝及本侧履带。\n实际联轴器锁定、编码器尾部和柔性线束仍需核对；工具只检查批头／直杆，手柄及材料承载待验。',375,10,9)
end()
header('简化底盘 · 开放干舱与一体电机安装面','实际保存模型的独立视图；蓝色为保留的后部湿舱隔板，红色为电机原有4颗端面固定螺钉。')
picture('drive-frame.png',17,100,203,145)
picture('drive-integrated-face.png',229,102,169,141)
title(24,91,'前隔板、上内隔板及横梁取消，后湿舱隔板保留')
title(236,91,'电机固定面与底盘一体')
box(14,28,392,51,PALE)
para(21,68,'不再有独立电机端板及其4颗底部锁紧螺钉。\n侧壁、顶梁、电机固定面及履带连接柱连续承力。\n取消电源上内隔板；保留电源内托架、承托条及固定柱。\n后湿舱隔板及双液舱中央隔板保持。',190,10,8)
para(218,68,'底盘前后132宽，履带接口与左右各14外移保持。\n电机维护接受先移去电源内托架和本侧履带。\n一体化减少零件与配合，但不代表材料强度已通过。\n打印方向、螺纹、公差、变形及实际装配均待验。',183,10,8)
end()
assert page==TOTAL_PAGES, 'Drawing index and total page count differ'
c.save()
print(PDF)
print('Pages:',page)
