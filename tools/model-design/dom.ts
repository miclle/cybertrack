interface Elements {
  'comment-popover': HTMLElement;
  'close-comment': HTMLButtonElement;
  'resume-comment': HTMLButtonElement;
  'draft-status': HTMLElement;
  'interaction-hint': HTMLElement;
  'history-panel': HTMLElement;
  'details-panel': HTMLElement;
  'toggle-history': HTMLButtonElement;
  'toggle-details': HTMLButtonElement;
  'close-history': HTMLButtonElement;
  'close-details': HTMLButtonElement;
  'model-title': HTMLElement;
  'model-info': HTMLElement;
  'reset': HTMLButtonElement;
  'viewport': HTMLElement;
  'model-canvas': HTMLCanvasElement;
  'empty-model': HTMLElement;
  'webgl-error': HTMLElement;
  'pick-label': HTMLElement;
  'render-status': HTMLElement;
  'geometry-result': HTMLElement;
  'parts': HTMLElement;
  'pick-type': HTMLElement;
  'selection-hint': HTMLElement;
  'selection-info': HTMLElement;
  'part-name': HTMLElement;
  'selection-fields': HTMLElement;
  'comment': HTMLTextAreaElement;
  'submit': HTMLButtonElement;
  'status': HTMLElement;
  'export-revision': HTMLSelectElement;
  'export-part': HTMLSelectElement;
  'export-step': HTMLButtonElement;
  'export-hint': HTMLElement;
  'export-status': HTMLElement;
  'undo': HTMLButtonElement;
  'history-count': HTMLElement;
  'history-status': HTMLElement;
  'history-empty': HTMLElement;
  'history-list': HTMLElement;
  'comment-section': HTMLElement;
  'comment-count': HTMLElement;
  'empty-comments': HTMLElement;
  'comments': HTMLElement;
}
// IDs and element types belong to index.html, shared by browser and embedded builds.
export function element<K extends keyof Elements>(id: K): Elements[K] {
  const value=document.getElementById(id);
  if (!value) throw new Error(`缺少界面元素：${id}`);
  return value as Elements[K];
}
