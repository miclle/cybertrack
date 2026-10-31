#!/usr/bin/env python3
"""Build an offline exercise using the shipped theatre editor and a local screen-only stage."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(root=ROOT):
    page = (root / "firmware/esp32-audio/web/index.html").read_text()
    script = (root / "tools/family-study/rehearsal.js").read_text()
    head = """<meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'none'; base-uri 'none'">
<title>小D 泡泡剧场 · 离线排演</title>
<style>main> :not(#theatre):not(#paper){display:none!important}#paper{position:sticky;top:0;z-index:3;background:#faf9f5;border-bottom:2px solid #829739;padding:10px 4px}#paper p{margin:4px 0}#paper-stage{font-weight:650}#paper small{color:#4c584a}</style>"""
    stage = """<section id="paper"><small>CyberTrack · 离线排演 · 仅在屏幕上演示</small><h1>小D 泡泡剧场</h1>
<p id="paper-stage" role="status">选一段开场，试着当一次导演。</p></section>"""
    for old, new in (
        ("<title>CyberTrack</title>", head),
        ('online = false; disconnect("网络已断开，网页动作已请求停止。");',
         '// The screen-only stage has no network dependency.'),
        ('>保存到设备并预览<', '>保存排演草稿并预览<'),
        ('>家长确认开始<', '>家长确认排演<'),
        ('<details id="theatre"', stage + '<details open id="theatre"'),
        ("选一个开场，或载入语音编好的草稿。", "选一个开场，在这张纸上舞台保存、预览和排演。"),
        ('</footer><script>', '</footer><script>' + script + '</script><script>'),
    ):
        if page.count(old) != 1:
            raise ValueError(f"The shipped editor changed; check rehearsal integration at {old}")
        page = page.replace(old, new)
    return page


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/family-study/rehearsal.html")
    target = parser.parse_args().output
    target.parent.mkdir(parents=True, exist_ok=True)
    content = build()
    if target.exists() and target.read_text() != content:
        parser.exit(2, "Output already exists and differs; choose a new --output path.\n")
    if not target.exists():
        with target.open("x") as stream:
            stream.write(content)
    print(target.resolve())
