import mermaid from "mermaid";

export async function renderDiagrams(diagrams) {
  mermaid.initialize({
    startOnLoad: false, securityLevel: "strict", suppressErrorRendering: true,
    theme: "neutral", htmlLabels: false,
  });
  for (const [index, source] of diagrams.entries()) {
    try {
      const { svg } = await mermaid.render(`flowchart-${index}`, source.textContent);
      const figure = document.createElement("figure");
      figure.className = "diagram";
      figure.innerHTML = svg;
      source.parentElement.replaceWith(figure);
    } catch (error) {
      // Keep readable diagram source when rendering fails.
      console.warn("无法渲染 Mermaid 图表", error);
    }
  }
}
