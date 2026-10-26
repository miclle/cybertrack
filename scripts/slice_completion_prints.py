"""Slice omitted PLA parts together and compare conservative/fast path candidates."""
import json,concurrent.futures
from pathlib import Path
import slice_remaining_prints as slicer
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'hardware/model/completion-print'
PARTS=[('WaterPod',48,62),('BubblePod',115,62),('EffectTray',72,125),('IgnitionMOSCarrier',180,125),('IgnitionMOSRetainer',180,155),('ChestAudioPanel',60,170),('PrintChestGuardL',140,198),('PrintChestGuardR',185,198),('LowerChin',60,200),('ChestBadge',60,220),('WaterLidMark',100,220),('BubbleLidMark',125,220)]
def run_all():
 slicer.OUT=OUT;slicer.REF=ROOT/'hardware/model/print-ready/CyberTrack-Ready-5plates.3mf'
 cases=[('reference-024',PARTS,{'layer_height':'0.24','wall_generator':'classic'}),('fast-028',PARTS,{'wall_generator':'arachne'}),('wide-028',PARTS,{'wall_generator':'arachne','line_width':'0.6','outer_wall_line_width':'0.6','inner_wall_line_width':'0.6','top_surface_line_width':'0.6'})]
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(slicer.run,cases))
 (OUT/'comparison.json').write_text(json.dumps(rows,indent=2)+'\n')
if __name__=='__main__':run_all()
