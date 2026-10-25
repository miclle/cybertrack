"""Assembly identification and documented mating relationships, not a manufacturing BOM.

Every current CAD object must be assigned once. Mirrored/repeated objects share a
card, but retain their individual IDs, geometry, CAD names and world coordinates.
"""
import re
from collections import OrderedDict

SYSTEMS = OrderedDict([
 ('A', ('履带与传动', '动力固定 / 接口 / 维护', '先核对成品履带接口，再装电机、联轴器及履带；电机维护先移去本侧履带与电源。')),
 ('B', ('底盘、外甲与停止操作区', '外形尺寸 / 动力固定', '底盘电机固定面为一体；外甲分件固定工艺未定。停止按钮仅占位，不表示已接入切断电路。')),
 ('C', ('充电宝与底部检修', '电源承托架 / 动力维护', '先铺垫、安放电源和拉带，再装内托架4点紧固；最后合底盖6点。拆底盖不要求先取电源。')),
 ('D', ('L298N 托框与 MT3608 升压板', '驱动板布局 / 固定与拆装', '机外装垫、螺母和侧压件，核实安全接触边后装板；托框从底部装入，两颗螺钉固定。')),
 ('E', ('固定颈架与线束导向', '总装爆炸 / 内部路线', '固定颈架承托头舱；层板、套筒、横梁并非已验证活动关节。结构连接工艺仍需细化。')),
 ('F', ('头部下壳、面罩与侧甲', '头舱冠盖 / 总装爆炸', '以头壳为位置基准；面罩、耳部和后脑饰件的分体固定工艺未定；侧格栅不代表扬声器已定位。')),
 ('G', ('冠盖及随盖饰件', '头舱冠盖 / 整板上取', '冠盖组件由4颗候选螺钉固定在头壳上；拆时上提65。图卡内饰件随盖移动，工艺未定。')),
 ('H', ('面包板整组与浅托盘', '面包板布局 / 浅托盘 / 整板上取', '保留面包板内部接线；托盘4点固定在头壳支柱。装回前收置超声波线束，避免夹线。')),
 ('I', ('超声波与前脸接口', '双探头 / 超声波共存', '探头与PCB作为整模块处理；拆时先断线，后退11、上提70。PCB固定和接头仍是候选。')),
 ('J', ('水枪与胶粘底托', '水枪尺寸 / 水枪固定 / 线管', '先装空底托两颗基座螺钉，再铺胶垫、装枪、放管和接线；拆枪先断管断线并解除粘接。')),
 ('K', ('泡泡枪与整体圆环底座', '前置双枪 / 泡泡枪拆装', '先固定空底座，再按拆卸路径逆序穿环、入槽并胶辅固定；前环无分缝，不增加环上螺钉。')),
 ('L', ('双瓶背包、绑带与顶部吸管', '双瓶背包 / 顶部供液', '先固定两底托和软垫，再放入成品瓶、合绑带、顶部插管；拆瓶先移开目标吸管并松绑带。')),
 ('N', ('背包本体夹持与效果板承板', '背包夹环 / 薄承板固定', '本体解除外半夹环后上取；承板先拆充电宝再从下方解除四点紧固。板边压框及局部接线空间为候选，真实接口与公差仍待实测。')),
 ('M', ('工具、接线与维护空间', '对应系统维护详图', '本组均为自由空间，不是实物零件，不计入采购或打印；装配时保持通道畅通。')),
])


def system(name, obj):
    if obj['category'] == 'clearance': return 'M'
    if name.startswith(('BackpackArc','ArcClamp','ArcLiner','ArcBottomPad','ArcInsert','ArcScrew','Effect','FrontEffect')): return 'N'
    if name.startswith(('Track','Motor','DriveCoupler')): return 'A'
    if name.startswith(('Battery','BottomCover','BottomService','PowerBank')): return 'C'
    if name.startswith(('L298N','MT3608')): return 'D'
    if name.startswith('Breadboard') or name == 'ElectronicsTray': return 'H'
    if name.startswith('Ultrasonic'): return 'I'
    if name.startswith('WaterGun'): return 'J'
    if name.startswith('BubbleGun') and name != 'BubbleGunHoseRoute': return 'K'
    if name.startswith(('Water','Bubble','Backpack','RearBaseArmor')): return 'L'
    if name.startswith(('Neck','PowerCable','BaseCable','HeadCable')): return 'E'
    if name.startswith(('Crown','BrowArmor','OccipitalBrow','HeadCrown','HeadService')): return 'G'
    if name.startswith(('HeadShell','Visor','Cheek','Jaw','Audio','Ear','Temple','Occipital','Sensor')): return 'F'
    if name.startswith(('LowerTub','RearBulkhead','WetDivider','Keel','Shoulder','Chest','LowerChin','Stop')): return 'B'
    raise ValueError('Unassigned CAD object: '+name)


def family(name):
    # Only collapse mirrored/numbered occurrences of the same named feature.
    name = re.sub(r'^Track(?:Left|Right)', 'TrackPair', name)
    name = re.sub(r'BatteryPad.*', 'BatteryPad', name)
    name = re.sub(r'(?:L|R)?(?:Front|Rear)$', '', name)
    name = re.sub(r'[LR]?\d+$', '', name)
    return re.sub(r'[LR]$', '', name)


def relation(name, obj, group):
    """Return assembly target and scope-limited installation note from current design."""
    if group == 'M':
        return '所示机构的检修 / 接线区域', '仅用于避让审查，不安装。形状与坐标表示预留范围；工具、手指、软线仍须实物核对。'
    if group=='N':
        if name.startswith('FrontEffect'):return '底盘左右前护甲外侧','0.45每侧两根封闭端外观线与根部护套；纯造型假设，无穿壳孔、内部高压路径、电极或固定工艺，不用于接线或制造。'
        if name.startswith('BackpackArc'):return '背包外侧两道夹环及底托','Ø25.5×70规划本体；先拆本侧4螺钉及两外半夹环，再上取90。非实测，无高压引线或通电集成。'
        if name.startswith('ArcClamp'):return '背包一体内半夹环','每半环两颗外侧M2.5级候选螺钉；上环带顶部限位，拆螺钉后外移35。间隙、材料、强度和手部操作待验。'
        if name.startswith(('ArcLiner','ArcBottomPad')):return '夹环与本体接触界面','夹环软衬0.5、底垫1 mm候选；未建压缩，实际灌封壳接触区、材料、夹持力及温升待核。'
        if name.startswith('ArcInsert'):return '一体内半夹环的盲孔','共8个M2.5级候选嵌件；与外侧螺钉配套，不作为已验证螺纹啮合或工艺参数。'
        if name.startswith('ArcScrew'):return '外半夹环 → 内半夹环嵌件','共8颗M2.5级候选，从外侧操作；取出路径35，工具杆只覆盖Ø3直杆。'
        if name.startswith(('EffectMOS','EffectBuck')):return '承板浅凹座与开窗压框','MOS33×17×12／降压20×11×5；PCB厚1.6、四边无元件区2.5假设。机外拆框后上取20，实际板边必须核对。'
        if name.startswith('EffectSupport'):return 'PCB两条板边下方','0.5 mm垫放在1 mm深座内；板底中央0.5余量，焊脚、接触区、压缩及材料待实测。'
        if name.startswith('EffectRetainerInsert'):return '承板压框支柱','8个M2级短嵌件候选；实物规格、嵌件强度及热熔工艺未定。'
        if name.startswith('EffectRetainerScrew'):return '开窗压框 → 承板支柱','每框2颗M2级候选螺钉，全机新增8颗；先整盘取出，机外上退20。'
        if name.startswith('EffectRetainer'):return 'PCB无元件边缘上方','4个独立开窗框；仅覆盖假设空白板边，顶间隙0.4。机外拆本框2螺钉后上取20，再提板。'
        if name=='EffectTray':return '顶盖内侧四根一体支柱','低位凹座与四耳沉台，孔X±47、Y−49/−26.5；先拆充电宝及底盖，再退出4螺钉，向下取100。'
        if name.startswith('EffectInsert'):return '顶盖内柱向下开口盲孔','4个M2.5级候选嵌件；顶盖外表面不穿孔，配合、制造和强度待验。'
        if name.startswith('EffectScrew'):return '承板四耳 → 顶盖内柱','4颗M2.5级候选，先拆充电宝再从下操作；头部凹入耳内，距电源2.1 mm；盘底2 mm，公差仍须复核。'
    if name=='BackpackShell':return '双瓶护壳及外侧一体内半夹环','0.42新增两侧夹环支撑、底托和连接肋；原液瓶舱几何保持。夹持、材料、液体共存与制造未验收。'
    if name=='KeelLid':return '底盘折面顶盖及内侧一体支柱','原前斜坡外表面保持；0.43调整薄承板4根内柱，底部螺钉固定，不穿透外表面。'
    if name.startswith('TrackPair'): raise ValueError(name)
    if name.startswith(('TrackLeft','TrackRight')):
        return '对应侧成品履带总成', '成品内部几何参考；胎块、轮组及紧固件不按此图逐件制造。内部拆装与真实数量以实物为准。'
    if name.startswith('TrackMountScrew'):
        return '履带安装件 → 底盘侧面', '每侧2颗M3级候选；先对齐安装件孔位，再固定。长度、螺纹啮合及防松待定。'
    if name.startswith('TrackMount'):
        return '对应侧履带 → 底盘', '按来源安装件对齐底盘两点；与联轴器同轴关系、孔距和实物配合待核。'
    if name.startswith('MotorFaceScrew'):
        return '电机端面 → 底盘一体固定面', '每侧4颗M3级候选；保持原孔轴。端面螺纹深度、螺钉长度及扭矩待核。'
    if name.startswith('MotorShaft'):
        return '电机输出端 → 六角联轴器', '电机附属轴几何，不是额外独立安装轴；Ø6偏心D形接口与锁紧方式待实物核对。'
    if name.startswith('Motor'):
        return '底盘一体电机固定面', '端面4颗候选螺钉固定；拆时先移电源和本侧履带，再退端面螺钉、向下取电机。'
    if name.startswith('DriveCoupler'):
        return '电机D轴 ↔ 履带驱动端', '黄铜六角联轴器参考；装配长度、孔形和锁紧未实测，不据图指定顶丝。'
    if name == 'LowerTub':
        return '整机底部承载基体', '电机固定面与底盘一体，无独立端板；先核实孔位和电源、驱动板维护空间。'
    if name.startswith('Stop'):
        return '后肩本地停止操作区', '按钮及基台为位置占位；选型、固定和切断电路未设计，不能视为已可用的停止机构。'
    if name == 'PowerBank':
        return '电源内托架上的四处承托垫', '120×73×31.5实测外形；端口面朝+Y。先核对插头，内托架向下取出60。'
    if name == 'BatteryHatch':
        return '底盘四处电源固定点', '配4垫圈、4颗M2.5级候选螺钉及嵌件；先托住电源，再紧固；底盖可独立拆卸。'
    if name.startswith('BatteryPad'):
        return '电源内托架 → 充电宝底面', '四处承托垫；先铺垫再放电源。材料、压缩量与胶粘方式待核。'
    if name.startswith('BatterySupportWasher'):
        return '电源内托架固定耳承压面', '与对应电源螺钉配套定位；承压、材质和实际垫圈标准待核。'
    if name.startswith('BatteryInsert'):
        return '底盘电源固定柱', '4处M2.5级配套嵌件候选；安装工艺和孔配合待定，不指定压装或热熔参数。'
    if name.startswith('BatteryScrew'):
        return '内托架固定耳 → 底盘嵌件', '从下方紧固，4颗M2.5级候选；须先托住电源；沉孔与头型未采购定型。'
    if name == 'BatteryPullStrap':
        return '电源及内部承托架', '柔性拉带占位，随内托架下取；固定端、材料和承载待实物确认。'
    if name == 'BottomServiceCover' or name.startswith('BottomCoverScrew'):
        return '底盘底部检修口', '一体底盖用6颗M2.5级候选螺钉；拆下可检修驱动板，电源内托架保持。'
    if name=='MT3608Envelope':
        return 'L298N左上方干舱／固定待设计','37×18×6用户实测包络；先拆L298N托框及左电机后裸板下取90；接头、固定及散热待验。'
    if name.startswith('L298N'):
        target = 'L298N开口托框'
        note = '在机外装配侧压组件；板边安全接触位置、材料及压紧量须核实，不使用未测PCB孔。'
        if 'MountInsert' in name: target,note='顶盖一体吊柱盲孔','2处M2.5级候选嵌件；盲孔不贯穿顶盖，配合及安装工艺待定。'
        elif 'MountScrew' in name: target,note='托框 → 顶盖两根吊柱','2颗M2.5级候选；从底部紧固，拆时托住托框、断线，再退出螺钉。'
        elif 'ClampNut' in name: note='四处M2级候选螺母从托框槽口放入；配侧压螺钉，真实防转及防松待验。'
        elif 'ClampScrew' in name: note='四处M2级候选侧压螺钉配绝缘垫；在机外调整，不让金属件压焊脚或元件。'
        elif 'SidePad' in name: note='四处0.5厚候选绝缘侧压垫，位于侧压螺钉与板边之间；接触位置待测。'
        elif 'RearPad' in name: note='四角后挡软垫；背面中央避空，不代表已避开实际焊脚。'
        elif 'BottomPad' in name: note='两处0.8厚候选垫承托PCB下沿；安装前核实下沿安全接触区。'
        elif name=='L298NCarrier': target,note='顶盖吊柱下端','先在机外装板与侧压件，再将整框上装；2颗底部锁紧螺钉固定。'
        elif name=='L298NEnvelope': note='46.2×43.5×27.5用户外形包络；竖装、下沿承托、四点侧压，真实器件位置未建模。'
        return target,note
    if name in ('PowerCableRoute','BaseCableGrommet','HeadCableGrommet','NeckCableBridge'):
        return '底盘中央干区 → 颈架 → 头舱后槽', '线束经护口和限位桥进入托盘后缘；Ø6为规划。拆托盘先断开对外线束，真实弯曲待验。'
    if group=='E': return '固定颈架 / 头舱承托结构', '按图中世界坐标定位；固定结构，不提供关节运动。杆套与层板的连接及装配工艺尚未细化。'
    if name.startswith('CrownInsert'): return '头壳四处冠盖支座','配冠盖4颗M2.5级候选螺钉；嵌件孔配合及安装工艺待实物确认。'
    if name.startswith('CrownScrew'): return '冠盖 → 头壳四处支座','4颗M2.5级候选；先对齐冠盖，确认无夹线再紧固；拆卸后冠盖上提65。'
    if name=='HeadCrownShell': return '头壳四处冠盖支座','4颗M2.5级候选螺钉固定；0.25装配分缝为设计值，合盖前检查夹线，拆盖整体上提65。'
    if group=='G': return '整体冠盖组件','随整体冠盖上提65；分对象用于造型识别，饰件独立固定或合并成形工艺未定。效果件不含高压器件。'
    if name == 'HeadShell': return '固定颈架的头舱承托鞍座','内部托盘支柱与头壳一体；承托面Z171.5。头壳与颈架连接工艺尚未细化。'
    if group=='F': return '头壳 / 前脸 / 对应侧外甲','按模型位置识别；分件固定、胶粘或合并成形方式未定。耳部饰件不能证明扬声器出声通道。'
    if name == 'ElectronicsTray': return '头壳内部四支柱承台','4颗M2.5级侧耳螺钉；前缘49×2让位朝超声波，后槽走线；拆冠盖、断线后上提85。'
    if name.startswith('BreadboardInsert'): return '头壳四支柱','M2.5级嵌件候选，配托盘侧耳螺钉；嵌件规格、安装工艺及柱根强度待验。'
    if name.startswith('BreadboardScrew'): return '托盘侧耳 → 头壳四支柱','孔位X±57、Y−40/−5；4颗M2.5级候选，上方直杆操作。长度及扭矩待核。'
    if name=='BreadboardEnvelope': return '浅托盘101×86内区','整组100×85×36规划，包含扬声器/麦克风/屏幕/ESP32及线束；内部位置、总高和防脱未实测。'
    if name.startswith('UltrasonicFace'): return '超声波探头端面','仅为探头端面的分色几何，不是额外采购的端盖；与对应圆柱一起随模块拆装。'
    if name.startswith('UltrasonicRing'): return '前脸双Ø16.6孔 → 模块PCB','Ø16×10.3用户尺寸；中心距26为推导。双探头属于同一模块，固定方式未设计。'
    if name=='UltrasonicWireSpace': return '模块顶部接头 → 面包板侧边交接区','Ø4线束路线为候选，板端接口未定；取托盘或超声波前先断开并收置线束，折线不代表真实弯曲半径。'
    if group=='I': return '超声波整模块后部 / 顶部','PCB、背面器件及向上接头均为未实测包络；与探头共同拆装，不能按此图采购或钻固定孔。'
    if name.startswith(('WaterGunBase','BubbleGunBase')):
        gun='水枪' if name.startswith('Water') else '泡泡枪'
        return gun+'空底托 → 对应侧肩梁','每侧2套M3级嵌件及基座螺钉候选；先固定空底托再装枪，孔轴随15°安装面。'
    if name.startswith(('WaterGunLead','BubbleGunLead')):
        return '对应枪尾端 → 干区线束','线束Ø3、插头16×10×10为候选；先解除固定再拔插。端子、固定与应力释放待定。'
    if name.startswith('WaterGunHoseSupport'):
        return '水枪底托外侧前 / 后挡板','两处上开口Ø5.6托槽承托Ø5实测软管；制造合并须纳入底托，不作为独立紧固件或防拉夹。'
    if name.startswith('WaterGunLowerPad'):
        return '水枪底面 ↔ 一体底托','两处1 mm双面软胶候选；不钻原枪体。胶厚、材质和保持力待验；拆枪前完全解除粘接。'
    if name=='WaterGunCradle': return '水枪侧肩梁15°承托面','两颗基座螺钉固定；尾线导向鞍已一体，前后托管槽制造时合并；枪体靠底部软胶。'
    if name in ('WaterGunBody','WaterGunInlet','WaterGunMaximumEnvelope'):
        return '水枪胶粘底托 / 侧接软管','成品枪体与未测接头示意；最大包络含管宽38.5。拆时脱胶、局部+Z抬2、−Y前抽150。'
    if name in ('BubbleGunShell','BubbleGunWheel','BubbleGunMotor','BubbleGunGearcase','BubbleGunMountingTab','BubbleGunFrontFoot','BubbleGunInspectionEnvelope'):
        return '泡泡枪成品模块 → 圆环 / 阶梯槽','成品内部示意或外形包络，非新增采购件；整枪穿整体环入槽、胶辅助固定，槽面与最大宽待核。'
    if name.startswith(('BubbleGunRing','BubbleGunSlotWall')) or name=='BubbleGunCradle':
        return '泡泡枪同一底座组件','整体圆环和两段槽随底座拆装；前环无分缝无螺钉。分对象表达特征，制造合并范围须核对。'
    if name=='BubbleGunLowerPadRear': return '泡泡枪阶梯槽底','0.6厚候选垫承托薄片底面；胶辅助固定，材料与粘接方式待验。'
    if name in ('WaterHoseRoute','BubbleGunHoseRoute'):
        return '对应瓶顶部 → 对应枪接头','清水管Ø5实测、泡泡管Ø4候选；从瓶顶插入，不穿后护甲或侧壁。接头、密封与管长待核。'
    if name.startswith(('WaterPod','BubblePod')):
        return '对应瓶底托 → 湿舱底部','每个开窗底托2套M3级候选嵌件/螺钉固定；先装空底托，再放软垫、瓶与绑带。'
    if name.endswith('Module'): return '对应开窗底托 / 绑带','成品瓶含盖Ø48.8×114、150 mL；不拆分打印瓶盖。顶部插管；松绑带后整瓶上取150。'
    if 'Pad' in name and group=='L': return '对应瓶底面 / 侧壁与底托之间','1 mm候选软垫；先铺垫再放瓶，压缩量和防滑保持力待验。'
    if 'RetentionBand' in name or 'StrapClosure' in name:
        return '对应瓶底托导槽 / 瓶体外侧','12×1候选可释放绑带与魔术贴搭接；后侧拉片释放，非刚性卡扣。张紧及防滑待验。'
    if group=='L': return '低位双瓶背包 / 对应护舱','护壳、后护甲及识别饰条按模型位置装配；连接、分体或一体制造方式尚未细化。'
    if group=='B': return '底盘 / 顶盖 / 对应侧结构','按模型定位；肩梁承托双枪，湿舱隔板分隔空间。分体连接、密封与制造工艺未定。'
    raise ValueError('Missing assembly relationship: '+name)


def build_catalog(objects):
    groups = {k: OrderedDict() for k in SYSTEMS}
    entries = {}
    for index, (name, obj) in enumerate(sorted(objects.items()), 1):
        group=system(name,obj)
        target,note=relation(name,obj,group)
        entries[name]={'id':f'CT{index:03d}', 'name':name, **obj,
                       'system':group,'target':target,'assembly_note':note}
        # Different instructions or targets must never be combined merely by name.
        key=(family(name),target,note,obj['category'])
        groups[group].setdefault(key,[]).append(entries[name])
    all_cards=[]
    for group, families in groups.items():
        cards=[members[i:i+4] for members in families.values() for i in range(0,len(members),4)]
        all_cards.extend(cards)
    sheets=[{'cards':all_cards[i:i+6]} for i in range(0,len(all_cards),6)]
    # Avoid a nearly empty trailing sheet while keeping every card together.
    if len(sheets)>1 and len(sheets[-1]['cards'])<3:
        last=sheets[-2]['cards']+sheets[-1]['cards']
        sheets[-2]['cards'],sheets[-1]['cards']=last[:4],last[4:]
    assert sum(len(card) for sheet in sheets for card in sheet['cards'])==len(objects)
    return entries,sheets


def render_catalog(api, entries, sheets):
    """Append one navigation page and six-card A3 sheets using the drawing pack API."""
    text,para,box,line=(api[n] for n in ('text','para','box','line'))
    header,end,drawing=(api[n] for n in ('header','end','drawing'))
    ink,muted,accent,pale=(api[n] for n in ('INK','MUTED','ACCENT','PALE'))
    start=api['page']+2
    ranges={g:[start+i for i,s in enumerate(sheets) if any(card[0]['system']==g for card in s['cards'])] for g in SYSTEMS}
    header('全对象装配索引 · 按系统查零件','每个当前CAD对象均有唯一CT编号；对称件与重复紧固件合并图卡，保留各自外形与世界坐标。')
    text(20,238,'系统 / 装配位置',11,bold=True)
    text(154,238,'当前装配图',11,bold=True)
    text(285,238,'对象数',11,bold=True)
    text(333,238,'逐项图卡页',11,bold=True)
    # Page references are supplied by the retained front matter, not hard-coded
    # assumptions about how many appendix cards happen to exist.
    system_pages=api['SYSTEM_PAGE_REFS']
    for i,(g,(name,_,_)) in enumerate(SYSTEMS.items()):
        y=224-i*11.5
        if i%2==0: box(14,y-3.5,392,11.5,pale)
        text(20,y,f'{g}  {name}',10,bold=True)
        text(154,y,system_pages[g],9)
        text(291,y,str(sum(e['system']==g for e in entries.values())),10)
        text(339,y,f'{ranges[g][0]}-{ranges[g][-1]}',10)
        api['c'].linkRect('',f'page-{ranges[g][0]}',
                          (14*api['U'],(y-3.5)*api['U'],406*api['U'],(y+8)*api['U']),relative=0,thickness=0)
    para(20,64,'读图：图卡小图是保存模型的独立消隐轴测图，不是爆炸位移或实际比例。每项C为世界包围盒中心，S为世界包围盒尺寸X×Y×Z，均为mm；斜放件S不等于零件自身长宽高。',378,9,5)
    para(20,48,f"数量：{len(entries)}个CAD对象包含{sum(e['category']=='clearance' for e in entries.values())}个非实体空间；复合履带对象内有多实体，探头端面含分色对象。对象数和实体数均不直接作为采购数量。扬声器等面包板组内设备没有独立模型，仅由整组规划包络覆盖。",378,9,5)
    text(20,29,'蓝 / 橙色编号对应对象；固定方式未定处明确留项。几何覆盖完整不等于装配工艺、制造或实物验收完整。',9,muted)
    end()
    categories={'drive':'成品参考','structure':'结构候选','exterior':'外形候选','envelope':'包络 / 路线','component':'部件参考','clearance':'非实体空间'}
    for sheet in sheets:
        groups=list(dict.fromkeys(card[0]['system'] for card in sheet['cards']))
        if len(groups)==1:
            group=groups[0];name,refs,sequence=SYSTEMS[group]
            header(f'{group} · {name} · 逐项装配图卡',sequence)
        else:
            header('逐项装配图卡 · '+' / '.join(groups),
                   '；'.join(g+' '+SYSTEMS[g][0] for g in groups)+f'。按卡片系统字母与第{start-1}页索引查找总装图。')
        text(15,240,'对应装配图：'+'；'.join(g+' '+system_pages[g]+'页' for g in groups)+'。小图分别缩放，尺寸以数值为准。',9,muted)
        for slot,members in enumerate(sheet['cards']):
            x=14+(slot%2)*199;y=28+(2-slot//2)*69
            box(x,y,193,66)
            first=members[0]
            label=first['label'].replace('001','').replace('002','').replace('003','')
            if len(members)>1:
                label='同类件 · '+re.sub(r'\s+[LR]?\d*$','',re.sub(r'^(左侧|右侧|左|右)','',label))
            label=first['system']+' · '+label
            # Keep enough room for four identity + coordinate rows.
            yy=para(x+49,y+60,label,139,10,4.4)
            yy=para(x+49,yy-0.3,'位置：'+first['target'],139,8.6,4.1)
            yy=para(x+49,yy-0.3,first['assembly_note'],139,8.6,4.1)
            for item in members:
                b=item['bbox'];center=[(b[k]+b[k+3])/2 for k in range(3)];size=[b[k+3]-b[k] for k in range(3)]
                fmt=lambda v: '/'.join(f'{a:.1f}'.replace('-0.0','0.0') for a in v)
                text(x+49,yy-0.8,item['id']+'  '+item['name'],7.7,accent,bold=True)
                text(x+49,yy-4.5,'C '+fmt(center)+'   S '+fmt(size),7.3,muted)
                yy-=7.8
                item['page']=api['page']
            if yy < y+1:
                raise ValueError(f'Card text overflow: {first["name"]} ({yy-y:.1f} mm)')
            count=len(members)
            for j,item in enumerate(members):
                if count==1: cx,cy,w,h=x+24,y+34,41,43
                elif count==2: cx,cy,w,h=x+24,y+48-j*24,39,18
                else: cx,cy,w,h=x+13+(j%2)*22,y+49-(j//2)*25,19,18
                d=api['json'].loads((api['DATA']/('part_'+item['name']+'.json')).read_text())
                b=d['bounds'];scale=min(w/max(b[2]-b[0],.01),h/max(b[3]-b[1],.01))
                drawing('part_'+item['name'],cx,cy,scale)
                text(cx,cy-h/2-3,item['id'],7,accent,align='center')
            para(x+3,y+6,categories[first['category']]+f' · {count}对象 / '+str(sum(m['solids'] for m in members))+'实体',43,6.8,3.1)
        end()
    return {'system_page_ranges':ranges,'entries':entries}
