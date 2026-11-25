export const repository = "https://github.com/miclle/cybertrack";
export const branch = "v2";
export const prototype = "artifact/previews/27-prototype-front-workbench.jpg";

export const models = [
  {
    id: "cybertrack",
    title: "CyberTrack v2 整机",
    description: "查看 A1 主板对应的头舱、底盘与双瓶背包装配。",
    source: "hardware/model/CyberTrack.FCStd",
    document: "hardware/model/README.md",
  },
];

export const sections = [
  ["项目", [
    ["docs/current-status.md", "当前状态"],
    ["docs/quick-start.md", "样机上手"],
    ["docs/requirements.md", "产品需求"],
    ["docs/decisions.md", "设计决策"],
    ["docs/TODO.md", "项目待办"],
    ["docs/references.md", "技术资料索引"],
    ["docs/lingxi-solution.md", "灵矽方案"],
  ]],
  ["机械与电气", [
    [models[0].document, "整机 CAD 说明"],
    ["docs/assembly.md", "打印与装配"],
    ["docs/head-shell-print.md", "头壳打印"],
    ["docs/wiring.md", "接线表"],
    ["hardware/BOM.md", "物料清单"],
    ["docs/schematic-and-pcb.md", "原理图与制板"],
    ["hardware/architecture/README.md", "供电与接口"],
    ["hardware/pcb/README.md", "定制主板与 A1 接口"],
    ["hardware/pcb/camera-revision/README.md", "A2 前摄接口"],
    ["hardware/pcb/motion-feedback/README.md", "A3 编码器与 IMU"],
    ["hardware/model/studies/a3-harness/README.md", "A3 线束与颈部改件"],
    ["hardware/model/lean-print/README.md", "Lean 打印排盘"],
  ]],
  ["交互与固件", [
    ["docs/architecture.md", "软件架构"],
    ["docs/lan-control.md", "手机控制"],
    ["docs/wifi-configuration.md", "Wi-Fi 配置"],
    ["docs/agent-role.md", "语音角色"],
    ["docs/action-sequences.md", "动作序列"],
    ["docs/status-explanation.md", "状态与故障解释"],
    ["docs/effects-control.md", "喷水与泡泡"],
    ["docs/ultrasonic-ranging.md", "测距与前进保护"],
    ["firmware/README.md", "固件工程"],
    ["firmware/CAPABILITIES.md", "设备接口"],
    ["firmware/esp32-audio/README.md", "A1 与面包板固件"],
  ]],
  ["验证", [
    ["docs/verification-plan.md", "验收矩阵"],
    ["docs/validation/README.md", "验证记录索引"],
    ["docs/validation/firmware-host.md", "固件主机验证"],
    ["docs/validation/lingxi-capture.md", "语音联调"],
    ["docs/validation/nvs-config-review.md", "部署配置核对"],
    ["docs/validation/stop-trials.md", "停止测试"],
    ["docs/validation/engineering-log.md", "工程修改记录"],
  ]],
  ["样机记录", [
    ["hardware/schematic/README.md", "旧面包板原理图"],
    ["docs/validation/bench.md", "台架实测"],
    ["docs/validation/ct73-deployment.md", "首次行走与 BOOT 停止"],
    ["docs/validation/ct74-deployment.md", "测距提示听感"],
    ["docs/validation/ct78-deployment.md", "ct78 部署记录"],
    ["docs/validation/ct78-stop-duration.md", "ct78 语音失败与复测"],
  ]],
];
