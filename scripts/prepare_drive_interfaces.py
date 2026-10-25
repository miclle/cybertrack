"""Extract only the explicitly authorised drive mounting interface, never the body.

Run once for a new reference revision; existing curated assets are read-only.
The 0.3-mm inboard strip is excluded because the old shroud ends at X59.2.
Full four-mm bearing seats are checked separately in drive_mount_check.py.
"""
import argparse,hashlib,json
from pathlib import Path
import FreeCAD as App
import Part


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    args=p.parse_args()
    out=Path(__file__).resolve().parents[1]/'hardware/components/drive-interface'
    if out.exists():raise SystemExit('Refusing to overwrite curated interface reference')
    source=args.input.resolve();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    digest=sha(source);d=App.openDocument(str(source))
    out.mkdir(parents=True)
    try:
        mask=Part.makeBox(13.71,72,45,App.Vector(59.3,-36,28))
        q=d.getObject('LowerChassis').Shape.common(mask)
        assert q.isValid() and len(q.Solids)==1
        path=out/'MotorInterfaceL.brep';q.exportBrep(str(path))
        reread=Part.Shape();reread.read(str(path))
        diff=q.cut(reread).Volume+reread.cut(q).Volume
        assert diff<=1e-5
        screw=d.getObject('TrackMountScrewLFront').Shape
        screwpath=out/'TrackMountScrewLFront.brep';screw.exportBrep(str(screwpath))
        reread=Part.Shape();reread.read(str(screwpath))
        assert screw.cut(reread).Volume+reread.cut(screw).Volume<=1e-5
        report={'source_file':source.name,'source_sha256':digest,'source_object':'LowerChassis',
          'clip_box_mm':[59.3,-36,28,73.01,36,73],
          'coordinate_frame':'source saved world: X left, Y rear, Z up; translate X+14 for CyberTrack left',
          'scope':'motor face and TrackMount standoffs only; excludes old chassis, cover and exterior',
          'readback_difference_mm3':diff,'files_sha256':{x.name:sha(x) for x in (path,screwpath)},
          'source_unchanged':sha(source)==digest,'physical_fit_verified':False}
        (out/'readback.json').write_text(json.dumps(report,indent=2)+'\n')
    finally:App.closeDocument(d.Name)


if __name__=='__main__':main()
