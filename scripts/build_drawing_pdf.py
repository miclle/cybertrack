"""Rebuild the complete A3 assembly/maintenance review from current native CAD.

Run export_drawing_geometry.py first. No historical screenshots or fixed-revision
geometry assertions are used. Known fit conflicts require an explicit review flag.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from assembly_catalog import build_catalog, render_catalog, SYSTEMS

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--allow-review-conflicts',action='store_true')
args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'tmp/pdfs'
MODEL=ROOT/'hardware/model'
PDF=MODEL/'CyberTrack-assembly-and-service.pdf'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
meta=json.loads((DATA/'dimensions.json').read_text())
report=json.loads((MODEL/'readback.json').read_text())
pp02=json.loads((MODEL/'pp02-adjustment-audit.json').read_text())
DETAILS=json.loads((DATA/'assembly-details.json').read_text())
source=MODEL/meta['source_document']
delivery=MODEL/'CyberTrack.FCStd'
assert sha(source)==meta['source_sha256']==DETAILS['source_sha256']
delivery_hash=sha(delivery)
tail=None
pre_tail_source,pre_tail_delivery=meta['source_sha256'],delivery_hash
if report.get('bubble_tail_height_audit'):
    tail=json.loads((MODEL/report['bubble_tail_height_audit']).read_text())
    assert tail['geometry_and_export_checks_passed'] and tail['bottom_tab_unchanged'] and tail['saved_and_reopened']
    assert tail['source_sha256']==meta['source_sha256'] and tail['delivery_sha256']==delivery_hash
    assert tail['shell_height_mm']==35.9 and tail['tab_height_mm']==6.8
    assert set(tail['changed_source'])=={'BubbleGunGearcase','BubbleGunInspectionEnvelope'}
    pre_tail_source=tail['baseline_files'][meta['source_document']]
    pre_tail_delivery=tail['baseline_files']['CyberTrack.FCStd']
cable=None
if report.get('cable_passage_audit'):
    cable=json.loads((MODEL/report['cable_passage_audit']).read_text())
    assert cable['scope_passed'] and cable['saved_and_reopened'] and cable['checks']['passed']
    assert cable['source_sha256']==pre_tail_source and cable['delivery_sha256']==pre_tail_delivery
    assert cable['baseline_files'][meta['source_document']]==pp02['source_sha256']
    assert cable['baseline_files']['CyberTrack.FCStd']==pp02['delivery_sha256']
    assert not any(n.startswith(('Bubble','PrintBubble')) for n in cable['changed_source'])
else:
    assert pre_tail_source==pp02['source_sha256'] and pre_tail_delivery==pp02['delivery_sha256']
assert pp02['geometry_and_export_checks_passed']
assert pp02['ring']['bore_diameter_mm']==32 and pp02['ring']['notch_width_mm']==7.5
assert pp02['ring']['notch_depth_mm']==2.3 and pp02['ring']['foot_width_mm']==20
cad_checks_passed=pp02['assembly_fit_passed'] and report['collision_check']['passed'] and report['service_paths']['passed']
assert cad_checks_passed or args.allow_review_conflicts,'Use --allow-review-conflicts for the explicitly marked current fit-conflict review.'
expected_names={o['name'] for o in report['source_feature_objects']}|{o['name'] for o in report['print_consolidation']['parts']}
assert set(DETAILS['objects'])==set(meta['objects'])==expected_names
assert not {'BubbleGunSlotWall1','BubbleGunSlotWall6'} & expected_names
CATALOG,CATALOG_SHEETS=build_catalog(DETAILS['objects'],cable_passage=bool(cable),tail_height=bool(tail))
# 7 overview/dimension pages, 14 system pages, 2 control details, 1 evidence page.
FRONT_PAGES=24
TOTAL_PAGES=FRONT_PAGES+1+len(CATALOG_SHEETS)
SYSTEM_PAGE_REFS={g:str(8+i) for i,g in enumerate(SYSTEMS)}
SYSTEM_PAGE_REFS['B']+='、22-23'
SYSTEM_PAGE_REFS['K']='6-7、'+SYSTEM_PAGE_REFS['K']
REVISION=report.get('local_revision',report['design_revision'])
for name,file in [('ZH','STHeiti Light.ttc'),('ZHB','STHeiti Medium.ttc')]:
    pdfmetrics.registerFont(TTFont(name,'/System/Library/Fonts/'+file,subfontIndex=0))
U=72/25.4
INK='#1E303B';MUTED='#536673';ACCENT='#C55722';PALE='#EAF0F2';BLUE='#287E96'
c=canvas.Canvas(str(PDF),pagesize=(420*U,297*U),pageCompression=1)
c.setTitle('CyberTrack 整机装配与维护 · '+REVISION)
c.setAuthor('CyberTrack')
c.setSubject('Current native CAD review; known PP02 fit conflict; not manufacturing release')
page=0
projection_keys=set()
color_views=json.loads((DATA/'colors/manifest.json').read_text())
assert color_views['source_sha256']==meta['source_sha256']
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

def end():c.showPage()

def title(x,y,s,sub=''):
    text(x,y,s,12,bold=True)
    if sub:text(x,y-7,sub,9,MUTED)

def drawing(key,cx,cy,scale=1):
    projection_keys.add(key)
    d=json.loads((DATA/f'{key}.json').read_text())
    assert d['source_sha256']==meta['source_sha256'] and d['projection_revision']==3, f'Stale projection: {key}'
    b=d['bounds']
    mx,my=(b[0]+b[2])/2,(b[1]+b[3])/2
    def pt(x,y):return (cx+(x-mx)*scale,cy+(y-my)*scale)
    color=color_views['views'][key]
    image_path=DATA/color['image']
    assert color['source_sha256']==meta['source_sha256'] and color['render_revision']==2
    assert color['projection_sha256']==sha(DATA/f'{key}.json')
    assert color['image_sha256']==sha(image_path), f'Stale colour image: {key}'
    x0,y0=pt(*color['bounds'][:2]);x1,y1=pt(*color['bounds'][2:])
    c.drawImage(str(image_path),x0*U,y0*U,(x1-x0)*U,(y1-y0)*U)
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

def bbox(name):return meta['objects'][name]['bbox']

def dim(name,axis):
    b=bbox(name);return b[axis+3]-b[axis]

def f(v):return f'{v:.2f}'.rstrip('0').rstrip('.')


def header(name,subtitle):
    global page
    page+=1
    c.bookmarkPage(f'page-{page}');c.addOutlineEntry(f'{page:02d} {name}',f'page-{page}',level=0)
    c.setFillColor(INK);c.rect(0,278*U,420*U,19*U,fill=1,stroke=0)
    text(14,285,'CYBERTRACK',18,'#FFFFFF',True)
    text(406,285,'ASSEMBLY / SERVICE',10,'#FFFFFF',align='right')
    text(14,265,name,20,bold=True)
    bottom=para(14,256,subtitle,390,9,4.2)
    assert bottom>=246,'Subtitle overflow: '+name
    line(14,245,406,245,'#CAD5DB',.6)
    line(14,20,406,20,'#CAD5DB',.6)
    text(14,13,'2026-10-26 · '+REVISION+' · 单位 mm · PP02 配合未通过',8.5,MUTED)
    text(406,13,f'未制造放行 · A3 横向 · {page} / {TOTAL_PAGES}',8.5,MUTED,align='right')

def fitted(key,cx,cy,w,h,dimension=False):
    d=json.loads((DATA/(key+'.json')).read_text());b=d['bounds']
    scale=min(w/max(b[2]-b[0],.01),h/max(b[3]-b[1],.01))
    p,b=drawing(key,cx,cy,scale)
    if dimension:
        hdim(p,b[0],b[2],b[1],b[1],b[1]-8/scale,f(b[2]-b[0]))
        vdim(p,b[1],b[3],b[0],b[0],b[0]-8/scale,f(b[3]-b[1]))
    return p,b,scale

def block(x,y,heading,body,w=180):
    text(x,y,heading,12,bold=True)
    return para(x,y-9,body,w,10,6)-8

header('整机装配与维护 · 当前模型','从当前保存的原生 CAD 重建彩色实体视图与逐项图卡；图纸用作结构评审，尺寸不含制造公差。')
fitted('iso',116,149,186,171)
text(116,48,'整机轴测 · +X 向左 / +Y 向后 / +Z 向上',9,MUTED,align='center')
y=233
y=block(224,y,'本版状态',('主模型：0.56 + PP02配合待解决。\n已含尾壳35.9、15芯净径10通道、\n六件合并打印件、电源开关和BOOT按钮。' if tail else '主模型：0.55 + PP02配合待解决。\n已含15芯净径10通道、六件合并打印件、\n顶盖电源开关、肩梁BOOT按钮及最新PP02。' if cable else '主模型：0.54 + PP02-2026-10-26。\n已包含辰克5 V电池包、六件合并打印件、\n顶盖电源开关、肩梁BOOT按钮及最新PP02。'),176)
y=block(224,y,'关键更新',('尾壳35.9不含底部薄片6.8；\n承托面至尾顶42.7为推导，15°姿态保持。\nPP02偏心孔Ø32及7.5×2.3缺口保持。' if tail else 'PP02：孔Ø32，孔心局部上移1.3；\n支脚宽20；底部贯穿缺口7.5×2.3。\n删除指定前长槽壁与横挡块，对侧保留。'),176)
y=block(224,y,'配合状态','CAD实体和导出检查通过；PP02仍与现有\n泡泡枪示意外壳相交。装拆路径未重新通过，\n不得以此图册作为配合或制造放行。',176)
block(224,y,'读图顺序',f'2-4 六向尺寸；5 打印划分；6-7 PP02详图。\n8-21 分系统装配；22-23 开关与BOOT。\n24 证据与维护边界；25 索引；26起逐项图卡。',176)
end()

for a,b,title_text,suba,subb in [
    ('front','rear','正面与背面 · 整机几何尺寸','正面：沿+Y观察；+X在右','背面：沿-Y观察；+X在左'),
    ('side','right','左右侧视 · 当前设备布局','左侧：沿-X观察；前方在左','右侧：沿+X观察；前方在右'),
    ('top','bottom','俯视与底视 · 当前装配位置','俯视：沿-Z观察；前方在下','底视：沿+Z观察；前方在下')]:
    header(title_text,'六个方向均保留当前源档零件颜色与透明度；合并打印件只出现一次，不重复叠加其源特征。')
    fitted(a,112,153,164,153,True);fitted(b,312,153,164,153,True)
    text(112,235,suba,11,bold=True,align='center');text(312,235,subb,11,bold=True,align='center')
    box(14,29,392,25,PALE)
    para(21,45,'标注为本视图投影外包尺寸，单位mm；不同视图独立缩放，禁止量图加工。真实插头、软线外伸、材料变形及装配公差未计入。\n隐藏的设备包络与维护空间在对应系统页及图卡中单独表达；PP02的枪体配合冲突见第7页。',375,9,6)
    end()

header('六件合并打印候选 · 装配分界','56个设计源特征归并为6个单实体候选；源特征图卡仅供识别，不能再分别打印或装配。')
for i,row in enumerate(report['print_consolidation']['parts']):
    x=14+(i%3)*132;y=29+(1-i//3)*105
    box(x,y,128,101)
    text(x+5,y+91,row['label'],10,bold=True)
    fitted('part_'+row['name'],x+64,y+56,105,56)
    text(x+5,y+19,'包络 '+' × '.join(f(v) for v in row['size_xyz_mm']),8,MUTED)
    text(x+5,y+9,f"{row['feature_count']}个源特征 → 1个打印实体",8,ACCENT)
end()

header('PP02 · 圆环、支脚与缺口尺寸','外环与安装位置保持；下图左侧使用未倾斜底座局部坐标，右侧为实际15°装配姿态。')
p,b,s=fitted('pp02_ring_local',111,161,140,132)
hdim(p,-74.5,-35.5,110,110,131,'Ø39 外环')
hdim(p,-65,-45,88.95,88.95,82,'20 支脚宽')
hdim(p,-58.75,-51.25,93,93,87,'7.5 缺口宽')
vdim(p,93,95.3,-51.25,-51.25,-30,'2.3 深')
leader(p(-39,111.3),160,197,'Ø32 偏心孔')
leader(p(-55,111.3),156,124,'孔心局部 Z111.3')
fitted('pp02_iso',310,165,170,140)
text(310,80,'PP02 单件 · 删除槽壁1和横挡块6',10,bold=True,align='center')
box(14,28,392,39,PALE)
para(21,57,'原孔Ø34、孔心Z110；当前Ø32、孔心Z111.3。开缺口前内孔最低点Z95.3，相比原Z93抬高2.3。\n缺口宽7.5，从圆孔最低点向下深2.3至Z93，贯穿圆环轴向厚3。支脚20宽，与前伸底板同宽。',375,10,7)
para(21,39,'坐标说明：以上为未施加15°俯仰变换的底座局部尺寸；装配中的世界Z差不能直接代替局部抬高量。',375,9,6)
end()

header('PP02 · 当前配合冲突与维护限制','此页为几何冲突评审；不移动枪体、不忽略相交，也不沿用旧穿环和取枪路径的通过结论。')
p,b,s=fitted('pp02_ring_local',112,162,144,145)
cx,cy=p(-55,110)
c.setStrokeColor(ACCENT);c.setLineWidth(1);c.setDash([4,2]);c.circle(cx*U,cy*U,15.75*s*U,fill=0,stroke=1);c.setDash([])
text(112,66,'实线：当前圆环；橙虚线：枪口Ø31.5轮廓',9,MUTED,align='center')
y=231
y=block(226,y,'已确认的当前结果',f"PP02与BubbleGunShell相交体积约\n{pp02['assembly_overlaps'][0]['volume_mm3']:.3f} mm³。底部缺口已移除中间部分\n相交，缺口两侧仍未避开枪壳。",173)
y=block(226,y,'尺寸关系','枪口示意圆心局部Z110、半径15.75；\n环孔圆心Z111.3、半径16。孔径虽大0.5，\n偏心1.3使下缘仍侵入枪壳。',173)
y=block(226,y,'维护处理','装配前核对真实枪体轮廓与定位面；\n先解决孔形或安装偏置，再重新验证\n插入、尾部入槽、脱胶及取枪路径。',173)
block(226,y,'本版保留的边界','两颗基座螺钉、软垫和枪体独立。\n图卡中的线束、接头与服务空间仍为候选；\n本页无打印公差、材料或保持力验收。',173)
end()

NOTES={
'A': [('装配','先核对成品履带、联轴器与电机接口，再对齐底盘一体端面。每台电机4颗端面螺钉、每侧履带2处安装紧固均为候选。'),('维护','断电、托稳机器人。更换电机前先拆电池内托架，再移开本侧履带与联轴器连接，退端面螺钉后向下取电机。'),('关键接口','用户确认电机输出端外径Ø11.9；固定面槽宽13、顶部圆弧Ø13，总名义间隙1.1，未扣打印误差。'),('未完成','真实轴端、D形孔、顶丝、防松、编码器尾线、工具手柄和承载仍须实物核对。')],
'B': [('结构与安装','PP04为底盘及湿舱隔板一体件。底盖、折面顶盖、电源内托架、两侧肩梁分别维护；未定连接工艺不据图补造紧固件。'),('电源开关','顶盖中央设一体座、本体开孔和前后护边；两颗候选自攻螺丝从上方装卸。中心X0/Y-64、法兰面Z81.1，见第22页。'),('BOOT按钮','右肩内侧中心X-36/Y-22、法兰面Z114。肩梁一体座、后插防转螺母和走线鞍座；型号与端子待定，见第23页。'),('停止边界','BOOT仅为GPIO0软件停止。总电源开关、执行器供能切断及其真实电流承载分别验证；本图不代替电气原理图。')],
'C': [('当前电池','辰克5 V电池包，用户尺寸116×70.5×19.5。世界范围X-58…58、Y-94.75…-24.25、Z33…52.5；端口朝向及软线未确认。'),('装配','先铺四处承托垫，安放电池及拉带，托架用4套候选紧固件固定；最后装6点紧固的一体底盖。'),('维护','断电并垫高。先拆底盖，电池仍在托架上；需要取电池时先断线、托住电池，再退托架4颗螺钉，整组向下取60。'),('证据边界','旧120×73×31.5充电宝尺寸、质量与台架证据不沿用。真实端口、拉带保持、线弯、供电能力和承载均未验收。')],
'D': [('设备包络','L298N：46.2×43.5×27.5，长边沿+Z。MT3608：37×18×6，位于X25…43、Y-17…20、Z82…88；均不虚构未测孔位。'),('L298N装配','机外先装垫、侧压件和候选螺母，核对板边无元件区后装板。整框自底部装入，两颗候选M2.5锁紧件连接顶盖吊柱。'),('维护','先开底盖、断线并托住托框，再退锁紧件、整组下取80。MT3608裸板原维护方案要求先拆L298N及左电机，再向下取90。'),('未完成','MT3608固定件与端子未设计；L298N真实板边、焊脚、插头、夹紧量、通风与温升待验，不沿用旧电池间隙值。')],
'E': [('固定颈架','PP06由19个源特征合并；横梁、侧板和斜撑组成固定支承，不是可动关节。头壳与底盘的连接界面另行核对。'),('走线','主线束沿底盘中央干区、颈架及头舱后槽进入浅托盘。Ø6为规划通道，限位桥与护口保持独立。'),('维护','取头部浅托盘前先解除对外线束并收置；避免线束夹在冠盖与托盘边缘。BOOT双线在中央段共享既有线束预算。'),('未完成','套孔薄桥、层向、冲击强度、真实束径与弯曲余量未验收；图中的几何通道不代表线束已完成布置。')],
'F': [('头部下壳','头壳作为超声波面罩、浅托盘及冠盖的定位基体；保持既有外形比例。面罩、耳部和部分侧甲仍为独立对象。'),('安装','按当前CAD坐标核对壳体和饰件；尚未确定的胶粘或分体紧固工艺保持待定，不根据造型孔推定螺钉规格。'),('维护','检修电子整组优先从冠盖上方操作；避免直接强拆头壳饰件。声学开口、屏幕窗口、USB及天线按真实面包板位置复核。'),('未完成','耳部格栅不证明扬声器定位或出声通过；头壳连接、材料、跌落和结构承载仍需实物验收。')],
'G': [('一体冠盖','PP05合并冠盖及饰件共22个源特征。图卡中的眉甲、顶甲等为源特征，不再作为独立打印或装配件。'),('安装','四处冠盖候选紧固点中心X±64、Y-52/7；合盖前确认线束未夹在壳缝和饰件内侧。'),('维护','卸下4颗冠盖螺钉后整件上提65；顶甲和效果造型随盖移动。壳缝Z206…206.25为0.25设计间隙。'),('未完成','连接薄筋、层向、螺纹／嵌件配合及真实上取操作待试配；顶部效果造型不构成防水或绝缘设计。')],
'H': [('面包板包络','整组100×85×36为用户规划，含底板、元件、扬声器／麦克风／屏幕及线束。世界范围X±50、Y-70…15、Z174…210。'),('浅托盘','主体105×90，内区101×86，底厚2.5；四孔中心X±57、Y-40/-5。前缘49×2让位，后槽供线束进入。'),('维护','先取冠盖，断开并收置超声波和外部线管，退4颗托盘螺钉后整盘上提85。整板内部接线保持，不按图虚构设备重排。'),('未完成','整组总高和可接触塑料边缘未实测；压片、防脱、真实USB／天线与完整线束操作仍待核对。')],
'I': [('模块尺寸','双探头Ø16×10.3为用户输入；中心距26为推导，面板孔Ø16.6为候选。两探头属于同一模块，端面分色不是新增采购件。'),('安装','PCB45×20×1.6、背面深4、向上接头12×6×8及Ø4线束为布局预算；真实接口和固定件未冻结。'),('维护','先收置接头线束并取出浅托盘，再解除待设计固定件；原候选路径为向后退11使探头脱孔，再上提70。'),('未完成','上述路径是既有候选维护方案；真实接头方向、板端、工具手部及制造公差待试配。')],
'J': [('胶粘底托','PP01由底托及两处托管槽合并。枪位保持15°上仰，底托两颗基座螺钉连接对应肩梁；枪体与1 mm候选软胶独立。'),('管与线','喷水软管Ø5为用户实测；前后两处Ø5.6托槽引导管路向后。尾线导向鞍与扎带槽已并入底托，不另钻枪体。'),('维护','断电排液、断管断线并完全解除粘接。原候选方案为沿局部+Z抬2，再沿枪轴前抽150；空底托另拆两颗基座螺钉。'),('未完成','胶材、厚度、保持力、实际允许倾角、滴液倒流及脱胶操作均待验证；CAD路径不等于实物装配通过。')],
'K': [('当前底座','PP02：Ø32偏心孔、局部孔心上移1.3，孔底原抬高2.3；20宽支脚，孔底中央7.5×2.3贯穿缺口。'),('删除范围','删除近侧前长槽壁1与前横挡块6。对侧长槽壁2、后段槽壁3/4及后止挡5保留；软垫与枪体独立。'),('装配冲突','缺口两侧与原示意枪壳仍相交约65.113 mm³。现有位置不应强行装入；先处理真实轮廓或安装偏置，再验证孔形。'),('维护边界','旧抬尾15°、后退10、上抬3、外移90仅为原方案，不作为当前可执行步骤。穿环、入槽、脱胶和取枪必须重新验证。')],
'L': [('双瓶与背包','两瓶均Ø48.8×114（含盖）、150 mL；容量来自用户输入，不以几何圆柱体积推算。PP03护壳、桶座、下后护甲和脊条一体。'),('安装','每个独立开窗底托用2套候选M3固定；铺底垫和侧垫后放瓶，闭合12×1候选绑带。无打印上盖，瓶肩和瓶盖形状未建模。'),('补液维护','先断电，抽出并收置目标吸管，释放目标绑带；整瓶向上取150，在机外开盖。另一瓶及其软管可保留。'),('未完成','真实最大瓶径、保形、绑带保持、软管防折、通气密封、吸程及倾斜漏液均需实物验证。')],
'N': [('一体桶座','两侧Ø25.5×70模块规划本体置于PP03一体桶座和完整环带。已取消分体夹环、夹环螺钉及顶部倒L压件；上取90，防脱保持待验。'),('效果承板','四板承板连接顶盖内柱；先拆底盖和电池、断开引线，再退4颗承板螺钉，整组下取100。机外退每个压框2颗螺钉后取板。'),('第三块P01','点火低压MOS位于前舱独立托架，两点吊装；先拆底盖和电池，断线并退2颗吊装螺钉后整组下取80。'),('证据边界','PCB厚度、无元件边、端子与固定强度仍为候选；本图仅描述机械装拆，不提供高压接线或通电试验步骤。')],
'M': [('空间分类','本组表示工具、接线、避让和维护区域，不是采购或打印零件；部分路线用扫掠体表示，不能当作真实线缆。'),('当前可见路线','示意包含BOOT双线走廊及点火模块的预留路线。后者只记录路径空间，不是导线、电极或绝缘护罩。'),('维护','断开相关接口并收置柔性线路后再移动模块；整手、完整工具、线尾与端子尚未全部建模。'),('未完成','弯曲半径、护套、夹持、末端连接、线束填充和电气隔离需按实物补齐；不得把几何余量当作安全距离。')]
}
if cable:
    NOTES['E'][1]=('走线','主线束从底盘中央净径10通道上行，在托盘下方向左转，再由面包板左侧上行；15芯预算已包含BOOT双线，上护口随弯道成形。')
    NOTES['H'][1]=('浅托盘','主体105×90，内区101×86，底厚2.5；四孔中心X±57、Y-40/-5。前缘49×2让位；新增侧缘让位，主线束不再沿原后槽上行。')
    NOTES['M'][1]=('当前可见路线','中央Ø10总空间预算包含15根导线，BOOT双线计入其中。点火预留路线单独显示；高压输出线不属于中央通道，图中空间不是实体线缆。')
if tail:
    NOTES['K'][1]=('尾壳与薄片','尾壳高35.9不含底部薄片6.8；承托至尾顶42.7为推导。枪口、薄片、底座与15°姿态保持。尾壳距槽壁0.30；实际宽度及BOOT指端空间仍须核对。')
for group,(name,_,sequence) in SYSTEMS.items():
    header(group+' · '+name,sequence)
    fitted('system_'+group+'_iso',112,161,177,145)
    text(112,72,'当前系统轴测 · 按最终装配位置显示',9,MUTED,align='center')
    # Include plan geometry as a smaller second view for location, not duplicate material.
    fitted('system_'+group+'_top',112,45,150,34)
    y=232
    for heading,body in NOTES[group]:y=block(225,y,heading,body,175)
    assert y>=25,('system note overflow',group,y)
    end()

header('顶盖电源开关 · 安装与上取','当前0.53开关座保留在折面顶盖中央；图中尺寸为用户输入与安装候选，不是触点额定验收。')
fitted('part_KeelLid',112,157,174,151)
fitted('part_PowerSwitchBody',310,187,140,62)
y=133
p=report['power_switch_layout']
y=block(225,y,'安装基准',f"中心X0/Y-64；法兰接触面Z{p['flange_contact_plane_z_mm']}。\n本体开孔11.2×6.4；螺钉孔距14.8。\n两颗Ø2×6塑料自攻螺钉为候选，挂耳厚0.5为假设。",175)
block(225,y,'维护与验证','先断电并断开引线；从上方退两颗螺钉，再向上取出开关，底盖和电池可保持。护边、手感、真实接头及电流承载仍待验证。',175)
text(112,49,'顶盖：中央开关座与内部支柱一体',9,MUTED,align='center')
end()

header('右肩BOOT按钮 · 后插螺母与线束','当前0.54候选：GPIO0软件停止；按钮型号未选定，不能替代独立切断执行器供能。')
fitted('part_ShoulderRailR',112,169,177,128)
fitted('part_StopSignalRoute',112,65,156,62)
fitted('part_StopBody',310,204,82,50)
fitted('part_StopNut',371,204,42,40)
y=165
y=block(225,y,'座与接口','中心X-36/Y-22，法兰面Z114；孔Ø7.3。\n候选板厚2，螺母对边10×厚2，后腔宽10.4；\n按帽行程预算1.5，护边顶Z119.5。',175)
y=block(225,y,'候选拆卸','先断线，从上方旋出按钮，上提12再向前取出30。\n螺母从后腔取出。按钮未选型，螺纹与焊脚\n几何尚未闭合，实际手部操作待验证。',175)
block(225,y,'走线','双线走廊Ø2.8沿颈架后缘与中央通道进入头舱\n后槽；板内GPIO0/GND末段尚未几何完成。\n通电停止行为与独立断电另行验证。',175)
end()

header('证据、维护顺序与未完成项','图册生成只读取CAD与检查记录，不修改模型，也不把历史专项通过改写为当前整机验收。')
y=233
for heading,body in [
('本次几何来源',f"交付模型：CyberTrack.FCStd；设计源档：{meta['source_document']}。\n全部视图、对象图卡、尺寸包络均从此源档读取；没有混用旧版本PNG。"),
('本次已核对',f"{len(expected_names)}个对象图卡完整覆盖；6件合并打印候选及56个源特征关系明确。\nPP02保存回读有效、单实体、STL闭合且无非流形边；独立STEP几何差检查通过。"),
('本次未通过','PP02与BubbleGunShell仍相交，装拆路径未重新通过；图册各页均保留此状态。\n其他系统页描述当前机构和既有候选维护顺序，不表示本次重新执行了全机维护检查。'),
('建议维护次序','断开电源并排液、稳定承托；先开维护盖，再断开并收置相关线管，托住目标组件后解除紧固。\n机外核对设备和板卡后按逆序装回；PP02须先解决配合冲突，不能据图强行装配。'),
('还需实物验证','真实设备尺寸、线尾、工具／手部、连续维护路径、紧固与胶粘保持、材料层向、打印公差、\n承载、温升、供电、密封和液体共存均不能由CAD或PDF检查代替。')]:
    y=block(21,y,heading,body,376)
assert y>=42
text(21,38,'源档 SHA-256：'+meta['source_sha256'],8,MUTED)
text(21,29,'交付 SHA-256：'+sha(delivery),8,MUTED)
end()
assert page==FRONT_PAGES
catalog_result=render_catalog(globals(),CATALOG,CATALOG_SHEETS)
assert page==TOTAL_PAGES
c.save()
audit=dict(revision=REVISION,date='2026-10-26',source_document=meta['source_document'],
    source_sha256=meta['source_sha256'],delivery_sha256=sha(delivery),pdf_sha256=sha(PDF),
    page_count=page,front_matter_pages=FRONT_PAGES,catalog_index_page=FRONT_PAGES+1,
    card_count=sum(len(s['cards']) for s in CATALOG_SHEETS),object_count=len(CATALOG),
    annotated_object_count=len(catalog_result['entries']),
    nonphysical_space_count=sum(o['category']=='clearance' for o in CATALOG.values()),
    merged_print_parts=6,merged_source_features=sum(bool(o.get('merged_into')) for o in CATALOG.values()),
    missing_objects=sorted(expected_names-set(CATALOG)),projection_count=len(projection_keys),
    all_projections_current=True,historical_raster_previews_used=False,
    color_view_count=len(projection_keys),colors_from="native CAD face materials",
    color_manifest_sha256=sha(DATA/"colors/manifest.json"),
    cable_passage_audit_sha256=sha(MODEL/report['cable_passage_audit']) if cable else None,
    bubble_tail_height_audit_sha256=sha(MODEL/report['bubble_tail_height_audit']) if tail else None,
    geometry_modified_by_pdf_generator=False,assembly_fit_passed=cad_checks_passed,
    pp02_adjustment_audit_sha256=sha(MODEL/'pp02-adjustment-audit.json'),
    physical_fit_verified=False,manufacturing_released=False,**catalog_result)
(MODEL/'assembly-annotation-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
assert sha(source)==meta['source_sha256'] and sha(delivery)==delivery_hash
print(PDF);print('Pages:',page,'Cards:',audit['card_count'],'Objects:',len(CATALOG))
