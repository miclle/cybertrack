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

捕获循环只读取 ID、原话和前置状态，丢弃 `expected_calls` 与 `response_expectation`。模拟状态覆盖空闲、70% 前进及已有两步草稿；模拟动作接受仅用于观察后续回复，不证明参数被真实固件接受。模拟编排回执按实际捕获参数计算，不复制期望答案。模型原始调用与 TTS 文本均保留。

每例必须收到 TTS stop 才标记 completed；超时、断线或没有完成信号不能按“没有工具调用”记为正确，评分器对 incomplete 单独拒绝。即使工具参数准确率达标，成功静默、回执解释和禁止伪执行仍须逐例审阅回复。合成用例单测不是线上模型成绩。

实际运行结果、失败项及真人／设备边界另存带日期的验证记录。原始输出和凭据分开保存；公开交付前检查内容不含令牌、网络名称、设备私有配置或真人身份。
