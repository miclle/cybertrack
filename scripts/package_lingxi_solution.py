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
from package_family_rehearsal import build as build_rehearsal
from review_lingxi_reference import EVALUATIONS, score_replay, score_spoken_replay, STT_SPOKEN_SCORE, STT_EXPERIMENT, STT_CAPTURE

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
    contents["family/rehearsal.html"] = build_rehearsal(root).encode()
    firmware = check(root)
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

本包对应 Git 提交 `{head}`。打包输入存在未提交修改为 `{dirty}`。版本、应用字节数和 SHA-256 见 `MANIFEST.json` 的 `firmware` 小节。

| 记录 | 固件版本 |
|---|---|
| 源码与构建依据 | `{firmware['source_version']}` |
| 最近一次应用部署 | `{firmware['recorded_deployment']}` |

## 从七种文本记录分别重算成绩

解压后在本目录运行。只需要 Python 3.9 或更高版本。

```sh
python3 scripts/review_lingxi_reference.py
```

从此包复现的是记录所列工具版本和角色的结果，历史基线保留在 scores，ct57 工具回归保留在 candidate_scores，ct61 原话和真实固件主机的 80 条语义及八条编排另在 firmware_host_scores，编排首次超时继续列入 incomplete。程序核对清单列出的文件，并逐条比较捕获的工具调用、参数和调用顺序。输出分别列出七种文本记录的成绩、偏差用例编号与门槛判断，并标明工具来源和输入模式。命令成功表示复现了记录，编排组原有的失败会保留。平台输入采用文本，静态夹具与真实固件主机分别标识。完整主机源码与构建入口见[固件主机验证](docs/validation/firmware-host.md)，参考包离线复算工具选择，控制守卫重放需要完整 checkout。真人拾音、扬声器听感、机械动作和家庭体验需分别验收。

- [模型参数与选型对照](docs/validation/model-parameters.md)中的未采纳结果也可复算：`qwen_scores` 保留完整语义／编排与漏停、禁止调用，`doubao_compose_scores` 保留八条编排及畸形参数失败。豆包二十条语义仅为诊断子集，不在本包重算完整语义成绩。
- [单次识别失败隔离](docs/validation/voice-input-guard.md)另附 ct62 构建及离线控制回放证据；C005 拒绝后换用 sequence 被拦截，零启动。它不是新的模型成绩，原模型禁止调用记录保持不变。重跑控制回放仍需完整 checkout 与 prepared 固件，本包仅核对所存材料的完整性。
- [真实 STT 驱动主机](docs/validation/ct62-stt-host.md)的二十条合成语音另在 `spoken_stt_review` 复算转写与工具结果：19 条正常结束并匹配，V017 未收到结束事件仍保留。事件与控制回执完整重放需要完整 checkout 和固定主机二进制。
- [ct63 播放匹配](docs/validation/plan-feedback.md)另附构建和离线回放：同一批事件新增抑制 216 个组合／序列／目标速度确认包，保留 397 个状态／否定／澄清包；30 条合成不一致保留音频。这不是新的模型成绩，播放重跑需要完整 checkout 和同版 C++ 回放器。
- [回执收敛试验](docs/validation/compact-model-receipts.md)未采纳；`compact_receipt_scores` 保留 5/8 及 C006 的禁止调用。字节减少不等于语义通过，该试验结束后恢复 ct63，当前候选见版本表。实验源码补丁和完整 MCP 重放需要按专题中的范围复核。
- [停止说明对照](docs/validation/stop-negation.md)也未采纳；`stop_negation_scores` 重算语义 77/80 与编排 6/8，继续标明 V064 误停、V079 含糊请求擅自前进。八条明确停止通过不能抵消禁止调用；诊断 ct65 未部署，该试验结束后恢复 ct63，当前候选见版本表。
- [ct66 即时停止回执](docs/validation/stop-dispatch.md)附八组实际 MCP 调度回放、回执分配失败和十三组软件检查摘要。停止校验后同步完成，不留二次回调；公开工具及角色不变。包内只核对记录完整性，重跑控制与分配失败测试需要完整 checkout，不是第八组模型成绩，也没有部署。
- [状态话术限定](docs/validation/stop-role-qualifier.md)的十四次定向对照未采纳：两组严格匹配均 6/7，停止静默均 0/3，平台原角色已恢复。它不是第八组完整模型评分。[灵矽联调反馈](docs/validation/platform-tts-feedback.md)另提供过程文字进入 TTS 与含糊改稿的事件、复核步骤和协作问题，尚未代发。
- [ct67 相对改稿门禁](docs/validation/relative-draft-duration.md)附十三组原生回放、分类器来源和二十条定向合成语音审阅。真实 STT／终态均 20/20，严格调用 14/20，六条多查状态，在线实际澄清拒绝为零。它不替代旧 `spoken_stt_review` 或增加第八组完整文本评分；本包只核对这些材料的完整性，完整控制重放需 checkout 与对应主机。
- [ct68 含糊动作门禁](docs/validation/vague-action-admission.md)附二十六组原生对照和二十条定向真实 STT 审阅：严格调用 16/20、终态 20/20，三次猜测执行被拒绝。八条含糊输入零启动不能抵消模型错误或多余查询；本包仅核对材料完整性，不增加第八组固定成绩。原始压缩轨迹及完整控制重放需要 checkout，最近部署仍为 ct45。
- [意图分流角色对照](docs/validation/intent-routing-role.md)72 次文本会话未采纳：两组均 29/36，各有禁止调用，停止静默均 0/6；原角色与参数已恢复。该主机使用占位识别文本，不能计作 STT 门禁覆盖。本包只核对所存材料完整性，不增加第八组固定模型成绩；完整回放需要 checkout 与原始轨迹。
- [编排说明对照](docs/validation/compose-routing.md)保留了未采纳的诊断：工具匹配增多，但一次含糊请求擅自缩短草稿。包内含摘要与两份定义，原始轨迹和该诊断的重算需要完整 checkout。
- 场景、平台职责与复用方法见[灵矽解决方案](docs/lingxi-solution.md)。
- 家长可阅读[上手卡](docs/quick-start.md)，开发者可核对[设备能力](firmware/CAPABILITIES.md)及[角色源文件](firmware/esp32-audio/role-prompt.txt)。
- 语义偏差见[候选完整回归](docs/validation/lingxi-ct57-full.md)与[历史基线](docs/validation/lingxi-role-5991.md)，远端音频包的端侧处理见[播放回归](docs/validation/lingxi-ct51-playback.md)。
- 供电与机械设计见[硬件架构](hardware/architecture/README.md)和[整机模型辅助设计](tools/model-design/README.md)。

家长与孩子可双击[离线泡泡剧场](family/rehearsal.html)，选择模板、修改和确认，在屏幕上排演各步，也可以中途全停。排演页内没有设备或灵矽连接。主持人可用浏览器打开包内的[亲子观察单](tools/family-study/observer.html)，逐户下载匿名记录，用 `python3 scripts/analyze_family_sessions.py 记录目录/*.json` 分别汇总原型与实机结果。

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
    sources.extend(["scripts/package_family_rehearsal.py", "tools/family-study/rehearsal.js", "firmware/esp32-audio/web/index.html"])
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
