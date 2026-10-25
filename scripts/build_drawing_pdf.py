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
from assembly_catalog import build_catalog, render_catalog

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
assert sha(MODEL/meta.get('source_document','CyberTrack.FCStd'))==meta['source_sha256'], 'Stale CAD projections'
# A stale PNG must never silently be packaged with a newer CAD drawing.
for rel,digest in report['files_sha256'].items():
    path=ROOT/rel
    if not path.exists(): path=MODEL/Path(rel).name
    assert sha(path)==digest, f'Stale model artifact: {path}'
pitch_audit=json.loads((MODEL/'gun-pitch-audit.json').read_text())
breadboard_audit=json.loads((MODEL/'breadboard-change-audit.json').read_text())
integration_audit=json.loads((MODEL/'ultrasonic-integration-change-audit.json').read_text())
effects_audit=json.loads((MODEL/'effects-change-audit.json').read_text())
board_audit=json.loads((MODEL/'effect-board-change-audit.json').read_text())
booster_audit=json.loads((MODEL/'mt3608-change-audit.json').read_text())
assert booster_audit['passed'] and booster_audit['source_sha256']==meta['source_sha256']
assert board_audit['passed'] and board_audit['source_sha256']==booster_audit['baseline_sha256']
assert effects_audit['passed'] and effects_audit['source_sha256']==board_audit['baseline_sha256']
assert integration_audit['passed'] and integration_audit['source_sha256']==effects_audit['baseline_sha256']
assert breadboard_audit['passed'] and breadboard_audit['source_sha256']==integration_audit['baseline_sha256']
assert pitch_audit['passed'] and pitch_audit['source_sha256']==breadboard_audit['baseline_sha256']
assert report['design_revision']=='0.44', 'Review annotations for a new model revision'
cad_checks_passed=all(report[key]['passed'] for key in ('mt3608_check','effects_mount_check','collision_check','service_paths','breadboard_check','water_gun_check','bubble_gun_check','ultrasonic_check','ultrasonic_integration_check','rear_armor_symmetry_check','top_feed_check','drive_mount_check','l298n_check','l298n_mount_check','bottle_backpack_check','head_lift_check')) and report['water_gun_check']['removal']['passed']
assert cad_checks_passed or args.allow_review_conflicts, 'CAD checks failed; use --allow-review-conflicts only for a marked conflict review PDF'
# Guard dimension callouts that describe named features, not just overall extents.
expected = {
    'BottomServiceCover': [-65.8,-96.8,26,65.8,40,28.8],
    'TrackMountL': [87,-32.5,33,98,32.5,71],
    'TrackMountR': [-98,-32.5,33,-87,32.5,71],
    'UltrasonicRingL': [5,-87.8,155,21,-77.5,171],
    'UltrasonicRingR': [-21,-87.8,155,-5,-77.5,171],
    'SensorStatusStrip': [-8,-81.5,172.5,8,-81,173.5],
    'PowerBank': [-60,-96,33,60,-23,64.5],
    'L298NCarrier': [-28.75,-17,29.2,28.75,24.5,78.2],
    'L298NEnvelope': [-21.75,-4,32,21.75,23.5,78.2],
    'ElectronicsTray': [-61,-72.5,171.5,61,17.5,177],
    'BreadboardEnvelope': [-50,-70,174,50,15,210],
    'CrownFinL': [43.5,-16,192,59.5,31,203],
    'CrownFinR': [-59.5,-16,192,-43.5,31,203],
    'CrownEffectInsetL': [47.5,-5,196,55.5,20,196.6],
    'WaterGunMaximumEnvelope': [38.4,-129,104.7,76.9,9.5,129.3],
    'BubbleGunInspectionEnvelope': [-72.9,-129,89.55,-37.1,-62,125.75],
    'BubbleGunMountingTab': [-58,-87,89.55,-52,-62,96.35],
    'BubbleGunFrontFoot': [-60,-106,89.55,-50,-87,96.35],
    'WaterModule': [3.6,40.6,40,52.4,89.4,154],
    'BackpackShell': [-80,35,34,80,107.5,124],
}
for name in ('UltrasonicRingL','UltrasonicRingR','SensorStatusStrip','CrownFinL','CrownFinR','CrownEffectInsetL'):
    expected[name][2] += 25
    expected[name][5] += 25
assert abs(report['water_gun_layout']['mount']['side_walls']['channel_width_mm']-34.4)<1e-6
assert report['water_gun_layout']['mount']['hose']['measured_od_mm']==5
assert report['water_gun_layout']['mount']['hose_support']['seat_diameter_mm']==5.6
assert report['water_gun_layout']['mount']['hose_support']['quantity']==2
assert report['water_gun_layout']['mount']['leads']['guide_integral_with_cradle']
assert report['water_gun_layout']['mount']['cap_screws']==0
assert report['water_gun_layout']['mount']['adhesive']['thickness_mm']==1
assert report['top_feed_check']['top_insertion_only']
assert report['top_feed_check']['bottle_envelope_uncut']
ultrasonic=report['ultrasonic_check']
assert ultrasonic['derived_center_spacing_mm']==26
assert ultrasonic['candidate_hole_diameter_mm']==16.6
assert ultrasonic['panel_datum_y_mm']==-77.5 and ultrasonic['datum_is_assumption']
pitch=report['gun_pitch']
assert pitch['elevation_degrees']==15 and pitch['rotation_about_X_degrees']==-15
assert report['bubble_gun_layout']['mount']['ring']['one_piece']
for name in ('WaterGunMaximumEnvelope','BubbleGunInspectionEnvelope','BubbleGunMountingTab','BubbleGunFrontFoot'):
    kind='water' if name.startswith('Water') else 'bubble'
    pivot=pitch['pivot_world_mm'][kind];offset=pitch['translation_world_mm'][kind]
    b=expected[name];angle=math.radians(pitch['rotation_about_X_degrees']);points=[]
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
                       ('BreadboardScrew',[-57,57],[-40,-5])]:
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
c.setTitle('CyberTrack 0.44 模型与装配图纸')
c.setAuthor('CyberTrack')
c.setSubject('A3 design review drawings; dimensions in mm; not manufacturing release')
page=0
DETAILS=json.loads((DATA/'assembly-details.json').read_text())
assert DETAILS['source_sha256']==meta['source_sha256'], 'Stale assembly details'
assert set(DETAILS['objects'])==set(meta['objects'])=={o['name'] for o in report['objects']}
CATALOG, CATALOG_SHEETS=build_catalog(DETAILS['objects'])
TOTAL_PAGES=31+len(CATALOG_SHEETS)
SYSTEM_PAGE_REFS={'A':'20-22','B':'2-4、20-22','C':'5、22','D':'23-24、30','E':'8-9','F':'6、8','G':'6、12','H':'10-12','I':'18、25','J':'13-15','K':'16-17','L':'7、19','N':'26-29','M':'各系统检修'}

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
    c.bookmarkPage(f'page-{page}')
    c.addOutlineEntry(f'{page:02d} {title}',f'page-{page}',level=0)
    c.setFillColor(INK);c.rect(0,278*U,420*U,19*U,fill=1,stroke=0)
    text(14,285,'CYBERTRACK',18,'#FFFFFF',True)
    text(405,285,f'CT-44 / {page:02d}',11,'#FFFFFF',align='right')
    text(14,265,title,21,bold=True);text(14,256,subtitle,10,MUTED)
    if not cad_checks_passed:
        text(405,244,'尺寸修订待适配：静态／拆卸／USB 空间未通过',10,ACCENT,True,align='right')
    line(14,250,406,250,'#CAD5DB',.6)
    line(14,20,406,20,'#CAD5DB',.6)
    text(14,13,'模型与装配评审图 | Rev 0.44 | 图纸更新 2026-10-25 | 单位：mm',9,MUTED)
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

header('模型总览与图纸索引','0.44：新增37×18×6实测MT3608升压板包络；L298N左上方干舱候选，固定待设计；原409个对象保持。')
labeled_picture('assembly.png',28,87,170,146,[
    ((740,260),18,239,'顶部效果护框／冠盖','left'),
    ((630,460),18,218,'超声波双探头','left'),
    ((468,620),18,180,'泡泡枪','left'),
    ((756,699),203,156,'水枪','right'),
    ((668,822),18,104,'前护甲／底座','left'),
    ((1080,876),203,88,'履带组件','right')])
labeled_picture('rear-assembly.png',229,87,170,146,[
    ((915,460),405,239,'后脑壳／饰板','right'),
    ((1050,525),405,196,'外露液瓶包络','right'),
    ((870,830),405,171,'背包液舱外壳','right'),
    ((1090,860),405,119,'后护甲','right'),
    ((1060,810),217,93,'中央脊甲','left')])
text(108,72,'前方轴测 / 前方为 -Y',11,align='center');text(310,72,'后方轴测 / 低位护舱与液瓶',11,align='center')
box(14,29,392,33,PALE)
text(20,51,' × '.join(f(v) for v in report['assembly_size_xyz_mm']),20,bold=True)
text(20,37,'整机宽 × 长 × 高；模型几何外包络',9,MUTED)
text(143,55,'图纸内容',11,bold=True)
para(143,49,'02-04 六向尺寸　05 电源　06 头舱　07 双瓶　08 爆炸　09 走线\n10 面包板布局　11 浅托盘固定　12 整盘检修　13-15 水枪与线管\n16-17 泡泡枪　18 双探头　19 顶部供液　20-22 动力固定与维护\n23 L298N布局　24 支架与拆装　25 超声波共存\n26-27 夹环与承板　28 板卡固定　29 接线与余量　30 升压板　31 全对象索引　32起 逐项图卡',250,8.5,4.5)
end()

header('正面与背面 · 主要外形尺寸','各视图独立标识观察方向；尺寸为模型几何值。矢量线稿使用遮挡线消隐，未显示隐藏线。')
p,b=drawing('front',111,160,.5)
title(28,239,'正面','沿 +Y 观察；右侧为 +X / 机体左侧；比例 1:2')
hdim(p,b[0],b[2],b[1],b[1],b[1]-15,f(b[2]-b[0]))
vdim(p,b[1],b[3],b[0],b[0],b[0]-14,f(b[3]-b[1]))
hdim(p,-89.5,89.5,193,193,242,'179 含侧耳')
p,b=drawing('rear',310,160,.5)
title(227,239,'背面','沿 -Y 观察；左侧为 +X / 机体左侧；比例 1:2')
hdim(p,b[0],b[2],b[1],b[1],b[1]-15,f(b[2]-b[0]))
leader(p(-28,145),232,180,'外露瓶体包络')
leader(p(28,124),350,170,'低位护舱顶 Z124')
box(14,29,392,38,PALE)
para(20,56,'尺寸依据：整机最大宽度 228；整体高度 228；两侧耳部总宽 179。\n这些数值描述当前 CAD 外形，不含制造公差、线缆外伸、真实接头或变形。',210,10,7)
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
para(21,53,'俯视：移开目标吸管与绑带后单瓶上取；中部冠盖与顶甲整体上取。\n底视：六颗螺钉固定一体底盖；充电宝由内部独立托架承托。',240,10,7)
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

header('头舱冠盖与电子托板','整体冠盖上取；中央顶甲随冠盖拆装。整板浅托盘与服务空间见第11-12页；面包板含元件／线束按100×85×36规划。')
title(25,239,'整体冠盖俯视','4 处紧固；比例 1:1')
p,b=drawing('crown',109,165,1)
hdim(p,-64,64,7,7,39,'128 孔距')
vdim(p,-52,7,64,64,94,'59 孔距')
text(29,94,'孔中心：X±64；Y=-52 / 7',9,MUTED)
title(249,239,'共用托板俯视','4 处紧固；比例 1:1')
p,b=drawing('tray',316,165,1)
hdim(p,-61,61,-40,-40,-88,'122 侧耳总宽')
hdim(p,-57,57,-5,-5,28,'114 孔距')
vdim(p,-40,-5,57,57,75,'35 孔距')
text(253,94,'孔中心：X±57；Y=-40 / -5；底厚2.5；围边高3',9,MUTED)
box(14,29,392,54,PALE)
para(21,72,'冠盖：卸下 4 颗顶面螺钉，整组上提 65；外壳分缝为 Z206…206.25，间隙 0.25。\n托板：先移去冠盖，断开线束与邻近软管，再卸下 4 颗螺钉，上提 85。',376,10,7)
para(21,50,'面包板整组包络100×85×36为用户规划尺寸，替代旧裸板、母座、独立扬声器与剩余电子占位；不是整组实测。\n冠盖饰片在 CAD 中分对象表达，一体成形或定位固定工艺未定；顶部效果护框与标识随冠盖移动，详见后附G组冠盖图卡。',376,9,7)
end()

header('150 mL 双瓶背包 · 90 mm 低位护舱','用户指定两瓶 Ø48.8 × 114（含盖），各150 mL；完整外包络不削切，不以圆柱体积冒充液体容量。')
picture('bottle-backpack-layout.png',15,104,190,137)
picture('bottle-backpack-service.png',216,104,188,137)
title(23,243,'底托、侧垫与可释放绑带','透明柱为暂定完整包络；瓶肩／盖形未建模')
title(225,243,'单瓶独立上取 150','仅目标管及绑带移开；另一瓶与管路保留')
box(14,29,392,67,PALE)
para(21,85,'护舱Z34…124，高90；较原外壳降低34。\n瓶底Z40、含盖顶Z154，顶部包络露出30。\n每瓶底托2颗M3；底垫1、两道侧垫1；取消上盖及顶垫。\n12×1环绕绑带经前导槽定位、后拉片释放；保持力待测。',185,10,8)
para(220,85,'断电，抽出并收置目标瓶吸管；解开并移开目标绑带。\n从后侧抓取瓶子，向上抽出150，移到机外开盖加水。\n另一瓶及其软管保留；日常补液无螺钉拆装。\n82.4仅为贴标高；最大瓶径、柔性操作及密封仍待实测。',179,10,8)
end()

header('总装爆炸与维护分组','按当前模型的维护组件分解；螺钉与柔性路线在主图中隐藏，以突出装配层次。')
mappt=picture('service.png',40,36,195,200)
for pixel,x,y,label,align in [
    ((850,350),19,236,'整体冠盖','left'),
    ((760,480),19,214,'电子／音频托板组','left'),
    ((1000,190),258,229,'两只液瓶包络','right'),
    ((530,600),19,190,'泡泡枪主体','left'),
    ((610,690),19,165,'整体圆环／底槽','left'),
    ((785,780),19,137,'水枪主体','left'),
    ((855,825),258,148,'水枪胶粘底托','right'),
    ((870,585),258,193,'固定头舱','right'),
    ((970,645),258,171,'固定颈架','right'),
    ((1100,885),258,108,'履带动力组件','right'),
    ((760,955),19,80,'充电宝','left'),
    ((850,1040),19,44,'电源内托架／拉带','left')]:
    part_label(mappt,pixel,x,y,label,align)
items=[('01 整体冠盖','4 颗紧固；上提 65。顶甲、效果护框与标识、前后眉甲随盖移动。'),('02 电子 / 音频托板','4 颗紧固；断开线管后上提 85。图中仅错开 35，以便看清层次。'),('03 两只成品液瓶','抽出目标吸管、解开目标绑带，整瓶上取150；另一瓶及软管可保留。无打印上盖。'),('04 一体底盖 / 电源内托架','先拆6颗底盖螺钉；电源仍留机内。更换电源时再拆内托架4颗螺钉，下移60。'),('05 固定头舱 / 颈架 / 底座','保持组装；履带和驱动来源部件不在本次维护爆炸中分解。'),('06 水枪与泡泡枪','水枪先脱胶、抬起再沿枪轴前抽；泡泡枪抬尾后退脱环、侧移取出。固定与拆装详见第14-17页。')]
y=236
for heading,body in items:
    text(268,y,heading,11,bold=True);y=para(268,y-8,body,132,9,5)-8
para(268,64,'点火本体移至背包外侧，见26页。头部电子组为100×85×36整板包络，独立元件位置待核。',132,9,6)
para(268,44,'浅托盘4颗侧耳螺钉；旧主控小托架及压架6颗紧固件取消。底盖6颗；电机固定面与底盘一体，无端板锁紧螺钉。',132,8,5)
end()

header('内部路线、装配顺序与验证边界','黄色为电源线 / 插头包络；青色为喷水软管路线。头端电源线改经托盘后缘；路线为设计分配，不是完整接线或已验收液路。')
labeled_picture('routing.png',30,102,173,130,[
    ((868,402),20,240,'面包板整组包络','left'),
    ((855,510),219,221,'电源线／颈部导向','right'),
    ((1146,395),219,201,'泡泡液管（候选）','right'),
    ((672,620),20,180,'喷水管（Ø5实测）','left'),
    ((692,714),20,153,'水枪尾线插头占位','left'),
    ((920,840),219,141,'清水瓶包络','right'),
    ((1055,790),219,119,'泡泡液瓶包络','right'),
    ((555,733),20,103,'充电宝包络','left')])
title(23,78,'路线与维修关系')
para(23,67,'电源线候选 Ø6，从中央干区经过固定颈架进入头舱。\n两枪自吸（用户确认），液管从液舱顶部插入，经两侧接前枪；头端Ø6候选线束经托盘后缘开口。\n拆托板前先断开相关线管；未表达高压接线。',190,10,7)
y=238
for h,s in [('装配次序','动力与底座 → 电源内托架和一体底盖 → 冠盖定位与设备托板 → 两液体舱单独试验 → 布线后复查维护动作。'),('当前 CAD 证据',f"{len(report['objects'])} 个几何对象回读有效；{report['collision_check']['boolean_pairs_tested']} 对布尔检查发现 {len(report['collision_check']['overlaps'])} 对超阈值重叠；{len(report['service_paths']['scenarios'])} 组维护动作共 {sum(r['pose_count'] for r in report['service_paths']['scenarios'])} 个离散姿态，{sum(not r['passed'] for r in report['service_paths']['scenarios'])} 组未通过。"),('尺寸与图纸等级','蓝色尺寸为当前 CAD 设计值；充电宝 120 × 73 × 31.5 为用户提供。尺寸不含制造公差。未实测接口与紧固件只用于结构评审。'),('尚待实物确认','端口位置、手指与工具空间、连续拆卸路径、线管弯曲、真实设备固定、承载、密封排液和供电。未通过制造、电气或儿童使用验收。')]:
    text(235,y,h,12,bold=True);y=para(235,y-8,s,167,10,6)-9
box(14,25,392,16,PALE)
text(20,35,'几何源：hardware/model/'+meta.get('source_document','CyberTrack.FCStd')+' · 生成时核对源模型与预览图哈希。',9)
text(20,29,'SHA-256：'+meta['source_sha256'],8,MUTED)
end()
header('面包板整组 · 头部原外形内布局','沿用0.41：用户指定100×85×36规划包络；不拆分假造内部设备位置，头舱不布置点火模块。')
picture('breadboard-layout.png',18,105,188,134)
picture('breadboard-top.png',216,105,188,134)
text(110,95,'透明头壳／整板与浅托盘',11,bold=True,align='center')
text(310,95,'俯视／100沿左右、85沿前后',11,bold=True,align='center')
box(14,29,392,56,PALE)
para(21,74,'整组包络：X=-50…50；Y=-70…15；Z=174…210。左右100、前后85、高36。\n距冠盖最小4；头部外形、冠盖分缝及冠盖四孔保持，内部支柱局部重建。\n旧裸ESP32小托架、排母、防脱架、独立扬声器及前上方剩余电子占位由整组包络替代。',375,10,7)
para(21,46,'36为包含底板、元件、插头和线束的规划总高，不是实测。屏幕视窗、收音／出声、USB与天线仍需按实物复核。\n整板向上防脱压片需先确认塑料底座可接触边缘，本轮不假定元件顶面能够承压。',375,9,7)
end()
header('浅托盘 · 侧耳固定与内部承托','主体105×90、内区101×86；四周单边0.5是设计余量，非已验证制造公差。')
picture('breadboard-tray.png',20,112,180,125)
p,b=drawing('tray',310,171,1.1)
title(242,239,'托盘俯视／比例1.1:1')
hdim(p,-61,61,-40,-40,-87,'122 含侧耳')
hdim(p,-24.5,24.5,-70.5,-70.5,-78,'49 前缘让位／深2')
hdim(p,-57,57,-5,-5,29,'114 孔距')
vdim(p,-40,-5,57,57,76,'35 孔距')
box(14,29,392,65,PALE)
para(21,83,'托盘底面Z171.5、承托面Z174；底厚2.5，围边到Z177，高3。主体105×90，内区101×86。\n侧耳四孔X±57、Y=-40 / -5；Ø3通孔与M2.5级螺钉／嵌件均为候选。\n内部四柱Ø7；上承台Z171.5。支柱与头壳融合，外壳外轮廓保持。后缘留宽10线槽；前缘中央49×2让位。',375,10,7)
para(21,55,'围边只限制水平滑动；塑料底座边缘、压片接触位置和向上防脱保持力待实测。\n后缘Ø6候选线束与托盘／面包板分别检查；折线路线不等于实际弯曲半径或接头装配通过。\n材料、打印方向、柱根强度、嵌件保持力、线束应力释放和防松未验收。',375,9,7)
end()
header('整板上取 · 螺钉、工具与拆装路径','先断电、拆冠盖、断开并收置对外线束；板内跳线可保留，手指与柔性线束操作另验。')
picture('breadboard-service.png',18,113,188,126)
picture('breadboard-access.png',216,113,188,126)
text(110,103,'托盘连整组包络上提85',11,bold=True,align='center')
text(310,103,'四处Ø8直工具杆审查',11,bold=True,align='center')
para(21,88,'1. 断电，卸冠盖4颗螺钉，冠盖整体上取。\n2. 断开并收置超声波及对外线束，保留板内接线。\n3. 卸浅托盘4颗侧耳螺钉，各沿+Z退出20。\n4. 前缘让位托盘连组件沿+Z上提85。\n不得拉住跳线提取；实际抓取位置仍需试装。',183,10,7)
para(220,88,'已检查：整盘连续保守棱柱扫掠、四颗螺钉连续退出、四处Ø8×90直工具杆。\n反例：保留冠盖、保留托盘螺钉均应阻挡拆出；组件增加5高度应碰冠盖。\nUSB插拔、屏幕／音频位置和天线净空未建模，不沿用旧裸板检查结果。',179,10,7)
box(14,25,392,18,PALE)
text(21,36,'通过仅指规定包络与刚性路径；不代表实物装配、振动保持、强度、声学或射频通过。',9,MUTED)
end()
header('拆出水枪 · 实测尺寸与候选布局','长 138.5、最粗处宽 33.2、厚 24.6、带管宽 38.5；喷嘴、接头和前段轮廓为示意，不是接口测量。')
picture('water-gun-component.png',14,140,185,99)
picture('water-gun-layout.png',208,117,198,125)
text(106,130,'独立总成 / 总尺寸实测，分段形状假设',10,bold=True,align='center')
text(307,106,'头舱下方、颈架左侧 / 前向上仰 15°',10,bold=True,align='center')
para(20,114,'0.39 喷嘴端中心 (55, -131.00, 148.17)。\n两枪均上仰15°；旋转后前移10、上移3；复查头壳与底座。\n原完整尺寸包络随枪体刚性变换；接管仍朝+X。',180,10,7)
w=report['water_gun_check']
nearest=w['nearest_clearances'][0]
box(14,28,392,55,PALE)
para(21,72,f"0.25 保留左右定位挡板与底部双面软胶，外侧前后挡板均设上开口托管座，尾线导向鞍并入底托；无压盖和横向紧固。\n裸枪33.2宽检查挡板与整机，带管38.5宽检查夹具以外障碍；最近间距 {nearest['distance_mm']:.2f} mm（不含胶面）。\n粘接已解除且线管断开后，先沿底板法向抬起2，再沿枪轴向前150；裸枪、示意接头及外部带管包络连续扫掠通过。",375,9,7)
para(21,45,'胶厚暂按1；水枪位置及15°上仰保持。两块胶面与示意枪底接触，仅是几何接触核对。\n胶带型号、耐水、温度、脉冲载荷下保持力和脱胶方法未定；检查不构成粘接或实物拆卸验收。',375,9,6)
end()
header('水枪胶粘底托 · 底部双面软胶固定','按用户选择采用底部双面软胶；保留左右定位挡板、后挡和尾线导向；外侧双托管槽向上开放，尾线导向鞍与底托一体。')
picture('water-gun-mount.png',14,123,193,119)
mappt=picture('water-gun-service.png',222,140,174,85)
for pixel,x,y,label,align in [
    ((549,546),215,235,'水枪主体','left'),
    ((990,620),311,132,'胶粘底托','left'),
    ((860,590),311,242,'双面软胶×2','left'),
    ((1195,585),405,221,'一体尾线导向鞍','right'),
    ((1230,565),405,238,'尾线插头占位','right')]:
    part_label(mappt,pixel,x,y,label,align)
text(110,113,'左右挡板定位 / 顶部开放 / 外侧托管',11,bold=True,align='center')
text(309,113,'已解除粘接后的分解示意',11,bold=True,align='center')
para(20,99,'底托主板38.4×74×3；左右净宽34.4，单侧留0.6。\n两块双面软胶占位31.2×20，厚1，模块坐标中心Y=-62 / -10。\n两对挡板长12、高20、厚2；不设上压唇或侧垫。\n底托仍用2颗M3级候选螺钉连接左肩梁；模块内孔位及胶粘关系保持。\n双托管槽Ø5.6×6、间距52，紧贴挡板；尾鞍与底托一体。',183,9,6)
para(220,99,'拆装顺序\n1. 断电排液，断管后从双托座上提，断尾线并释放扎带。\n2. 先充分解除底部粘接；脱胶工艺和工具可达未验。\n3. 沿倾斜底板法向抬起2，再沿枪轴前方取出150。\n4. 若拆底托：卸基座2螺钉，沿底板法向抬2后外移60。',180,9,6)
box(14,27,392,32,PALE)
para(21,49,'双面软胶是当前保持方式；左右挡板与后挡仅用于定位，不代替胶粘保持力。基座螺钉固定底托，不直接锁住水枪。\n胶面按未压缩1厚占位，类型、实际厚度、表面处理、耐水与温度性能及重复拆装后的保持力待实测。\n枪体与空底托扫掠、6项线管／基座工具空间及两处局部管段上提10检查通过；未模拟剥离、手部或脱胶工具。',375,9,7)
end()
header('水管与尾部引线 · 路线及操作预留','青色为水管预留，黄色为线束、插头与工具预留；这些是空间假设，不是已选连接器或布线规格。')
labeled_picture('water-gun-spaces.png',29,97,197,132,[
    ((1100,250),20,239,'顶部供液管／路线预留','left'),
    ((660,770),20,89,'接管拔出空间','left'),
    ((1051,675),241,217,'尾线插头／拔出空间','right'),
    ((885,693),241,113,'外侧双托管座','right')])
text(126,72,'半透明体为审查空间，实体接触按操作步骤区分',10,bold=True,align='center')
para(251,236,'水管\n用户实测外径5；中心R8为假设，另留Ø8路线空间。\n打印背包盖已取消，实际瓶盖接口待定；枪侧接管沿+X拔30，操作包络Ø16。\n前后双托槽Ø5.6×6、间距52；沿外侧接顶部吸管，无后护甲穿管。',151,10,7)
para(251,174,'尾部引线\n模块坐标枪尾Y=9.5；Ø3线束随枪体倾斜后转至外侧；中心弯曲半径 8，路线预留 Ø8。\n插头候选 16×10×10，沿 +X 拔出 16；尾线导向鞍与扎带槽并入底托；扎带与抗拉待选。',151,10,7)
para(251,112,'工具\n水枪取消压盖及对应工具空间。\n基座螺钉：先脱胶并取出枪体，再用朝前操作的短臂内六角；端部Ø3、杆部Ø6、前伸臂40。\n仅检查基座工具杆，不包括手掌、把手转动或脱胶工具。',151,9,6)
box(14,27,392,31,PALE)
para(21,48,'Ø8水管审查区仅在托管座处允许重叠；实际Ø5管与托座另检，间隙0.3。尾线导向鞍同样单独检查实际线束。\n软管压力、最小允许弯曲半径、线尾抗拉、插头保持力和带液工作未测；先核实实物与胶粘保持性能，再确定材料和加工公差。',375,9,7)
end()
header('前置双枪 · 上仰15°与整体圆环','正面看左泡泡、右水枪；15°为设计候选。新薄片部件独立保存，原始模型与照片保留。')
picture('front.png',14,126,190,114)
labeled_picture('bubble-gun-mount.png',226,137,167,91,[
    ((500,428),215,239,'整体前圆环','left'),
    ((1010,717),405,130,'两段底槽／支架底座','right')])
text(109,115,'双枪上仰15° / 水枪前移10、上移3',11,bold=True,align='center')
text(309,115,'前圆环无分缝 / 后部两段底槽',11,bold=True,align='center')
para(21,102,'泡泡枪口中心(-55,-120.49,126.52)。\n水枪口中心(55,-131.00,148.17)；两轴同为上仰15°。\n泡泡平放基准：圆底离平面4.7，薄片6×25×6.8。\n31.5+4.7=36.2与原总高35.8的0.4差异仍待核对。',184,9,7)
para(220,102,'整体环孔34／外径39／厚3；径向间隙1.25。\n无前环螺钉；仅2颗M3级基座紧固候选。\n底槽名义后6宽×25长、前10宽，净宽6.4／10.4。\n前段长19为假设；槽端导入斜面、前后止挡与0.6底垫。',181,9,7)
box(14,28,392,36,PALE)
para(21,54,'用户拟用热熔胶／胶水辅助固定；圆环、阶梯槽与前后止挡定位。胶材、用量、粘接兼容性及保持力未确定。\n胶点需可接近清除，避开内部运动件；拆卸先清胶。前止挡依赖假设的前底轮廓，实物试配后再确定。\n15°不代表允许工作倾角；上仰时出泡、喷水、滴液／倒流、固定保持和真实拆装仍需实物验证。',375,9,7)
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
    ((553,560),215,240,'尾线插头预留','left'),
    ((994,330),405,237,'泡泡液舱吸管','right'),
    ((600,700),215,131,'基座工具空间','left'),
    ((644,470),405,131,'泡泡液管／路线预留','right'),
    ((730,624),405,192,'本地停止按钮／指端空间','right'),
    ((1210,580),405,157,'相邻喷水管','right')])
text(110,119,'抬尾15°，后退脱环，再向外取出',11,bold=True,align='center')
text(310,119,'线管和基座工具预留 / 非实际接线',11,bold=True,align='center')
para(21,105,'1 断电排液、清除辅助胶，先拔插头移开尾线，再断管。\n2 围绕圆环中心抬尾15°，沿模块后方退10，脱离圆环。\n3 沿模块上方抬3，再向车体右侧(-X)移90；安装反向。\n4 空托架卸2颗基座螺钉，沿底板法向抬6、向-X移90。',183,9,7)
para(220,105,'泡泡管顶部插入液舱，沿侧面接前枪；Ø4管／Ø3尾线、中心R8及Ø8预留均为候选。\n接管沿模块后方拔25；16×10×10插头向-X拔16。\n前圆环为整体，不设分缝、衬垫或前环工具空间。\n基座工具在主体取出后使用；不包含整手与把手。',181,9,7)
box(14,27,392,36,PALE)
para(21,53,'主体每0.5°转动、每0.5后退／抬升、每2侧移检查示意实体；实物外形和采样之间的连续空间尚未证明。\n空托架、基座螺钉另做保守连续扫掠；前向Ø36×50通道随枪轴上仰。停止按钮保留前方Ø12指端空间。\n宽度、薄片偏置、前槽长度与前底轮廓待实测；胶粘保持、线管防磨、防拉脱、排液及制造均未验收。',375,9,7)
end()
header('超声波双探头 · 实测尺寸与前脸候选','圆柱尺寸来自用户；中心距为推导；PCB面Y=-77.5基准、Ø16.6开孔和端面分色均为候选。')
title(26,235,'正面双探头','沿 +Y 观察；比例 2:1；中心 Z188')
p,b=drawing('ultrasonic_front',110,190,2)
hdim(p,-13,13,188,188,205,'26 中心距（推导）')
hdim(p,-21,21,180,180,174,'42 外沿总宽')
vdim(p,180,196,-21,-21,-29,'Ø16')
title(235,235,'侧面突出高度','沿 -X 观察；比例 2:1；前方在左')
p,b=drawing('ultrasonic_side',310,190,2)
hdim(p,-87.8,-77.5,196,196,206,'10.3 从候选PCB面计')
leader(p(-81,180),337,158,'前脸外表面 Y=-81')
picture('ultrasonic-layout.png',21,62,176,77)
text(109,53,'前脸候选 / 非实物安装照片',10,MUTED,align='center')
para(221,130,'输入：两圆柱Ø16、总宽42、离面板高10.3。\n推导：中心距26、圆柱净距10；中心X±13。\n面板：原孔补回，改为双Ø16.6贯穿候选孔。\n单边0.3为设计值；PCB／背面占位见第25页。\n探头内退3.5，露出前脸6.8；实际基准待确认。',178,10,8)
box(14,27,392,19,PALE)
para(21,39,'CAD检查使用完整实心圆柱包络，包含实体与预留空间。PCB／接头尺寸、安装基准、固定件及声学性能仍需实物核对。',376,9,6)
end()
header('双枪供液 · 全部从顶部插入','水枪和泡泡枪可自吸：用户于2026-10-24确认。后护甲和液舱侧壁均不设液管孔；以下为管路候选。')
p,b=drawing('top_feed_top',111,162,0.6)
title(21,240,'俯视 · 两路分别向同侧引出','沿 -Z 观察；比例 0.6:1；前方在下')
leader(p(-28,65),21,217,'泡泡入口 X−28／Y65')
leader(p(28,65),145,217,'喷水入口 X28／Y65')
p,b=drawing('top_feed_side',305,170,0.8)
title(223,240,'侧视 · 吸管伸入液舱','沿 -X 观察；比例 0.8:1；两舱投影重合')
line(*p(65,45),*p(65,154.5),BLUE,.6,[3,2])
text(331,132,'虚线：舱内吸管轴线',9,MUTED)
part_label(lambda x,y:(x,y),p(65,45),264,109,'瓶内候选管端Z45；非实测吸管长度')
box(14,29,392,62,PALE)
para(21,80,'取消打印背包盖；实际瓶盖接头未定。喷水管Ø5为实测，泡泡管Ø4、中心弯曲R8及Ø8路线预留为候选。\n吸管从瓶顶插入，两路上段中心线Z174，各自向对应枪侧引出；不横跨另一瓶，也不绕后护甲。\n补液：断电、处理残液、抽出目标吸管、解开目标绑带、整瓶上取150；柔性抽管及绑带收置尚未实测。\n自吸能力不等于本布置已验收：实际吸程、首次引液、漏气、通气防溅、管口固定与离底距离需实测。',375,10,10)
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
header('L298N 驱动板 · 独立包络与干舱竖装候选','用户尺寸长46.2 × 宽43.5 × 高27.5；橙色为整板矩形包络，无推定安装孔或内部器件。')
picture('l298n-layout.png',16,101,208,144)
picture('l298n-side.png',230,138,170,106)
title(232,127,'下部两台电机之间；前方 −Y')
para(232,119,'长边沿+Z、宽边沿−X、原高度沿−Y。\n世界包络：X±21.75；Y−4…23.5；Z32…78.2。\n电源线示意改为板前上升，再接原颈架通道。\n新增开口托框、顶盖吊架与底盖通风开口。',172,10,8)
box(14,28,392,65,PALE)
para(21,81,'含托框及夹件后的名义净距：\n左右电机各2.96；后隔板0.50；底盖0.40；\n充电宝6.26；电源线占位1.00 mm。\n0.34整组下取80 mm连续扫掠通过；\n后隔板和底盖间隙须重点试配。',184,10,9)
para(218,81,'独立板卡包络保持；原图确认器件分布。\n四角孔径／孔距没有实测，采用可调边缘夹持。\nPCB接触区、焊脚高度、真实插头与线径待核；\n几何通过不代表温升、绝缘、固定强度、\n公差或实物装拆通过。',182,10,9)
end()
header('L298N 固定与拆装 · 开口托框候选','两根顶盖一体吊柱承重；底盖独立拆卸；四点侧压不使用未测的PCB安装孔。')
picture('l298n-carrier.png',15,131,124,111)
picture('l298n-service.png',144,131,124,111)
picture('l298n-spaces.png',273,131,132,111)
title(19,123,'开口托框／机外调夹紧')
title(148,123,'断线后整组向下取出')
title(277,123,'接线与空气几何预留')
para(19,114,'托框底板2厚，后导柱3×4。\n4颗M2级侧压件＋绝缘候选垫。\n中央背面避开焊脚，顶止挡留0.8。\n接触点及夹紧力需实物核对。',119,9,7)
para(148,114,'底盖6颗→断线→托住托框\n→退2颗M2.5级锁紧件→下取80。\n机外松侧压件后板卡向上取出。\n直杆批头Ø3.6通道通过几何检查。',119,9,7)
para(277,114,'两侧电机线廊各宽3.25；\n下沿接口区32×11.5×10。\n底部进风总50、顶部排风总30 mm²。\n端子螺钉在托框取出后操作。',124,9,7)
box(14,28,392,47,PALE)
para(21,65,'检查：保存回读、静态干涉、托框连续下取、锁紧螺钉退出、底部接线入口和通风开口。\n边界：空气空间不是实体风管或热性能证明；孔口未做防水，后湿舱隔板保持。\n照片只能确认器件拓扑，不能提供精确接触面；PCB边缘、真实接头、线弯、手指及工具手柄仍待试配。\n本页及独立托框文件用于结构评审；材料、螺纹、强度、公差与温升未验收，不是加工放行。',378,10,9)
end()

header('超声波与面包板 · 候选共存及拆装','沿用0.41：头壳、前脸孔、冠盖保持；PCB、背面、向上接头及线束均明确为未实测候选。')
picture('ultrasonic-coexistence.png',16,129,190,112)
picture('ultrasonic-service.png',215,129,190,112)
text(110,120,'蓝：PCB／橙：背面／紫：接头／黄：线束',10,bold=True,align='center')
text(310,120,'先收置线束，整盘上提85',10,bold=True,align='center')
para(21,108,'PCB：左右45×上下20×厚1.6；背面深4。\n45×20借用通用整模块资料，其余为布局假设。\n向上接头：左右12×前后6×高8；线束Ø4。\n到面包板：背面1.9、接头／线束1.5。\n接头到冠盖约0.90，须实测与公差复核。\n若接头向后伸10，将侵入面包板8.1。',183,10,8)
para(220,108,'托盘前缘中央49×2让位，四孔及后槽保持。\n原前缘会扫到模块；线束未收置也会阻挡。\n取盘后释放待设计固定件，超声波先后退11，\n使探头脱孔，再上提70；连续刚性扫掠通过。\n10.3暂从PCB面计，探头内退3.5、外露6.8。\n真实接头、板端、固定与手部操作仍待确认。',181,10,8)
box(14,27,392,22,PALE)
para(21,41,'本页包络来自候选空间分配，不能当作供应商接口或实物安装通过。线束折线不代表真实弯曲半径，\n末端只到侧边交接区；尚未确定面包板实际接口。头部外壳几何保持，探头突出量改变。',376,9,6)
end()
header('背包外侧本体 · 分体夹环与拆装','0.42：仅被动机械本体与夹持候选；无高压引线、电极或驱动。头壳和前斜坡保持。')
picture('effects-clamp.png',18,132,186,111)
picture('effects-service.png',215,132,188,111)
text(110,122,'单侧：两道夹环 / 底托 / 上限位',11,bold=True,align='center')
text(310,122,'取下外半夹环后，本体向上90',11,bold=True,align='center')
para(21,109,'本体Ø25.5×70；中心X±74、Y85，Z54…124。\n夹环中心Z86、114；外径31.5，衬垫座孔26.5。\n软衬0.5、底垫1 mm；名义接触，未建压缩。\n内半夹环、底托和连接肋与背包护壳一体。\n每半环2颗M2.5级候选螺钉，全机8颗／8嵌件。\n外半夹环分缝0.6；上环带顶部限位。\n固定件最后侧Y107.5，比原脊条后伸10.5。\n两侧最外X±89.75，仍收在履带X±114内。',184,9.5,8)
para(220,109,'先断电、解除实际线束并托住本体。\n本侧4颗螺钉向外退出35；取下两外半夹环。\n夹环向外35以21个姿态检查；并非连续验证。\n本体向上90及螺钉退出用连续扫掠检查。\n上夹环未拆时，顶部限位会阻挡本体上取。\n液瓶按原步骤上取150，本体夹具保持原位。\n工具检查只覆盖Ø3直杆，不含手柄／手掌。\n端部、真实夹持区、紧固力及材料均待实测。',182,9.5,8)
box(14,27,392,16,PALE)
para(21,37,'模型无干涉不等于夹持可靠或绝缘通过。不得把软垫厚度、机械间隙、与液瓶的距离作为高压安全参数。',376,9,6)
end()

header('底盘效果板 · 承板固定与下取','0.43：底盘前斜坡不变；四耳加厚并开沉台，螺钉头收进承板底面以内。')
picture('effects-tray.png',18,136,188,107)
picture('effects-tray-bottom.png',215,136,188,107)
text(110,126,'充电宝上方：四板凹座及防脱压框',10,bold=True,align='center')
text(310,126,'四点：X±47 / Y−49、−26.5',10,bold=True,align='center')
picture('effects-tray-service.png',18,35,183,83)
para(215,115,'主底板Z66.5…68.5；四耳厚4。\n固定孔距94×22.5，4颗M2.5级候选螺钉。\n螺钉头底Z66.6，比盘底收进0.1。\n先拆底盖、充电宝及托架，收置中央电源线。\n断开整盘对外接线，托住承板、退出4螺钉。\n承板连四板、压框及局部线束向下取100。\n局部线束退出采用分段保守扫掠。\n先取整盘，才能在机外拆压框及板卡。\n工具仅检查直杆，不含手掌或手柄。\n下取到下壳最近0.8，需核对装配偏差。',188,9.5,8)
text(110,29,'向下取盘示意：充电宝已移除',9,align='center')
end()

header('四块板 · 独立开窗防脱压框','0.43候选：不虚构PCB安装孔；固定方式依赖未实测的板厚及无元件边缘。')
picture('effects-board-mount.png',18,131,188,112)
picture('effects-board-service.png',215,131,188,112)
text(110,121,'四个凹座 / 四个独立压框 / 八颗M2级螺钉',10,bold=True,align='center')
text(310,121,'机外先拆框，再向上取板',10,bold=True,align='center')
para(21,108,'MOS外包络33×17×12，高12仍为预算。\n降压板20×11×5采用用户尺寸。\nPCB厚1.6、四边2.5无元件区均为假设。\n板底Z68，PCB上表面Z69.6。\n1 mm深浅座，底部剩1 mm结构厚度。\n两条0.5板边垫；中央板底余量0.5。\n侧向余量0.5；压框与PCB上方留0.4。\n框到固定耳0.5／内柱约0.7，待试配。',183,10,8)
para(220,108,'先整盘取出，断开／收置本板接线。\n退出本框两颗M2级螺钉，上退20。\n压框上取20，随后板卡上取20。\n图示爆炸距离用于分辨对象，不是同步动作。\n保留压框、保留螺钉均作为阻挡反例。\n元件占满板边时会碰框：不能忽略该前提。\n压框不预紧元件；真实保持力及公差待验。',183,10,8)
box(14,27,392,16,PALE)
para(21,37,'实测无元件／无焊脚区、端子位置和板厚后才能定型；不能把候选边缘空白当作供应商尺寸。',376,9,6)
end()

header('接线空间与装配余量','0.43：局部低压布线预算，不定义针序、线径额定值或实际连接器；未涉及高压接线。')
picture('effects-board-wiring.png',18,110,192,133)
text(114,101,'半透明：板端接线区与线束通道',10,bold=True,align='center')
para(220,233,'每板内／外端各一处接线空间，外伸4。\nMOS预算4×8×4.5及4×4×4.5。\n降压板两端各4×4×2.5，方向未实测。\n中央5×4共享通道；两侧Ø3线路预算。\n端部重叠属于同一接线分配，不当作多条\n独立已布线回路；实际供电／控制须复核。\n外部主控、枪体及电源端接尚未完整布置。\n线路下取到顶盖约0.557，需核对真实线束。',183,10,8)
box(225,83,171,58,PALE)
text(233,129,'承板下方最小名义间隙：2.0 mm',12,bold=True)
text(233,115,'螺钉头：66.6 − 64.5 = 2.1 mm',10)
text(233,101,'承板底：66.5 − 64.5 = 2.0 mm',10)
text(233,89,'旧0.42螺钉头间隙为0.5 mm，已替代',9)
para(21,79,'余量是设计预算，尚不是实物保证。需核实充电宝真实最大厚度、打印／加工尺寸、承板翘曲、装配偏差，\n以及垫片／贴膜等叠加量；按最不利组合重新计算剩余间隙，并用实物试装确认。不得另加垫片后沿用2 mm结论。\n抬高整盘会挤占顶盖与L298N空间，因此采用凹入紧固件和低位板边固定；不扩大底盘外形。',376,10,8)
end()
header('MT3608 升压板 · 实测包络与干舱位置','P06／H13：37×18×6 mm；充电宝5 V经此板升至12 V供L298N；本页只记录机械包络。')
labeled_picture('mt3608-layout.png',20,65,245,180,[((925,540),256,228,'MT3608／37×18×6','right')])
para(275,233,'用户实测：长37／宽18／厚6 mm。\n长边沿+Y，宽边沿−X，厚度沿+Z。\n范围：X25…43、Y−17…20、Z82…88。\n\n底盘侧壁、顶盖名义净距各2 mm。\n距L298N托框约3.83 mm。\n前后各4 mm为局部接线预算。\n\n固定件、孔位和PCB接触面未设计。\n接头、焊脚与电位器位置待核。',123,10,6)
para(21,52,'拆装边界：断电断线，按既有流程先拆L298N托框及左电机（含先拆电源内托架与本侧履带），\n释放待设计固定件后，裸板沿−Z下取90 mm。电位器暂按取出后调节；不表示在位工具或完整线束通过。\n静态／接线空间及裸板连续扫掠通过；固定保持力、实际装拆、公差、散热与供电能力仍须实物验证。',375,10,6)
end()

catalog_result=render_catalog(globals(), CATALOG, CATALOG_SHEETS)
assert page==TOTAL_PAGES, 'Drawing index and total page count differ'
c.save()
(MODEL/'assembly-annotation-audit.json').write_text(json.dumps({
    'revision':'0.44', 'source_sha256':meta['source_sha256'],
    'pdf_sha256':sha(PDF), 'page_count':page,
    'card_count':sum(len(sheet['cards']) for sheet in CATALOG_SHEETS),
    'object_count':len(CATALOG), 'annotated_object_count':len(catalog_result['entries']),
    'nonphysical_space_count':sum(e['category']=='clearance' for e in CATALOG.values()),
    'missing_objects':sorted(set(meta['objects'])-set(CATALOG)),
    'removed_old_pages':[2,3,13,22,27,30,31],
    'geometry_modified_by_pdf_generator':False, 'geometry_change_audit_sha256':sha(MODEL/'mt3608-change-audit.json'), 'physical_fit_verified':False,
    **catalog_result,
},ensure_ascii=False,indent=2))
print(PDF)
print('Pages:',page)
