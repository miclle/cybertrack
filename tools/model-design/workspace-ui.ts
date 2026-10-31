import { element as $ } from './dom.js';

type Panel = 'history' | 'details';
let opened: Panel | null = null;
let anchor: [number, number] = [24, 100];
export function closePanels(): void {
  for (const name of ['history','details'] as const) {
    $(name+'-panel' as 'history-panel'|'details-panel').hidden=true;
    $('toggle-'+name as 'toggle-history'|'toggle-details').setAttribute('aria-expanded','false');
  }
  opened=null;
}
export function openPanel(name: Panel): void {
  closeComment(); closePanels(); opened=name;
  $(name+'-panel' as 'history-panel'|'details-panel').hidden=false;
  $('toggle-'+name as 'toggle-history'|'toggle-details').setAttribute('aria-expanded','true');
  $('close-'+name as 'close-history'|'close-details').focus();
}
export function positionComment(): void {
  const box=$('comment-popover'), viewport=$('viewport');
  if(box.hidden) return;
  const width=viewport.clientWidth, height=viewport.clientHeight;
  const x=Math.max(12,Math.min(anchor[0]+16,width-box.offsetWidth-12));
  const toolbar=document.querySelector('header')!.getBoundingClientRect();
  const top=toolbar.bottom-viewport.getBoundingClientRect().top+10;
  const y=Math.max(top,Math.min(anchor[1]+12,height-box.offsetHeight-50));
  box.style.left=x+'px';box.style.top=y+'px';
}
export function openComment(point?: [number,number]): void {
  if(point) anchor=point;
  closePanels();
  $('comment-popover').hidden=false;
  $('resume-comment').hidden=true;
  positionComment();
  $('comment').focus({preventScroll:true});
}
export function closeComment(): void {
  $('comment-popover').hidden=true;
  $('resume-comment').hidden=!$('comment').value && $('selection-info').hidden;
}
export function setupWorkspace(): void {
  for(const name of ['history','details'] as const) {
    $('toggle-'+name as 'toggle-history'|'toggle-details').addEventListener('click',()=>{
      if(opened===name) closePanels();else openPanel(name);
    });
    $('close-'+name as 'close-history'|'close-details').addEventListener('click',()=>{
      closePanels();$('toggle-'+name as 'toggle-history'|'toggle-details').focus();
    });
  }
  $('close-comment').addEventListener('click',()=>{closeComment();$('model-canvas').focus();});
  $('resume-comment').addEventListener('click',()=>openComment());
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape') {
      if(opened) {
        const panel=opened;closePanels();$('toggle-'+panel as 'toggle-history'|'toggle-details').focus();
      } else {closeComment();$('model-canvas').focus();}
    }
    if((event.metaKey || event.ctrlKey) && event.key==='Enter' && event.target===$('comment')) {
      event.preventDefault();$('submit').click();
    }
  });
  $('history-list').addEventListener('click',event=>{
    const link=(event.target as HTMLElement).closest('a');
    if(link?.hash.startsWith('#comment-')) {
      const target=document.getElementById(link.hash.slice(1));
      if(target) {event.preventDefault();target.scrollIntoView({block:'nearest'});}
    }
  });
  new ResizeObserver(positionComment).observe($('comment-popover'));
  new ResizeObserver(positionComment).observe($('viewport'));
}
