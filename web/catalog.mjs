export const repository = "https://github.com/miclle/cybertrack";
export const branch = "v2";
export const prototype = "artifact/previews/27-prototype-front-workbench.jpg";

export const models = [
  {
    id: "cybertrack",
    title: "CyberTrack v2 整机",
    description: "查看双履带、头舱、底盘与双瓶背包的装配关系。",
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
  ]],
  ["机械与电气", [
    [models[0].document, "整机 CAD 说明"],
    ["docs/assembly.md", "打印与装配"],
    ["docs/head-shell-print.md", "头壳打印"],
    ["docs/wiring.md", "接线表"],
    ["hardware/BOM.md", "物料清单"],
    ["docs/schematic-and-pcb.md", "原理图与制板"],
  ]],
  ["交互与固件", [
    ["docs/architecture.md", "软件架构"],
    ["docs/lan-control.md", "手机控制"],
    ["docs/wifi-configuration.md", "Wi-Fi 配置"],
    ["docs/agent-role.md", "语音角色"],
    ["docs/action-sequences.md", "动作序列"],
  ]],
  ["验证", [
    ["docs/verification-plan.md", "验收矩阵"],
    ["docs/validation/README.md", "验证记录索引"],
  ]],
];
