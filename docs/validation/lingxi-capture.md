# 灵矽隔离语音与文本联调

测试使用已授权绑定的灵矽会话和无执行器的固件主机。文本输入可检查模型调用，合成普通话可另查平台转写。真人拾音、现场播报和机械动作各自记录。

## 准备工具与角色

在仓库根目录从与候选相同的 prepared 源码导出工具。ct79 应得到九个机器人业务工具。

```sh
python3 scripts/export_lingxi_tools.py --source build/xiaozhi-ct79-src --output build/ct79-private/tool-schemas.json
```

按[角色维护流程](../agent-role.md)记录仓库与平台实际角色哈希、平台可见模型名称和固件版本。ct79 尚待配套部署与角色同步。连接文件保存在 Git 忽略目录，权限为 `0600`，包含 `token`、`device_id` 和 `client_id`。

## 采集与判读

在没有设备语音会话时使用 `scripts/capture_lingxi.py`，依赖 `websockets==15.0.1`。用 `--tools`、`--role`、`--corpus`、`--model`、`--connection` 和 `--output` 指定本轮输入和独立输出路径。用例按[语音回归清单](../agent-role.md#语音回归清单)选择，记录初始状态。需要实际固件回执时传入[已构建的主机程序](firmware-host.md)作为 `--firmware-host`。

用 `--raw-text` 仅发送原话；用 `--synthetic-speech` 发送合成普通话，并以平台实际返回的 STT 事件判读。逐条核对转写、调用及顺序、回执、终态和回复。漏掉否定尾句、未经请求启动或漏停都要保留原样；超时单列。音频包只记录时序与字节数。ct78 两项待复测失败见[停止与时长记录](ct78-stop-duration.md)。
