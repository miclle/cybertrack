"""Order the delivery tree by nearby assemblies, then top to bottom."""
import copy
import json
import os
from pathlib import Path
from statistics import median
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from model_tree import sha


def ordered_parts(report, drive_members):
    objects={o['name']:o for o in report['objects']}
    clusters={}
    overrides={'PrintCrown':'冠盖','PrintNeck':'颈架','PrintWaterCradle':'水枪',
               'PrintBubbleCradle':'泡泡枪','PrintBackpack':'背包','PrintLowerTub':'底盘结构',
               'BottomServiceCover':'底部检修盖','KeelLid':'底盘顶盖','BaseCableGrommet':'底盘顶盖'}
    for name,obj in objects.items():
        if name in drive_members:
            continue
        section=obj['label'].split(' · ')[0]
        cluster=overrides.get(name,section)
        if name in overrides:pass
        elif name.startswith('PowerSwitch'):cluster='底盘顶盖'
        elif name.startswith('BottomCoverScrew'):cluster='底部检修盖'
        elif section in ('履带','动力'):cluster='履带与动力'
        elif section=='底盘':cluster='底盘结构'
        clusters.setdefault(cluster,[]).append(name)
    clusters['履带与动力'].append('Drive')

    def center(name):
        if name=='Drive':
            boxes=[objects[n]['bbox_mm'] for n in drive_members]
            return tuple((min(b[i] for b in boxes)+max(b[i+3] for b in boxes))/2 for i in range(3))
        b=objects[name]['bbox_mm']
        return tuple((b[i]+b[i+3])/2 for i in range(3))

    def position_key(name):
        x,y,z=center(name)
        # Keep matched left/right pieces adjacent when heights and fore/aft align.
        return (-round(z,2),round(y,2),-round(x,2),name)

    blocks=[]
    for cluster,members in clusters.items():
        members.sort(key=position_key)
        blocks.append({'assembly':cluster,'height_mm':median(center(n)[2] for n in members),'members':members})
    blocks.sort(key=lambda b:(-b['height_mm'],b['assembly']))
    roots=[n for b in blocks for n in b['members']]
    # All left-side reference parts followed by the corresponding right side.
    drive=sorted(drive_members,key=lambda n:(0 if ('Left' in n or n.endswith('L')) else 1,position_key(n)))
    full=[]
    for name in roots:
        full.append(name)
        if name=='Drive':full.extend(drive)
    assert len(roots)==276 and len(full)==306 and len(set(full))==306
    return roots,drive,full,blocks


def reorder(out):
    root=Path(out)
    cad=root/'CyberTrack.FCStd'
    report_path=root/'readback.json'
    report=json.loads(report_path.read_text())
    tree_path=root/'model-tree-audit.json'
    tree=json.loads(tree_path.read_text())
    before=sha(cad)
    assert before==tree['delivery_sha256']
    assert sha(root/tree['source_document'])==tree['source_sha256']
    roots,drive,full,blocks=ordered_parts(report,tree['drive_members'])
    with zipfile.ZipFile(cad) as archive:
        entries=[(info,archive.read(info.filename)) for info in archive.infolist()]
    contents={i.filename:d for i,d in entries}
    xml=ET.fromstring(contents['GuiDocument.xml'])
    document=ET.fromstring(contents['Document.xml'])
    group=document.find("ObjectData/Object[@name='Drive']/Properties/Property[@name='Group']/LinkList")
    links={link.attrib['value']:link for link in group}
    assert set(links)==set(drive)
    old_group_order=[link.attrib['value'] for link in group]
    group[:]=[links[name] for name in drive]
    old=copy.deepcopy(xml)
    providers={v.attrib['name']:v for v in xml.find('ViewProviderData')}
    assert set(providers)==set(full)
    for rank,name in enumerate(full):providers[name].set('treeRank',str(rank))
    if ET.tostring(xml)==ET.tostring(old) and old_group_order==drive:
        return json.loads((root/'part-order-audit.json').read_text())
    stripped=copy.deepcopy(xml)
    for gui_document in (stripped,old):
        for v in gui_document.find('ViewProviderData'):v.set('treeRank','')
    assert ET.tostring(stripped)==ET.tostring(old)
    payload=ET.tostring(xml,encoding='utf-8',xml_declaration=True)
    document_payload=ET.tostring(document,encoding='utf-8',xml_declaration=True)
    group[:]=[links[name] for name in old_group_order]
    assert ET.tostring(document)==ET.tostring(ET.fromstring(contents['Document.xml']))
    fd,temp=tempfile.mkstemp(prefix='CyberTrack-order-',suffix='.FCStd',dir=root)
    os.close(fd)
    try:
        with zipfile.ZipFile(temp,'w') as archive:
            for info,data in entries:
                if info.filename=='GuiDocument.xml':data=payload
                elif info.filename=='Document.xml':data=document_payload
                archive.writestr(info,data)
        with zipfile.ZipFile(temp) as archive:
            assert all(archive.read(i.filename)==d for i,d in entries if i.filename not in ('Document.xml','GuiDocument.xml'))
        os.replace(temp,cad)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    after=sha(cad)
    audit={'delivery_document':'CyberTrack.FCStd','before_sha256':before,'delivery_sha256':after,
           'source_document':tree['source_document'],'source_sha256':tree['source_sha256'],
           'method':'Assembly median height descending; members by Z descending, Y ascending, X descending',
           'root_count':276,'part_count':305,'root_order':roots,'drive_display_order':drive,'assemblies':blocks,
           'geometry_entries_byte_identical':True,'document_properties_except_group_order_unchanged':True,
           'gui_properties_except_tree_rank_unchanged':True,
           'rank_metadata_verified':True}
    tree['delivery_sha256']=after
    tree['drive_members']=drive
    tree['order_audit']='part-order-audit.json'
    report['model_tree']['delivery_sha256']=after
    report['model_tree']['drive_members']=drive
    report['model_tree']['order_audit']='part-order-audit.json'
    report['files_sha256']['CyberTrack.FCStd']=after
    index={o['name']:o for o in report['objects']}
    report['objects']=[index[n] for n in full if n!='Drive']
    report['part_order']={k:v for k,v in audit.items() if k not in ('root_order','drive_display_order','assemblies')}
    # The naming proof records the prior byte-identical geometry/GUI state. Its
    # hash remains historical; the order audit explicitly links it to this file.
    for path,data in [(root/'part-order-audit.json',audit),(tree_path,tree),(report_path,report)]:
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    return audit
