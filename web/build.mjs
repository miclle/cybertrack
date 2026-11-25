import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";
import { build } from "esbuild";
import GithubSlugger from "github-slugger";
import MarkdownIt from "markdown-it";
import sanitizeHtml from "sanitize-html";
import { branch, models, prototype, repository, sections } from "./catalog.mjs";

const web = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(web);
const output = path.join(root, "build");
const tracked = new Set(execFileSync("git", ["ls-files", "-z"], {
  cwd: root,
  encoding: "utf8",
}).split("\0").filter(Boolean));
const md = new MarkdownIt({ html: true });
const escape = md.utils.escapeHtml;
const read = file => fs.readFileSync(path.join(root, file), "utf8");
const urlPath = name => name.split("/").map(encodeURIComponent).join("/");
const relative = (from, to) => urlPath(path.posix.relative(path.posix.dirname(from), to));
const docPage = source => source.replace(/\.md$/, ".html");
const modelPage = model => `cad/${model.id}.html`;
const github = (source, kind = "blob") => `${repository}/${kind}/${branch}/${urlPath(source)}`;

const named = new Map(sections.flatMap(([, entries]) => entries));
const documents = new Map([
  ...[...tracked].filter(file => file.startsWith("docs/") && file.endsWith(".md") && fs.existsSync(path.join(root, file))),
  ...named.keys(),
].map(file => [file, named.get(file) ?? read(file).match(/^# +(.+)$/m)?.[1] ?? file]));
const other = [...documents].filter(([file]) => !named.has(file) && file !== "docs/README.md");
const navGroups = [
  ["三维模型", models.map(model => [modelPage(model), model.title])],
  ...sections.map(([title, entries]) => [title, entries.map(([file, label]) => [docPage(file), label])]),
  ...(other.length ? [["更多文档", other.map(([file, label]) => [docPage(file), label])]] : []),
];
const attachments = new Set([prototype]);

function shell(page, title, content, model = false) {
  const link = target => escape(relative(page, target));
  const navLink = (to, label) =>
    `<a href="${link(to)}"${to === page ? ' aria-current="page"' : ""}>${escape(label)}</a>`;
  const nav = navGroups.map(([label, entries]) => {
    const open = !["样机记录", "更多文档"].includes(label) || entries.some(([file]) => file === page);
    return `<details data-group="${escape(label)}"${open ? " open" : ""}><summary>${escape(label)}</summary>
      <div>${entries.map(([file, name]) => navLink(file, name)).join("")}</div></details>`;
  }).join("");

  return `<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#202326"><title>${escape(title)} · CyberTrack</title>
<link rel="icon" href="${link("assets/mark.svg")}" type="image/svg+xml">
<link rel="stylesheet" href="${link("assets/site.css")}">
</head><body>
<a class="skip" href="#main">跳至正文</a>
<header class="masthead">
  <button class="menu" aria-controls="sidebar" aria-expanded="false">目录</button>
  <a class="brand" href="${link("index.html")}"><span class="mark" aria-hidden="true"></span>CyberTrack</a>
  <nav aria-label="工作区">
    <a href="${link("docs/README.html")}"${!model && page !== "index.html" ? ' class="active"' : ""}>工程文档</a>
    <a href="${link(modelPage(models[0]))}"${model ? ' class="active"' : ""}>三维模型</a>
  </nav>
  <a class="repository" href="${repository}">GitHub</a>
</header>
<aside class="sidebar" id="sidebar">
  <label class="filter"><span class="sr-only">筛选目录</span><input type="search" placeholder="筛选目录"><kbd>/</kbd></label>
  <nav aria-label="资料目录">${navLink("index.html", "项目总览")}${nav}</nav>
  <p class="no-results" hidden>没有匹配的文档或模型</p>
</aside>
<button class="scrim" aria-label="关闭目录" hidden></button>
<main id="main" tabindex="-1"><div class="content">${content}</div></main>
<script type="module" src="${link("assets/site.js")}"></script>
${model ? `<script type="module" src="${link("assets/viewer.js")}"></script>` : ""}
</body></html>`;
}

function overview() {
  const cards = [
    ["docs/current-status.html", "当前状态", "核对固件、打印件与样机验证进度。"],
    ["docs/assembly.html", "装配与检修", "查看装配顺序、拆卸路径与维护入口。"],
    ["docs/architecture.html", "软件架构", "了解语音、局域网控制与设备端的分工。"],
    ["docs/wiring.html", "接线与供电", "核对供电分支、接口和接线表。"],
  ];
  return `<section class="hero">
    <div class="hero-copy">
      <p class="eyebrow">工程资料库</p>
      <h1>CyberTrack</h1>
      <p class="hero-description">双履带语音交互机器人</p>
      <p>从 FreeCAD 整机、打印与装配，到接线、固件和样机验证。</p>
      <div class="actions">
        <a class="button primary" href="${modelPage(models[0])}">查看 v2 整机</a>
        <a class="button secondary" href="docs/quick-start.html">样机上手</a>
      </div>
    </div>
    <figure class="hero-photo">
      <img src="${escape(urlPath(prototype))}" alt="CyberTrack 早期双履带样机的正面实拍" width="1200" height="900">
      <figcaption>早期样机 · 工作台实拍</figcaption>
    </figure>
  </section>
  <section class="overview-section"><div class="section-line"><h2>工程文档</h2><a href="docs/README.html">查看目录</a></div>
  <div class="doc-cards">${cards.map(([to, title, description]) =>
    `<a href="${to}"><h3>${title}</h3><p>${description}</p></a>`).join("")}</div></section>
  <section class="overview-section"><div class="section-line"><h2>三维模型</h2></div>
    <div class="model-list">${models.map(model => `<a href="${modelPage(model)}">
      <span class="file-type" aria-hidden="true">3D</span><div><h3>${model.title}</h3><p>${model.description}</p></div>
      <span class="file-name">${path.posix.basename(model.source)}</span></a>`).join("")}</div>
  </section>`;
}

function resolveAsset(source, value, image = false) {
  if (!value || /^(?:[\w+.-]+:|\/\/|#)/i.test(value)) return value;
  const parsed = new URL(value, `https://local.invalid/${urlPath(source)}`);
  const file = decodeURIComponent(parsed.pathname.slice(1));
  const suffix = parsed.search + parsed.hash;
  if (documents.has(file)) return relative(docPage(source), docPage(file)) + suffix;
  const model = models.find(item => item.source === file);
  if (model) return relative(docPage(source), modelPage(model)) + suffix;
  if (tracked.has(file) && fs.existsSync(path.join(root, file))
    && /\.(?:avif|gif|jpe?g|png|svg|webp|pdf)$/i.test(file)) {
    attachments.add(file);
    return relative(docPage(source), file) + suffix;
  }
  if (image) return `https://raw.githubusercontent.com/miclle/cybertrack/${branch}/${urlPath(file)}${suffix}`;
  const directory = file.replace(/\/$/, "");
  const isDirectory = [...tracked].some(trackedFile => trackedFile.startsWith(directory + "/"));
  return github(file, isDirectory ? "tree" : "blob") + suffix;
}

function renderedDocument(source, title) {
  const slugger = new GithubSlugger();
  const tokens = md.parse(read(source), {});
  for (let index = 0; index < tokens.length; index++) {
    const token = tokens[index];
    if (token.type === "heading_open") {
      token.attrSet("id", slugger.slug(tokens[index + 1].children.map(child => child.content).join("")));
    }
  }
  const html = sanitizeHtml(md.renderer.render(tokens, md.options, {}), {
    allowedTags: [...sanitizeHtml.defaults.allowedTags, "img", "details", "summary", "sub", "sup", "del", "kbd"],
    allowedAttributes: {
      ...sanitizeHtml.defaults.allowedAttributes,
      a: ["href", "id", "name", "title"], img: ["src", "alt", "title", "width", "height", "loading"],
      th: ["width", "style"], td: ["width", "style"], code: ["class"],
      h1: ["id"], h2: ["id"], h3: ["id"], h4: ["id"], h5: ["id"], h6: ["id"],
    },
    allowedStyles: { "*": { "text-align": [/^(left|right|center)$/] } },
    transformTags: {
      a: (tagName, attrs) => ({
        tagName, attribs: attrs.href ? { ...attrs, href: resolveAsset(source, attrs.href) } : attrs,
      }),
      img: (tagName, attrs) => ({
        tagName, attribs: { ...attrs, src: resolveAsset(source, attrs.src, true), loading: "lazy" },
      }),
    },
  });
  return `<div class="doc-layout"><article class="prose" aria-label="${escape(title)}">${html}
    <footer><a href="${github(source)}">在 GitHub 查看 Markdown</a></footer></article>
    <aside class="on-page" aria-label="本页目录" hidden><strong>本页目录</strong><nav></nav></aside></div>`;
}

function modelView(model, asset) {
  const page = modelPage(model);
  return `<header class="model-title">
    <div><p class="eyebrow">三维模型</p><h1>${escape(model.title)}</h1>
    <p>${escape(model.description)}</p></div>
    <div class="actions"><a class="button secondary" href="${relative(page, docPage(model.document))}">设计说明</a>
    <a class="button secondary" href="${github(model.source)}">FreeCAD 源档</a></div>
  </header>
  <section class="viewer" data-model="${relative(page, asset)}" aria-label="三维装配查看器">
    <div class="toolbar">
      <button type="button" id="tree-toggle" aria-controls="part-tree" aria-expanded="false" disabled>零件树</button>
      <label>视角 <select id="orientation" disabled>
        <option value="iso">等轴测</option><option value="front">正视</option>
        <option value="top">俯视</option><option value="right">右视</option>
        <option value="custom" hidden>自由视角</option>
      </select></label>
      <button type="button" id="fit" disabled>适应视图</button>
    </div>
    <div class="workspace">
      <aside id="part-tree" aria-label="零件树" hidden>
        <label class="sr-only" for="part-filter">筛选零件</label>
        <input id="part-filter" type="search" placeholder="筛选零件">
        <div class="parts"></div><p id="no-parts" hidden>没有匹配的零件</p>
      </aside>
      <div class="viewport">
        <div id="canvas-holder"></div><div id="model-status" role="status">正在载入模型…</div>
        <output id="selection" hidden></output>
        <noscript><p>启用 JavaScript 后可查看模型。</p></noscript>
      </div>
    </div>
    <div class="explosion"><label for="explosion">爆炸图</label>
      <input type="range" id="explosion" min="0" max="100" value="0" disabled>
      <output id="amount" for="explosion">0%</output>
      <button type="button" id="reset" disabled>复位</button>
    </div>
  </section>
  <p class="view-help">拖动旋转 · 滚轮或双指缩放 · 右键或双指平移 · 点击零件查看名称</p>
  <p class="view-help">爆炸图按零件位置展开。实际拆装顺序见设计说明。</p>`;
}

const sha256 = file => createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const exporter = path.join(root, "scripts/export_web_model.py");
const exporterHash = sha256(exporter);
const materialReaderHash = sha256(path.join(root, "scripts/cad_gui_state.py"));
const bundledPython = "/Applications/FreeCAD.app/Contents/Resources/bin/python";

function readModel(file, fingerprint) {
  if (!fs.existsSync(file)) return null;
  const bytes = fs.readFileSync(file);
  try {
    const glb = gunzipSync(bytes);
    if (glb.toString("ascii", 0, 4) !== "glTF" || glb.readUInt32LE(8) !== glb.length) return null;
    const { asset, meshes } = JSON.parse(glb.toString("utf8", 20, 20 + glb.readUInt32LE(12)));
    if (meshes.length && asset.extras.sourceSha256 === fingerprint && asset.extras.exporterSha256 === exporterHash
        && asset.extras.materialReaderSha256 === materialReaderHash) {
      return bytes;
    }
  } catch {
    // A corrupt cache is regenerated from the FreeCAD source.
  }
  return null;
}

function stageModel(model, write) {
  const source = path.join(root, model.source);
  const fingerprint = sha256(source);
  const cache = path.join(output, "web-models", `${model.id}.glb.gz`);
  let bytes = readModel(cache, fingerprint);
  if (!bytes) {
    const python = process.env.FREECAD_PYTHON || (fs.existsSync(bundledPython) ? bundledPython : "python3");
    try {
      execFileSync(python, [exporter, source, cache], { cwd: root, stdio: "inherit" });
    } catch (cause) {
      throw new Error(`无法导出 ${model.source}。请确认 FREECAD_PYTHON 指向可导入 FreeCAD 的 Python。`, { cause });
    }
    bytes = readModel(cache, fingerprint);
    if (!bytes) throw new Error(`导出文件校验失败：${model.source}`);
  }
  const hash = createHash("sha256").update(bytes).digest("hex").slice(0, 16);
  const asset = `assets/models/${model.id}-${hash}.glb.gz`;
  write(asset, bytes);
  return asset;
}

fs.mkdirSync(output, { recursive: true });
const stage = fs.mkdtempSync(path.join(output, "web-staging-"));
const destination = path.join(output, "web");
const next = path.join(stage, "next");
const previous = path.join(stage, "previous");
function write(file, contents) {
  const target = path.join(next, file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, contents);
}

try {
  write("index.html", shell("index.html", "项目总览", overview()));
  for (const [source, title] of documents) {
    const page = docPage(source);
    write(page, shell(page, title, renderedDocument(source, title)));
  }
  for (const model of models) {
    const asset = stageModel(model, write);
    write(modelPage(model), shell(modelPage(model), model.title, modelView(model, asset), true));
  }
  for (const file of attachments) write(file, fs.readFileSync(path.join(root, file)));
  write("assets/site.css", read("web/site.css"));
  write("assets/mark.svg", read("web/mark.svg"));
  fs.copyFileSync(path.join(root, "LICENSE"), path.join(next, "LICENSE"));
  await build({
    absWorkingDir: web, entryPoints: ["site.js", "viewer.js"], outdir: path.join(next, "assets"),
    bundle: true, splitting: true, minify: true, format: "esm", target: ["es2022"],
    chunkNames: "chunks/[name]-[hash]", legalComments: "linked",
  });
  if (fs.existsSync(destination)) fs.renameSync(destination, previous);
  try {
    fs.renameSync(next, destination);
  } catch (error) {
    if (fs.existsSync(previous)) fs.renameSync(previous, destination);
    throw error;
  }
  console.log(`已生成 ${documents.size} 篇文档和 ${models.length} 个三维模型 → ${destination}`);
} finally {
  fs.rmSync(stage, { recursive: true, force: true });
}
