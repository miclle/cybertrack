# 灵矽联调反馈：过程文字进入语音及含糊改稿

本页是供维护方复核的技术材料，尚未代发或创建外部工单。它记录设备协议边界的现象，不断定模型或平台内部的具体成因。

## 场景和环境

亲子泡泡表演已有两步草稿，版本 7：左转 880 ms，然后吹泡泡 1000 ms。用户说“第二步短一点”，没有提供新时长；角色要求只追问具体几秒，不猜半秒或减半。预期不查询、不修改、不启动，草稿保持原样。

本轮两组使用相同的十二项公开工具、实际 ct66 MCP／控制主机和原话输入。平台显示 `deepseek-v4-flash`，统一意图识别，温度 0.7、Top P 1、频率惩罚 0、回复长度 500、thinking disabled、reasoning_effort low、usage 开启。基线角色 5991 字符，另一组仅在状态段增加六字。保存、重开及最终恢复均逐字核对；模型标签不是独立的模型身份确认。

统一模式使用同一模型处理意图和聊天；分离模式是另一种配置，官方指引标为不再推荐。本轮没有改动意图模式、默认插件或模型参数。[官方配置指引](https://linx.qiniu.com/docs/xrobot/guide/agent-config#_5-1-意图识别)

## 可直接核对的现象

[十四次对照](stop-role-qualifier.md)的两条 C008 都收到英文和规则分析文字。这些文字来自 `tts/sentence_start`，并伴随远端音频包；设备没有实际播放，因此不是扬声器听感结论。

| 基线 C008 事件 | 相对连接建立的毫秒 |
|---|---:|
| 请求 get_status | 1679 |
| 回执已发送 | 1683 |
| 首个 TTS 语句，开头为“Let me check” | 1871 |
| 收到首个音频包 | 1903 |
| 请求 compose，擅自将第二步设为 500 ms | 4124 |
| 实际回执接受改稿 | 4128 |
| 会话正常结束 | 25096 |

基线的草稿因此 7→8，但没有启动；后续语句又承认擅自修改并追问时长。另一组没有提交 compose，草稿保持 7，仍在查询后通过 TTS 输出英文操作说明及规则分析。两者分别说明：

- 过程播报可以出现在没有实际改稿的会话中，不能只靠等待保存回执解决。
- 格式正确、版本有效的改稿仍可能误解含糊输入；设备失败隔离不能拦住第一个被接受的误改。
- 三条停止在两组中都直接调用 stop，随后仍有确认文字。不能以“思考开关已关闭”或三个字的减少宣称静默成功。

数据见[基线编排轨迹](evidence/stop-role-qualifier/baseline-compose.json.gz)、[候选编排轨迹](evidence/stop-role-qualifier/candidate-compose.json.gz)和[完整审阅](evidence/stop-role-qualifier/review.json)。每条只采一次、两组分时运行，不保证下一次必现，不据此估计总体发生率。

## 复核方式

先在完整 checkout 阅读保存的轨迹；无需账号即可重算原回执，但需要本轮摘要一致的固定主机：

```sh
python3 scripts/review_stop_role_qualifier.py \
  --directory docs/validation/evidence/stop-role-qualifier \
  --executable /path/to/ct66/firmware_host
```

需要新采集时，按[隔离联调入口](lingxi-capture.md)准备依赖、私有认证、工具导出与主机，然后在授权平台环境运行以下单例。路径需换成自己的文件；不向机器人转发工具，不把认证配置提交到仓库。

```sh
build/lingxi-capture-venv/bin/python scripts/capture_lingxi.py \
  --connection /path/to/private-connection.json \
  --tools /path/to/exported-tools.json \
  --role firmware/esp32-audio/role-prompt.txt \
  --model deepseek-v4-flash --raw-text --audio-packets \
  --corpus docs/validation/compose-cases.json --ids C008 \
  --firmware-host /path/to/ct66/firmware_host \
  --timeout 55 --output output/tts-feedback-C008.json
```

检查工具调用、完整回执、草稿终态、TTS 语句与音频事件；新结果单独保存，不覆盖本页失败。仓库角色和平台保存内容须先核对，命令中的角色文件用于记录哈希，不会代替平台同步。

## 希望平台协助确认

1. 工具调用中间轮的普通内容，是否会直接进入 TTS；是否存在可配置的最终播报出口。公开设备事件不足以区分内部推理、普通内容或模板来源。
2. 能否在服务端区分操作过程与用户最终回复，并保留轮次／阶段关联以便追踪；这是接口建议，当前固件没有获得此类阶段字段。
3. 在支持的模型组合下，如何同时做到动作成功静默、拒绝／故障／限幅正常播报，以及含糊请求只追问。

不建议设备通过英文、关键词或整段静音过滤全部回复，这会掩盖有效追问、拒绝和故障。云端播报策略也不能延迟本地全停，或替代参数、版本与输出守卫。设备侧将另行研究相对时长改稿的准入，不能声称已理解任意自然语言。

## 共同验收出口

保持原角色、工具和语料的可追溯版本。C008 不查询／不改稿，只追问秒数；明确时长和方向替换、取消草稿、直接动作与停止继续正确。固定语义按原门槛核对准确率、禁止调用和八条明确停止，编排与回复语义分别审阅。录下 TTS 语句及音频的时序，确认没有操作前旁白，也不丢失真实拒绝与澄清。

当前只是可复核的反馈材料；未取得平台修复、设备部署、真人语音或家庭验收结果。

ct67 后续的[二十条真实 STT 定向会话](relative-draft-duration.md)进一步确认：合成语音经实际转写后，仍有英文及规则分析进入 TTS；所以现象也存在于这一语音入口。设备新增有限的无量化相对请求门禁，十三组原生拦截回放通过，但本批在线相对输入都只查询，不能据此宣称实时拦截过模型误改。原有反馈未因此关闭，材料仍未代发。
