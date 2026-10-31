# CyberTrack 模型辅助设计工具

CyberTrack 的模型辅助设计工具将“点选零件 → 提出修改 → 原生 CAD 修改 → 回读 → 恢复”用于可维护零件设计。它属于开发阶段工具，机器人日常语音仍直接通过灵矽运行。产品入口展示设计能力与使用价值；底层插件来源、版本和许可证在本文维护。

## 已交付的接入

[lock.json](lock.json) 固定上游提交 `13698aeebce8e26aa2e7f371b7170c854dba5f4d`（0.8.0，Apache-2.0）。完整源代码、原许可证及作者信息保留在独立 checkout；本项目不复制或重写上游插件。仓库目前需要有权访问 [miclle/solidcue](https://github.com/miclle/solidcue)，不能声称无权限用户也能直接复现。

在 CyberTrack 仓库根目录执行：

```sh
python3 scripts/solidcue.py prepare
python3 scripts/solidcue.py check
python3 scripts/solidcue.py start
```

需要 Git、Node.js ≥24、npm、uv 和可用的 Python 3.12。`prepare` 下载锁定源代码与依赖并构建插件；checkout 版本不符或存在修改时拒绝覆盖。服务使用 `output/solidcue/data/`，初始文档为空，监听 `127.0.0.1:9473`。端口占用时退出，避免覆盖已有 SolidCue 会话。数据、导出与研究件均在忽略目录，不包含录音或凭据。

插件仍沿用上游 `cad-comment-lab@cad-comment-local` 标识；安装／宿主重载见固定 checkout 的 `README.md`，FreeCAD 连接见 `docs/freecad-bridge.md`。`prepare/check/start` 不隐式修改全局插件配置。2026-10-31 已另行通过下述 Codex CLI 步骤安装固定版本；安装与真实宿主卡片验收分别记录。独立浏览器可检查预览，但真实空间评论投递与同卡片更新必须使用原生 MCP 插件验收。

## 安装固定版本插件与协议检查

先完成前面的 `prepare/check`，再从 CyberTrack 根目录执行：

```sh
codex plugin marketplace add "$PWD/tmp/solidcue-source"
codex plugin add cad-comment-lab@cad-comment-local
codex plugin list --marketplace cad-comment-local --json
```

2026-10-31 本机安装结果为 `0.8.0`、installed／enabled。marketplace 指向本项目锁定 checkout；不要删除该目录后再期待本地插件来源仍可用，也不要将它静默改指向其他版本。安装是本机 Codex 配置，不随仓库 clone 自动完成。

保持 `python3 scripts/solidcue.py start` 运行，再在另一个终端执行：

```sh
node scripts/check_solidcue_plugin.mjs
```

该命令比对安装缓存与锁定构建的 manifest、MCP 配置、服务脚本及 UI 字节，再通过已安装入口读取工具、资源和实时状态。覆盖 `sync_cad_snapshot` 在内的 13 个工具、CyberTrack 收件目录和未绑定 CLI 会话；仅调用 `get_state/open_model`，不会写评论或编辑模型。输出带时间戳的 `output/solidcue/plugin-check-*.json`。

它不在宿主中展开卡片，也不证明 `ui/message` 已投递。真实卡片仍须桌面重载后由本对话的 SolidCue 工具打开。锁定上游的 `mcp.test.mjs` 工具名单漏列 `sync_cad_snapshot`，因此本项目使用上述实际安装检查；不修改锁定上游来绕过版本校验。

## 从现有设计建立独立研究件

当前整机多数零件是静态 `Part::Feature`，不能把它们描述成可直接修改任意尺寸的参数模型。先从明确的单件开始：电池右前承托垫 `BatteryPadN54N90`，几何是 5 × 5 × 0.2 mm 的矩形实体。

`scripts/solidcue_freecad.py` 只在形状确实与轴对齐长方体等价时建立 `Part::Box` 研究件；复杂零件拒绝转换，不能用包络盒替代真实造型。它保留 X 向左、Y 向后、Z 向上的坐标，以原始文件 SHA-256 记录来源，始终另存至 `output/solidcue/studies/<唯一ID>/study.FCStd`。生产文件已在该进程打开时拒绝操作，避免把未保存修改归属于磁盘版本。

使用带 FreeCAD 模块的 Python，例如本机：

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
  /Applications/FreeCAD.app/Contents/Resources/bin/python \
  scripts/solidcue_freecad.py --object BatteryPadN54N90 --verify
```

该命令在独立研究件中完成 Length 5 → 6 → 5 mm，校验旧指纹拒绝、原生恢复几何，并导出 STEP／FCStd 快照。输出中的 `study_directory` 用于下一步：

```sh
node scripts/check_solidcue_sync.mjs <study_directory>
```

同步检查覆盖真实 STEP 的六面映射、合成评论与版本拒绝、修改与恢复记录，以及生产 FCStd 哈希保持一致。`--verify` 是主机验证，不是一次真实用户设计请求；恢复后不改正式模型，不产生制造放行。

## 实际设计闭环

1. 用 FreeCAD 打开独立研究件；通过已连接的 FreeCAD MCP 核对文档、对象、可编辑属性及实际桥接路径。
2. 原生导出唯一快照，再由 SolidCue `sync_cad_snapshot` 以 `attach` 接入空白文档。
3. 在真实卡片选择零件或面，明确修改哪个参数及目标毫米值。对话核对评论版本、hash 和原生 fingerprint。
4. 通过 FreeCAD MCP 修改，成功导出后同步 `edit`；同步失败时保留原生状态并先修复同步，禁止盲目再次编辑。
5. 需要撤销时，恢复最近一次原生属性编辑并同步 `undo`；不能只换回旧预览。
6. 几何检查、装配间隙、打印与实物维护分别验证，通过后再决定是否纳入生产模型。

首版只支持有效单实体、已有可编辑且无表达式绑定的长度属性。整机装配、任意草图编辑和跨版本稳定面引用不在保证范围。

## 当前证据与下一步

[接入验证记录](verification-20261031.json)记录真实 FreeCAD 1.1.4 的修改／恢复与 SolidCue STEP 同步结果；插件构建及 `npm run test:bundle` 也已通过。生产模型未改动。

2026-10-31 已安装并通过[实际插件协议检查](verification-installed-20261031.json)，13 个工具及独立空白数据目录正确；本机服务已启动但未配置自动启动。FreeCAD RPC 仍返回连接拒绝，最近桌面检查为 Mac 锁屏。尚未完成真实桌面卡片的评论投递、原生工具修改和同卡片恢复。上游既有桌面结果不替代 CyberTrack 的验收。下一步是连接 FreeCAD、重载固定版本插件，在该独立研究件完成上述六步并补实际截图／回执；此项不依赖机器人实机，但依赖桌面宿主连接。
