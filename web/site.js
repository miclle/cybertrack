const sidebar = document.querySelector(".sidebar");
const filter = sidebar.querySelector("input");
const groups = [...sidebar.querySelectorAll("details")];
const links = [...sidebar.querySelectorAll("nav a")];
const menu = document.querySelector(".menu");
const scrim = document.querySelector(".scrim");
const mobile = matchMedia("(max-width: 900px)");
const storageKey = "cybertrack-docs-sidebar";
let saved = {};
try {
  saved = JSON.parse(localStorage.getItem(storageKey)) || {};
} catch {
  // Navigation remains usable when storage is disabled.
}
for (const group of groups) {
  const current = group.querySelector('[aria-current="page"]');
  const key = group.dataset.group;
  if (current || key in saved) group.open = Boolean(current || saved[key]);
  group.addEventListener("toggle", () => {
    if (filter.value || group.open === saved[key]) return;
    saved[key] = group.open;
    try {
      localStorage.setItem(storageKey, JSON.stringify(saved));
    } catch {
      // The state can still be restored on this page after filtering.
    }
  });
}
sidebar.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest" });

function toggleMenu(open, refocus = true) {
  sidebar.classList.toggle("open", open);
  menu.setAttribute("aria-expanded", String(open));
  scrim.hidden = !open;
  if (open) filter.focus();
  else if (refocus && mobile.matches) menu.focus();
}

menu.addEventListener("click", () => toggleMenu(menu.getAttribute("aria-expanded") === "false"));
scrim.addEventListener("click", () => toggleMenu(false));
mobile.addEventListener("change", () => toggleMenu(false, false));

let beforeFilter;
filter.addEventListener("input", () => {
  const query = filter.value.trim().toLocaleLowerCase();
  if (query && !beforeFilter) beforeFilter = groups.map(group => group.open);
  for (const link of links) link.hidden = !link.textContent.toLocaleLowerCase().includes(query);
  for (const [index, group] of groups.entries()) {
    group.hidden = !group.querySelector("a:not([hidden])");
    if (query) group.open = !group.hidden;
    else if (beforeFilter) group.open = beforeFilter[index];
  }
  if (!query) beforeFilter = undefined;
  sidebar.querySelector(".no-results").hidden = links.some(link => !link.hidden);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && sidebar.classList.contains("open")) toggleMenu(false);
  if (event.key !== "/" || event.ctrlKey || event.altKey || event.metaKey ||
    event.target.closest("input, textarea, select, [contenteditable]")) return;
  event.preventDefault();
  if (mobile.matches) toggleMenu(true);
  else filter.focus();
});

const contents = document.querySelector(".on-page");
if (contents) {
  const headings = [...document.querySelectorAll(".prose h2[id], .prose h3[id]")];
  const toc = contents.querySelector("nav");
  for (const heading of headings) {
    const link = document.createElement("a");
    link.href = "#" + encodeURIComponent(heading.id);
    link.textContent = heading.textContent;
    if (heading.tagName === "H3") link.className = "subsection";
    toc.append(link);
  }
  contents.hidden = !headings.length;
}

const diagrams = document.querySelectorAll(".prose pre > .language-mermaid");
if (diagrams.length) {
  const { renderDiagrams } = await import("./diagrams.js");
  await renderDiagrams(diagrams);
}
