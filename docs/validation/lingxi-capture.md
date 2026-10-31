# 灵矽隔离文本联调

此入口验证真实灵矽服务的工具发现、工具选择和回复。它不连接机器人 HTTP、串口或执行器，不接受设备回调；状态与执行回执是内存模拟数据。模型返回的动作调用只记录，不执行。它不能证明真人语音识别、固件执行、物理效果或儿童使用通过。

协议依据为灵矽官方 [WebSocket 文档](https://linx.qiniu.com/docs/xrobot/platform/websocket)与[端侧 MCP 文档](https://linx.qiniu.com/docs/xrobot/mcp/hardware-mcp)。捕获器固定连接官方 WSS 地址，保留证书校验。使用现有 CyberTrack 绑定的认证信息；只在已授权联调、机器人无语音会话时运行，不创建绑定、不更换平台模型或音色。测试文字会进入该智能体的会话记录。返回音频只计字节数后丢弃，不保存录音。

## 准备与运行

先按 [角色流程](../agent-role.md)保存并回读当前角色，确认对应固件。模型名称取自平台可见配置；WSS 不返回模型身份，记录不能将配置名称冒充服务端签名证明。

```sh
uv venv build/lingxi-capture-venv
uv pip install --python build/lingxi-capture-venv/bin/python websockets==15.0.1
python3 scripts/export_lingxi_tools.py --source build/xiaozhi-ct45-src \
  --output build/ct45-private/tool-schemas.json
```

导出器核对 prepared 注册源码与仓库一致，使用该构建树实际 `mcp_server.h` 的序列化方法；编译前将所有工具回调替换为空操作，不编译 GPIO／网络执行路径。仅导出 12 个 `self.tank.*` 工具，不含模型设计插件工具。此步骤是主机导出，真实远端发现以捕获中的 initialize／tools/list 事件为证。

认证文件放在 Git 忽略目录，权限为 `0600`。字段为 `token`、`device_id`、`client_id`，值由获授权设备的现有 OTA／配置流程取得；不能粘贴进公开记录或提交。捕获器不自动提取浏览器凭据。

```sh
build/lingxi-capture-venv/bin/python scripts/capture_lingxi.py \
  --connection build/ct45-private/capture-connection.json \
  --tools build/ct45-private/tool-schemas.json \
  --corpus docs/validation/voice-cases.json \
  --role firmware/esp32-audio/role-prompt.txt \
  --model deepseek-v4-flash --timeout 90 \
  --output output/voice/<唯一运行名>.json
python3 scripts/evaluate_voice.py output/voice/<唯一运行名>.json \
  --output output/voice/<唯一运行名>-score.json
```

编排增量将两条命令的 corpus 改为 `docs/validation/compose-cases.json`（评分命令使用 `--corpus`），输出改用新的唯一文件名。`--ids C001` 可做单条诊断，不能计为完整集通过。已有捕获不覆盖，失败不自动重试；补跑必须保留原记录，不能用后一次成功抹去首轮失败。

## 输入、回执与判定

每例新建会话，发送 hello，按固件 8000 字节上限分页回应 tools/list，末页返回后发送文本。当前入口使用 `listen.detect.text`，不是麦克风 ASR；服务端 STT 文本回传也不能当作语音识别证据。发送内容由“无执行器文本评测”的说明、用例 `context` 和用户原话构成，因此结论只覆盖这种上下文；该前缀可能影响模型行为，不能直接外推到无前缀口述。

捕获循环只读取 ID、原话、前置状态和显式的 `fixture_status`（若有），丢弃 `expected_calls` 与 `response_expectation`。模拟状态覆盖空闲、70% 前进及已有两步草稿；模拟动作接受仅用于观察后续回复，不证明参数被真实固件接受。模拟编排回执按实际捕获参数计算，不复制期望答案。模型原始调用与 TTS 文本均保留。

每例必须收到 TTS stop 才标记 completed；超时、断线或没有完成信号不能按“没有工具调用”记为正确，评分器对 incomplete 单独拒绝。即使工具参数准确率达标，成功静默、回执解释和禁止伪执行仍须逐例审阅回复。合成用例单测不是线上模型成绩。

可加 `--raw-text` 做无前缀诊断，只发送用户原话；模拟前置状态经 get_status 回执暴露，不能冒充固定上下文测试的等价重跑。[只读诊断集](status-cases.json)显式提供合成 `fixture_status`，用于故障、缺少记录、过期距离和序列等待；该集独立审阅，不送入只支持固定 80／8 的评分器。

编排夹具对不支持的喷水／点火和非法步骤返回 `invalid_plan`，保留原稿；它不模拟完整固件的时间、租期、所有权或驱动。首轮夹具缺少此检查，历史结果原样保留并在[ct45 联调记录](lingxi-ct45-20261031.md)说明，不能把模拟接受当成固件通过。

实际运行结果、失败项及真人／设备边界见[ct45 联调记录](lingxi-ct45-20261031.md)。原始输出和凭据分开保存；公开交付前检查内容不含令牌、网络名称、设备私有配置或真人身份。

## 成功播报的来源

[四条原话的时序记录](evidence/ct45-turn-timing.json)分别覆盖前进、超限喷水、停止和状态查询。每条均先发出模拟工具回执，随后收到平台的 TTS 文本和音频，回执至首个音频包分别为 1228、1569、1765 和 1382 毫秒。前进和停止也有语音。捕获器丢弃全部音频，只记录字节数。此观察将多余确认定位到服务端返回的语音，无法进一步归因到服务内部的模型或合成环节。设备端如需抑制成功确认，应保留查询、限幅、拒绝及本地警报的声音。后续捕获另记中止的 TTS，不能把中止当作正常完成。

ct46 在远端音频进入解码队列前检查当前语音轮次。首批支持省略参数的「前进、后退、左转、右转、喷水、吹泡泡、停止、停下、全部停止」。必须匹配唯一工具、默认参数和先于 TTS 开始的成功回执。其他措辞、未收到识别文本、提前到达的语音、多工具、限幅及错误保留平台音频。断线、新输入和 TTS 结束清除标记。本地测距警报走独立路径。该候选影响扬声器播放，平台仍可能生成文字和音频，屏幕保留回复。真人口述与扬声器听感待验。

验证 ct46 候选时，先用该候选的 prepared 目录导出工具，再给捕获器加 `--ct46`。导出步骤同时编译主机状态解释器，读取合成快照并复用固件的 `StatusFacts`。模型看到的解释来自当前状态，捕获器不会把用例期望嵌入回执。

[ct46 原话迁移集](ct46-transfer-cases.json)在候选固件冻结后新增，包含短指令、超限喷水、含糊改稿、禁止通道和恢复条件。每条保留服务回传的识别文本、调用、回执、首个音频包和 TTS 边界。可在主机上重放一条捕获，复用候选固件实际的播放判断。以下命令在仓库根目录、已导出候选工具且安装 jq 的环境下运行。

```sh
c++ -std=c++17 -I "$HOME/esp/esp-idf/components/json/cJSON" \
  -I build/xiaozhi-ct46-final-src/main/boards/bread-compact-wifi \
  scripts/replay_lingxi_feedback.cc build/lingxi-schema-export/cJSON.o \
  -o build/lingxi-schema-export/replay-feedback
jq -c '.results[0]' output/voice/ct46-repeat/1-transfer.json | \
  build/lingxi-schema-export/replay-feedback
```

输出为首包被抑制、可播放或未收到首包。文本输入不能验证麦克风识别，主机回放也不能证明扬声器实际静默。固定 80 条带评测前缀，端侧会按真实识别文本处理，不能人为剥掉前缀再报告端到端静默率。

复测 ct47 时用 `build/xiaozhi-ct47-src` 导出 schema 并选择 `--ct47`。夹具和固件共用草稿能力描述及故障说明。ct46 的完整三轮记录与 ct47 的回执变更验证分别保存。

运行中语音与混合编排的[定向用例](ct48-running-cases.json)提供两种起始状态。使用 ct48 工具描述、`--ct47 --raw-text` 和该 corpus 捕获。前四条从“70% 前进、剩余 4 秒”的固定快照开始，其余从空闲开始。原话不附加状态前缀，模型可用只读工具查看夹具。全停回执清除活动方向、速度、逻辑输出、剩余时长和保持标识。

主机重放从相同初态开始，每条原话单独创建控制会话。使用冻结的主机时钟、无输出驱动和固件的 `Reply`、`ControlSessions`、`ParseShowEdit`，逐条处理捕获的查询、全停及改稿调用。最终再读一次状态，以核对运动、启动计数与实际保存的各步参数。其他工具超出本重放器覆盖范围，会被标为无法验证。按以下步骤运行，第二条命令接受 JSON 或 gzip 轨迹。

```sh
python3 firmware/esp32-audio/tests/run_mcp_tests.py --source build/xiaozhi-ct48-src
python3 scripts/replay_running_intents.py output/voice/ct48-running/1.json
```

对于运行中的四条用例，另按输入至工具调用及 TTS 结束的实际包间隔推进主机时钟，逐次核对截止时间、逻辑输出和启动计数。该计算验证受控时钟下的截止语义，现场调度延迟、电机惯性和机械停车距离仍需实测。平台在线时看到内存夹具回执，固件代码回读是捕获完成后的独立检查。

## 让平台收到随时间变化的只读回执

上面的固定快照适合比较动作意图。检验“还要走多久”时，使用 `--timed-host --raw-text` 和[采样时刻用例](status-timing-cases.json)。先按上一节编译主机回执程序。每次查询取输入已发出到该 RPC 到达的实测间隔，以 5 ms 步长推进受控时钟，用固件回执序列化代码生成查询结果，再通过同一条 WSS 会话返回。该模式只允许无参数的 `get_status`。其他调用照实记录并返回错误，不发送到执行器。原始轨迹保留主机程序、角色、用例、工具描述的哈希，以及查询、回复文本和首个音频包的时间点。

初态分别为 70% 前进且剩余 4000 ms 或 400 ms。长短对照可以区分“查询时还有计时”和“查询到达前计时已结束”。核对回复时分开检查方向是否带多余倒计时、剩余秒数是否与回执匹配并明确属于查询瞬间、是否对未来运动作出保证，以及到期后是否猜测停机原因。只读重放没有实物位移反馈。

## 用固件回执验证“只改第二步”

在仓库根目录用对应版本的 prepared 源码运行 `python3 firmware/esp32-audio/tests/run_mcp_tests.py --source build/xiaozhi-ct50-src`。它会在 `build/audio-host/` 生成 `receipt_replay`。将上文捕获命令的工具描述换成同版导出，语料换成 `docs/validation/compose-cases.json`，并附加以下参数。

```sh
--ids C002 --draft-host build/audio-host/receipt_replay
```

主机通过网页草稿接口建立版本 7，第一步左转 880 ms，第二步吹泡泡 1000 ms。虚拟网页每 200 ms 续约，仅保持草稿所属会话在线。灵矽实际发来的查询、停止和改稿按到达时刻及原顺序送入固件，每次收到的回执随后送回同一条平台会话。用于检查的末尾快照不会授权下一次改稿。轨迹中可分别检查版本、两步参数、动作启动次数和云端答复。固定集上下文会告诉模型初始版本，另加 `--raw-text` 才是只给用户原话的对照。

## 核对整段回复的播放策略

在捕获命令中加 `--audio-packets`，仅记录每个远端音频包的到达顺序、时刻和字节数，丢弃内容。用上文方法把 `scripts/replay_lingxi_feedback.cc` 和待测版本的 `voice_feedback.h` 编译在一起。将单条用例送给程序并加 `--packets`，得到抑制与可播放的包数。程序会核对逐包字节总数与捕获器的独立计数；只记录首包的历史文件不能用于全段判定。该输出衡量固件策略，现场扬声器听感需另外记录。

### 合成普通话上行

运行采集器时传入 `--synthetic-speech` 和口述集的用例 ID。macOS 的 Tingting 以每分钟 180 词合成用户原话，FFmpeg 将声音编码为 16 kHz 单声道 Opus。夹具依次发送手动监听开始、每帧 60 ms 的二进制包和监听结束。用例原文、前置状态和预期答案均不作为识别提示发送。工具只由隔离夹具应答。

每条记录保存编码参数、帧数、字节数、载荷摘要、平台转写、工具参数和回复文字。临时音频会随合成结束清除。回复音频仅计字节。转写与工具选择可以离线复核，麦克风、扬声器、环境噪声和机械动作仍需现场观察。

### 移动中与空闲时说“全速”

用 `run_mcp_tests.py --source` 先构建当前版本的主机回执程序。给合成语音采集命令增加 `--ids V040 --audio-packets --speed-host thirty_second_forward70` 或 `--speed-host idle`。前者从 70% 前进、原截止为第 30 秒开始，后者从零启动、全路关闭开始。计时从发送监听开始算起。两组仅向灵矽发送“全速”的声音，模型收到调用结果后才可能获知设备状态。

夹具每次按本会话已观察的调用与时刻重放固件调度和回执；只允许状态查询和绝对调速。空闲时固件不签发调速票据，平台收到与固件分发器相同的 JSON-RPC 错误。运行轨迹的 `initial_profile` 指定实际初态，`context` 是 V040 文本用例原有描述。音频包大小和顺序可用于离线对照不同版本的播放策略。

### 对照 RPC 错误与拒绝结果

仅为隔离实验时，可以在 `--speed-host` 基础上增加 `--admission-result-fixture`，将同一个主机拒绝包在 `result=rejected` 的工具结果里返回，包含原错误 `rejection_reason` 和 `physical_feedback=false`。轨迹另存原始错误，标记这是夹具转换。默认路径仍使用实际固件的 RPC 错误。两组使用相同的工具描述、角色与语音，结果不作为板上接口已修改的证据。

### 从空草稿验证保存回执

`--draft-host` 默认保留两步、版本 7 的网页草稿。新建场景可以同时指定 `--draft-profile empty_web_draft`，从无草稿、版本 0 开始。查询不会创建草稿，只有实际 `compose` 成功回执才保存版本 1。运行前用相同候选的 `run_mcp_tests.py` 构建主机回执程序，并固定其二进制。轨迹的 `initial_profile` 与 `host_replay_sha256` 标识所测初态和实现。

### 固定工具与角色，对照草稿状态说明

`--draft-read-facts-fixture` 为隔离对照增加 `draft_status_facts`，只影响状态查询回执。先将 `scripts/lingxi_status_fixture.cc` 与当前 `status_facts.h`、cJSON 编译到 `build/lingxi-schema-export/draft-read-fixture`。轨迹绑定帮助程序和头文件哈希。默认夹具保持原样，实际 ct59 主机回执直接包含该字段，无需实验开关。

说明按真实 `show_draft.active` 生成，只指出当前是否有草稿及查询不构成保存确认，不代替保存操作。对照组保持角色和十二个工具定义一致。
