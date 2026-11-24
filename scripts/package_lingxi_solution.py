#!/usr/bin/env python3
"""Package an explicit text-only Lingxi reference bundle; never publish it."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

from check_firmware_current import check
from review_lingxi_reference import EVALUATIONS, score_replay, score_spoken_replay, STT_SPOKEN_SCORE, STT_EXPERIMENT, STT_CAPTURE
from review_lingxi_reference import FULL_SPEECH_SCORES, score_full_speech
from review_full_speech import score_replay as full_speech_replay

ROOT = Path(__file__).resolve().parents[1]


def read_inputs(root, paths):
    root = root.resolve()
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate bundle entry")
    contents = {}
    for name in sorted(paths):
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not path.parts or str(path) != name:
            raise ValueError("bundle paths must be normalized repository-relative paths")
        allowed_text = path.suffix in {".md", ".json", ".txt", ".py"} or path.name in {"LICENSE", "NOTICE"} or name == "tools/family-study/observer.html"
        if set(path.parts) & {"secrets", "recordings", "output", "tmp", ".git"} or not allowed_text:
            raise ValueError("bundle supports reviewed reference text only")
        target = root / name
        if target.resolve() != target or not target.is_file():
            raise ValueError(f"missing or symlinked bundle input: {name}")
        contents[name] = target.read_bytes()
        contents[name].decode("utf-8")
    return contents


def build_archive(root, paths, head, dirty):
    contents = read_inputs(root, paths)
    firmware = check(root, board="breadboard")
    current = json.loads(contents["firmware/current.json"])
    if "firmware/" + current["software_evidence"] not in contents:
        raise ValueError("current candidate build evidence must be included in the bundle")
    raw = (root / STT_CAPTURE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != json.loads(contents[STT_EXPERIMENT])["files"]["full20.json.gz"]["sha256"]:
        raise ValueError("STT original capture differs from experiment")
    trace = json.loads(gzip.decompress(raw))
    replay = {key: trace[key] for key in ("input_mode", "kind", "run_id", "model", "role_sha256", "corpus_sha256",
                                         "synthesis_source_sha256", "capture_source_sha256", "tool_schema_sha256",
                                         "host_input_mode", "fixture_version", "host_replay_sha256")}
    replay["results"] = [{key: row[key] for key in ("id", "input_text", "echoed_text", "completed", "completion", "calls",
                                                  "uplink", "replies", "received_audio_bytes_discarded")} |
                         {"simulated_receipts": [{"result": receipt.get("result")} for receipt in row.get("simulated_receipts", [])]}
                         for row in trace["results"]]
    score_spoken_replay(replay, json.loads(contents[STT_SPOKEN_SCORE]))
    contents["replay/stt/voice.json"] = (json.dumps(replay, ensure_ascii=False, indent=2) + "\n").encode()
    full_scores = json.loads(contents[FULL_SPEECH_SCORES])['suites']
    for suite in ('voice', 'compose'):
        raw = (root / FULL_SPEECH_SCORES).with_name(f'full-{suite}.json.gz').read_bytes()
        recorded = full_scores[suite]
        if hashlib.sha256(raw).hexdigest() != recorded['capture_gzip_sha256']:
            raise ValueError(f'{suite}: full speech compressed capture differs')
        payload = gzip.decompress(raw)
        if hashlib.sha256(payload).hexdigest() != recorded['capture_json_sha256']:
            raise ValueError(f'{suite}: full speech original capture differs')
        replay = full_speech_replay(json.loads(payload))
        score_full_speech(suite, contents[f'docs/validation/{suite}-cases.json'], replay, recorded['speech_score'])
        contents[f'replay/ct71-full-stt/{suite}.json'] = (json.dumps(replay, ensure_ascii=False, indent=2) + '\n').encode()
    for prefix, score_path, suites, _ in EVALUATIONS:
        scores = json.loads(contents[score_path])
        for suite in suites:
            raw = gzip.decompress((root / score_path).with_name(f"full-{suite}.json.gz").read_bytes())
            if hashlib.sha256(raw).hexdigest() != scores[suite]["capture_json_sha256"]:
                raise ValueError(f"{prefix}{suite}: original capture does not match recorded score")
            trace = json.loads(raw)
            replay = {key: trace[key] for key in ("run_id", "kind", "role_sha256", "model", "corpus_sha256", "fixture_version")}
            if prefix:
                for key in ("tool_schema_sha256", "input_mode", "fixture_version"):
                    replay[key] = trace[key]
                    if replay[key] != scores[suite][key]:
                        raise ValueError(f"{prefix}{suite}: recorded {key} differs")
                if "host_replay_sha256" in trace:
                    replay["host_replay_sha256"] = trace["host_replay_sha256"]
                    if replay["host_replay_sha256"] != scores[suite]["host_replay_sha256"]:
                        raise ValueError(f"{prefix}{suite}: host implementation differs")
            replay["results"] = [{key: row[key] for key in ("id", "calls", "completed")} for row in trace["results"]]
            score_replay(suite, contents[f"docs/validation/{suite}-cases.json"], replay, scores[suite])
            contents[f"replay/{prefix}{suite}.json"] = (json.dumps(replay, ensure_ascii=False, indent=2) + "\n").encode()
    contents["START_HERE.md"] = f"""# CyberTrack 灵矽方案参考材料

ct78 已移除表演编辑与预览。包内旧 compose 轨迹仅供复算历史结果，不代表当前功能或当前角色成绩。

本包对应 Git 提交 `{head}`。打包输入存在未提交修改为 `{dirty}`。版本、应用字节数和 SHA-256 见 `MANIFEST.json` 的 `firmware` 小节。

| 记录 | 固件版本 |
|---|---|
| 源码与构建依据 | `{firmware['source_version']}` |
| 最近一次应用部署 | `{firmware['recorded_deployment']}` |

## 复算文本与合成语音记录

解压后在本目录运行。只需要 Python 3.9 或更高版本。

```sh
python3 scripts/review_lingxi_reference.py
```

评分器用包内语料和回放重新计算工具匹配、缺例、禁止调用和停止偏差，并校验清单中的文件。各组保留采集时的模型、角色、输入方式和固件版本。未完成会话和失败用例随结果列出。

修改 v2 时从[当前状态](docs/current-status.md)、[设备接口](firmware/CAPABILITIES.md)与[角色源](firmware/esp32-audio/role-prompt.txt)开始。新角色的现场语音验证按[验收矩阵](docs/verification-plan.md)执行。

主持人可用浏览器打开包内的[亲子观察单](tools/family-study/observer.html)，逐户下载匿名记录，用 `python3 scripts/analyze_family_sessions.py 记录目录/*.json` 分别汇总原型与实机结果。

包内材料可离线阅读和评测。原始部署记录、完整轨迹和 CAD 资产见[对应源码提交](https://github.com/miclle/cybertrack/tree/{head})。还可以在包内运行以下检查。

```sh
python3 -m unittest discover -s tests/improvements -v
python3 scripts/power_budget.py
```
""".encode()
    manifest = {"schema_version": 2, "scope": "Lingxi offline reference material",
                "git_head": head, "selected_inputs_dirty": dirty, "firmware": firmware,
                "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in contents.items()},
                "excluded": ["credentials", "recordings", "device identifiers", "firmware binaries", "physical acceptance", "CAD binaries"],
                "model_evaluation": "replay of recorded tool calls; no new model request", "family_trials": "not_run"}
    contents["MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
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
    current = json.loads((ROOT / "firmware/current.json").read_bytes())
    sources = ["tools/lingxi-solution/files.json", "scripts/package_lingxi_solution.py", "scripts/check_firmware_current.py",
               "firmware/esp32-audio/apply_overlay.py", "firmware/" + current["last_recorded_deployment"], STT_CAPTURE,
               *(str(Path(score_path).with_name(f"full-{suite}.json.gz"))
                 for _, score_path, suites, _ in EVALUATIONS for suite in suites)]
    sources.extend(str(Path(FULL_SPEECH_SCORES).with_name(f'full-{suite}.json.gz')) for suite in ('voice', 'compose'))
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--", *paths, *sources], cwd=ROOT, text=True))
    payload = build_archive(ROOT, paths, head, dirty)
    output = args.output or ROOT / "output/lingxi-solution" / f"cybertrack-lingxi-reference-{head[:12]}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(payload)
    print(json.dumps({"path": str(output.resolve()), "bytes": len(payload),
                      "sha256": hashlib.sha256(payload).hexdigest(), "selected_inputs_dirty": dirty}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
