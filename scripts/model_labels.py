"""Normalize delivery labels; preserve geometry, GUI state and design-source bytes."""
import copy
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from model_tree import sha


def part_labels():
    labels = {}

    def add(name, section, part, position=''):
        assert name not in labels, name
        labels[name] = ' · '.join(v for v in (section, part, position) if v)

    def sides(prefix, section, part):
        for side, word in (('L', '左'), ('R', '右')):
            add(prefix + side, section, part, word)

    def numbered(prefix, section, part, count, start=0):
        for i in range(count):
            add(prefix + str(i + start), section, part, str(i + 1))

    def corners(prefix, section, part):
        for suffix, word in (('LFront', '左前'), ('LRear', '左后'), ('RFront', '右前'), ('RRear', '右后')):
            add(prefix + suffix, section, part, word)

    tracks = {'RubberBand':'连续橡胶履带', 'TreadPads':'胎块底座', 'ChevronTreads':'人字形抓地块',
              'ShoulderLugs':'肩部胎块', 'WheelTires':'橡胶轮组', 'WheelRims':'金属轮圈',
              'WheelFaces':'镂空轮盘', 'WheelHubs':'轮毂与垫圈', 'SuspensionArms':'悬挂支臂与轴套',
              'RockerPlates':'承重轮摇臂板', 'Fasteners':'轮组与悬挂紧固件'}
    for side, word in (('Left','左'), ('Right','右')):
        for suffix, part in tracks.items():add('Track'+side+suffix, '履带', part, word)
    for prefix, part in {'Motor':'37R-520 电机（占位）', 'MotorShaft':'D 形输出轴',
                         'DriveCoupler':'六角联轴器（配合待测）', 'TrackMount':'履带安装件（参考）'}.items():
        sides(prefix, '动力', part)
    singles = {
        'BatteryHatch':('电源','承托架'), 'KeelLid':('底盘','折面顶盖'),
        'HeadShell':('头舱','固定下壳'), 'VisorRim':('前脸','内框'),
        'JawArmor':('下颌','中央护甲'), 'JawAccent':('下颌','识别片'),
        'OccipitalFrame':('后脑','护框'), 'OccipitalInset':('后脑','衬板'),
        'OccipitalSpine':('后脑','中央脊甲'), 'OccipitalMark':('后脑','识别条'),
        'SensorMask':('前脸','传感器面板'), 'SensorStatusStrip':('前脸','状态色条'),
        'ChestAudioPanel':('前舱','内嵌饰板'), 'LowerChin':('前舱','下缘护片'),
        'ChestBadge':('前舱','识别片'), 'StopPlinth':('停止按钮','基座'),
        'StopControl':('停止按钮','本体（占位）'), 'PowerBank':('电源','辰克 5 V 电池包（占位）'),
        'BatteryPullStrap':('电源','拉带（占位）'), 'ElectronicsTray':('面包板','浅托盘'),
        'PowerCableRoute':('电源','低压线束（规划）'), 'BaseCableGrommet':('底盘','线束护口'),
        'HeadCableGrommet':('头舱','线束护口'), 'NeckCableBridge':('颈架','线束限位桥'),
        'WaterHoseRoute':('水枪','供液管（规划）'), 'WaterGunBody':('水枪','本体'),
        'WaterGunInlet':('水枪','进水接头（占位）'), 'WaterGunLeadRoute':('水枪','尾线束（规划）'),
        'WaterGunLeadConnector':('水枪','插头（占位）'), 'BubbleGunLowerPadRear':('泡泡枪','后槽软垫'),
        'BubbleGunHoseRoute':('泡泡枪','供液管（规划）'), 'BubbleGunLeadRoute':('泡泡枪','尾线束（规划）'),
        'BubbleGunLeadConnector':('泡泡枪','插头（占位）'), 'BottomServiceCover':('底盘','底部检修盖'),
        'L298NEnvelope':('L298N','驱动板（占位）'), 'L298NCarrier':('L298N','可拆托框'),
        'BreadboardEnvelope':('面包板','整组包络（占位）'),
        'UltrasonicPCBEnvelope':('超声波','PCB（占位）'), 'UltrasonicRearEnvelope':('超声波','背面元件（占位）'),
        'UltrasonicTopConnector':('超声波','顶部接头（占位）'), 'UltrasonicWireSpace':('超声波','线束（规划）'),
        'EffectTray':('效果板','承板'), 'MT3608Envelope':('MT3608','升压板（占位）'),
        'IgnitionMOSBoard':('点火 MOS','控制板（占位）'), 'IgnitionMOSSupport':('点火 MOS','板边垫'),
        'IgnitionMOSRetainer':('点火 MOS','压框'), 'IgnitionMOSCarrier':('点火 MOS','独立托架'),
    }
    for name, (section, part) in singles.items():add(name, section, part)
    for suffix, position in {'N54N90':'右前','N54N29':'右后','54N90':'左前','54N29':'左后'}.items():
        add('BatteryPad'+suffix, '电源','承托垫',position)
    paired = {
        'CheekArmor':('颊部','护甲'), 'AudioSideGuard':('耳舱','侧护罩'),
        'AudioEarRing':('耳舱','阶梯环'), 'AudioEarGrille':('耳舱','格栅'), 'EarHub':('耳舱','中心饰片'),
        'TempleGuard':('太阳穴','护板'), 'TempleCrest':('太阳穴','上护甲'),
        'TempleLowerBlade':('太阳穴','下护甲'), 'EarOuterArc':('耳舱','外护弧'),
        'UltrasonicRing':('超声波','探头主体'), 'UltrasonicFace':('超声波','探头端面'),
        'ShoulderRail':('肩部','承力梁'), 'KeelSideFrame':('底盘','镂空侧框'),
        'ChestGuard':('前舱','侧甲'), 'ChestAccent':('前舱','嵌条'),
        'L298NBottomPad':('L298N','底部承托垫'), 'L298NMountInsert':('L298N','托框嵌件'),
        'L298NMountScrew':('L298N','托框锁紧螺钉'), 'BackpackArc':('点火模块','本体（占位）'),
        'ArcBottomPad':('点火模块','底垫'), 'IgnitionMOSMountInsert':('点火 MOS','托架嵌件'),
        'IgnitionMOSMountScrew':('点火 MOS','托架固定螺钉'),
        'IgnitionRoute':('点火走线','双线走廊（审查区）'),
    }
    for prefix, (section, part) in paired.items():sides(prefix,section,part)
    for prefix, section, part in [('BatteryInsert','电源','承托架嵌件'),('BatteryScrew','电源','承托架固定螺钉'),
                                 ('CrownInsert','冠盖','嵌件'),('CrownScrew','冠盖','固定螺钉'),
                                 ('TrackMountScrew','履带','安装件固定螺钉'),('BatterySupportWasher','电源','承压垫圈')]:
        corners(prefix,section,part)
    for side, word in (('L','左'),('R','右')):
        for i in range(3):add('OccipitalLouver'+side+str(i),'后脑','格栅饰条',word+str(i+1))
        for i in range(4):add('MotorFaceScrew'+side+str(i),'动力','电机端面螺钉',word+str(i+1))
        for i in range(2):
            for prefix, part in {'ClampNut':'侧压螺母（占位）','ClampScrew':'侧压螺钉',
                                 'SidePad':'侧压垫','RearPad':'后挡软垫'}.items():
                add('L298N'+prefix+side+str(i),'L298N',part,word+str(i+1))
            for key, part in {'Inner':'内侧衬垫','Outer':'外侧衬垫'}.items():
                add('ArcLiner'+key+side+str(i),'点火模块',part,word+str(i+1))
            for prefix, section, part in [('FrontEffectSleeve','前舱效果线','根部护套（外观示意）'),
                                         ('FrontEffectLead','前舱效果线','线体（外观占位）'),
                                         ('IgnitionRouteBranch','点火走线','单线接近区（审查区）')]:
                add(prefix+side+str(i+1),section,part,word+str(i+1))
    for prefix, section in [('WaterGun','水枪'),('BubbleGun','泡泡枪')]:
        numbered(prefix+'BaseInsert',section,'底座嵌件',2,1)
        numbered(prefix+'BaseScrew',section,'底座固定螺钉',2,1)
    numbered('WaterGunLowerPad','水枪','底部软胶垫',2,1)
    for suffix, part in {'Shell':'枪壳','Wheel':'泡泡转轮','Motor':'电机','Gearcase':'齿轮箱',
                         'MountingTab':'安装片','FrontFoot':'前支脚'}.items():add('BubbleGun'+suffix,'泡泡枪',part)
    numbered('BottomCoverScrew','底盘','检修盖固定螺钉',6)
    for prefix,section in [('Water','清水瓶'),('Bubble','泡泡液瓶')]:
        for suffix,part in {'Module':'瓶体含盖（占位）','Pod':'底托','BottomPad':'底垫','RetentionBand':'绑带',
                            'StrapClosure':'绑带搭接片','LidMark':'识别条'}.items():add(prefix+suffix,section,part)
        sides(prefix+'PodInsert',section,'底托嵌件')
        sides(prefix+'PodScrew',section,'底托固定螺钉')
        numbered(prefix+'SidePad',section,'环形侧垫',2)
    for prefix, section in [('Breadboard','面包板'),('Effect','效果板')]:
        numbered(prefix+'Insert',section,'托板嵌件',4)
        numbered(prefix+'Screw',section,'托板固定螺钉',4)
    for side,word in [('L','左'),('R','右')]:
        for kind, section in [('MOS','效果 MOS 板'),('Buck','效果降压板')]:
            key=side+kind
            add('Effect'+kind+side,section,'本体（占位）',word)
            add('EffectSupport'+key,section,'板边垫',word)
            add('EffectRetainer'+key,section,'压框',word)
            for position, posword in [('Inner','内'),('Outer','外')]:
                add('EffectRetainerInsert'+key+position,section,'压框嵌件',word+posword)
                add('EffectRetainerScrew'+key+position,section,'压框螺钉',word+posword)
    for position,word in [('Inner','内侧'),('Outer','外侧')]:
        add('IgnitionMOSRetainerInsert'+position,'点火 MOS','压框嵌件',word)
        add('IgnitionMOSRetainerScrew'+position,'点火 MOS','压框螺钉',word)
    labels.update({'PrintWaterCradle':'PP01 水枪一体底托','PrintBubbleCradle':'PP02 泡泡枪一体圆环底座',
                   'PrintBackpack':'PP03 双瓶背包一体外壳及桶座','PrintLowerTub':'PP04 一体底盘及湿舱隔板',
                   'PrintCrown':'PP05 一体冠盖及装甲饰件','PrintNeck':'PP06 一体固定颈架'})
    assert len(labels)==301 and len(set(labels.values()))==301
    return labels


def normalize(out):
    """Edit only XML Label/Label2; verify native readback before replacing delivery."""
    import FreeCAD as App
    root=Path(out)
    cad=root/'CyberTrack.FCStd'
    tree_path=root/'model-tree-audit.json'
    tree=json.loads(tree_path.read_text())
    before_sha=sha(cad)
    assert tree['delivery_sha256']==before_sha
    source=root/tree['source_document']
    assert sha(source)==tree['source_sha256']
    labels=part_labels()
    with zipfile.ZipFile(cad) as archive:
        entries=[(info, archive.read(info.filename)) for info in archive.infolist()]
    xml=ET.fromstring(dict((info.filename,data) for info,data in entries)['Document.xml'])
    original=copy.deepcopy(xml)
    objects={o.attrib['name']:o for o in xml.find('ObjectData')}
    assert set(objects)==set(labels)|{'Drive'}
    rows=[]
    changed=0
    for name,label in labels.items():
        props={p.attrib['name']:p for p in objects[name].find('Properties')}
        current=props['Label'].find('String')
        description=props['Label2'].find('String')
        old=current.attrib['value']
        if old!=label:
            changed+=1
            description.set('value','\n'.join(v for v in (description.attrib['value'],old) if v))
            current.set('value',label)
        rows.append({'name':name,'label':label,'description':description.attrib['value']})
    if not changed:
        return json.loads((root/'part-names-audit.json').read_text())
    # Compare all remaining document properties, including placement, links and evidence.
    stripped=copy.deepcopy(xml)
    for document in (stripped,original):
        for obj in document.find('ObjectData'):
            for prop in obj.find('Properties'):
                if prop.attrib['name'] in ('Label','Label2'):
                    prop.find('String').set('value','')
    assert ET.tostring(stripped)==ET.tostring(original)
    payload=ET.tostring(xml,encoding='utf-8',xml_declaration=True)
    fd,temp=tempfile.mkstemp(prefix='CyberTrack-labels-',suffix='.FCStd',dir=root)
    os.close(fd)
    doc=None
    try:
        with zipfile.ZipFile(temp,'w') as archive:
            for info,data in entries:archive.writestr(info,payload if info.filename=='Document.xml' else data)
        with zipfile.ZipFile(temp) as archive:
            assert all(archive.read(info.filename)==data for info,data in entries if info.filename!='Document.xml')
        doc=App.openDocument(temp)
        assert len(doc.Objects)==302 and doc.Drive.Label=='01 双履带与动力参考'
        for row in rows:
            obj=doc.getObject(row['name'])
            assert obj.Label==row['label'] and obj.Label2==row['description'],row['name']
        assert [o.Name for o in doc.Drive.Group]==tree['drive_members']
        App.closeDocument(doc.Name)
        doc=None
        os.replace(temp,cad)
    finally:
        if doc is not None:App.closeDocument(doc.Name)
        if os.path.exists(temp):os.unlink(temp)
    assert sha(source)==tree['source_sha256']
    after_sha=sha(cad)
    audit={'delivery_document':'CyberTrack.FCStd','before_sha256':before_sha,'delivery_sha256':after_sha,
           'source_document':tree['source_document'],'source_sha256':tree['source_sha256'],
           'part_count':301,'unique_labels':301,'renamed_count':changed,
           'geometry_and_gui_entries_byte_identical':True,'other_document_properties_unchanged':True,
           'native_readback_passed':True,'passed':True,'objects':rows}
    tree['delivery_sha256']=after_sha
    tree['label_audit']='part-names-audit.json'
    report_path=root/'readback.json'
    report=json.loads(report_path.read_text())
    descriptions={r['name']:r['description'] for r in rows}
    for row in report['objects']:
        row['label']=labels[row['name']]
        row['description']=descriptions[row['name']]
    report['files_sha256']['CyberTrack.FCStd']=after_sha
    report['model_tree']['delivery_sha256']=after_sha
    report['model_tree']['label_audit']='part-names-audit.json'
    report['part_names']={k:v for k,v in audit.items() if k!='objects'}
    for path,data in [(tree_path,tree),(report_path,report),(root/'part-names-audit.json',audit)]:
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    return audit
