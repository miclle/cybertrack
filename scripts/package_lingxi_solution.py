#!/usr/bin/env python3
"""Package an explicit text-only Lingxi reference bundle; never publish it."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build_archive(root, paths, head, dirty):
    root = root.resolve()
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate bundle entry")
    contents = {}
    for name in sorted(paths):
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not path.parts or str(path) != name:
            raise ValueError("bundle paths must be normalized repository-relative paths")
        if set(path.parts) & {"secrets", "recordings", "output", "tmp", ".git"} or path.suffix not in {".md", ".json", ".txt", ".py"}:
            raise ValueError("bundle supports reviewed reference text only")
        target = root / name
        if target.resolve() != target or not target.is_file():
            raise ValueError(f"missing or symlinked bundle input: {name}")
        contents[name] = target.read_bytes()
        contents[name].decode("utf-8")
    manifest = {"schema_version": 1, "scope": "Lingxi reference material, not deployed firmware or complete CAD distribution",
                "git_head": head, "selected_inputs_dirty": dirty,
                "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in contents.items()},
                "excluded": ["credentials", "recordings", "device identifiers", "firmware binaries", "physical acceptance", "CAD binaries"],
                "model_evaluation": "not_run", "family_trials": "not_run"}
    contents["MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    contents["START_HERE.md"] = f"""# CyberTrack 灵矽方案参考材料

本包用于评审、接入设计和无设备评测准备，不是可刷写固件或完整 CAD 分发。
来源 Git 提交：`{head}`；所选文件未提交修改：`{dirty}`。实际文件以 MANIFEST.json 哈希为准。

1. 阅读 docs/lingxi-solution.md：场景、平台职责、方案交付与平台建议。
2. 阅读 docs/quick-start.md 和 firmware/CAPABILITIES.md：亲子上手、当前能力及限制。
3. 以 firmware/esp32-audio/role-prompt.txt 核对角色；参考包不向平台上传配置。
4. 使用 docs/validation/ 中的文本集、口述集和空白采集模板，不把测试样例当成模型或用户结果。
5. 阅读 hardware/architecture/README.md 和 tools/solidcue/README.md：硬件与设计工具边界。

无需设备的检查：

```sh
python3 -m unittest discover -s tests/improvements -v
python3 scripts/power_budget.py
python3 scripts/evaluate_voice.py --help
```

本包只包含明确清单中的材料。文档中的其他相对链接须在完整 CyberTrack checkout 中阅读；完整源码、BOM、原理图和大体积模型对应 https://github.com/miclle/cybertrack/tree/{head} 。该提交未推送时远端链接尚不可用，应使用本地 checkout；未提交内容以清单为准。

泡泡剧场与确认编排仍按计划推进。真人语音、五组家庭体验、当前供电与完整停止验收未完成。没有录音、Wi-Fi 凭据、设备令牌或绑定码；没有替你部署或发布。
""".encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new archive path; existing files are never replaced")
    args = parser.parse_args()
    paths = json.loads((ROOT / "tools/lingxi-solution/files.json").read_text())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--", *paths], cwd=ROOT, text=True))
    payload = build_archive(ROOT, paths, head, dirty)
    output = args.output or ROOT / "output/lingxi-solution" / f"cybertrack-lingxi-reference-{head[:12]}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(payload)
    print(json.dumps({"path": str(output.resolve()), "bytes": len(payload),
                      "sha256": hashlib.sha256(payload).hexdigest(), "selected_inputs_dirty": dirty}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
