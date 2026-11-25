"""Bounded, read-only browser snapshot; no page source or user-entered values."""
SNAPSHOT_JS = r"""
(options) => {
  const props = [
    'display','position','z-index','box-sizing','overflow-x','overflow-y',
    'width','height','min-width','max-width','min-height','max-height',
    'margin-top','margin-right','margin-bottom','margin-left',
    'padding-top','padding-right','padding-bottom','padding-left',
    'gap','row-gap','column-gap','flex-direction','flex-wrap','flex-grow',
    'align-items','justify-content','grid-template-columns','grid-template-rows',
    'border-top-width','border-right-width','border-bottom-width','border-left-width',
    'border-top-color','border-right-color','border-bottom-color','border-left-color',
    'border-top-style','border-radius','box-shadow','opacity','transform',
    'color','background-color','background-image','font-family','font-size',
    'font-weight','font-style','line-height','letter-spacing','text-align',
    'text-transform','text-decoration-line','white-space','object-fit',
    'transition-property','transition-duration','transition-delay',
    'transition-timing-function','animation-name','animation-duration',
    'animation-delay','animation-timing-function','animation-iteration-count'
  ];
  const clip = (v,n=240) => String(v ?? '').slice(0,n);
  const round = n => Math.round(n*100)/100;
  const selector = el => {
    const parts = [];
    for (let n=el; n && n.nodeType===1 && parts.length<24; n=n.parentElement) {
      let pos=1;
      for(let s=n.previousElementSibling;s;s=s.previousElementSibling)
        if(s.localName===n.localName) pos++;
      parts.unshift(CSS.escape(n.localName)+':nth-of-type('+pos+')');
    }
    return parts.join(' > ');
  };
  const rows=[], candidates=[];
  const walker=document.createTreeWalker(document.documentElement,NodeFilter.SHOW_ELEMENT);
  let el=walker.currentNode, visited=0;
  while(el && visited<3000 && rows.length<350) {
    visited++;
    const b=el.getBoundingClientRect(), s=getComputedStyle(el);
    if(b.width>0 && b.height>0 && s.display!=='none' && s.visibility!=='hidden' && s.opacity!=='0') {
      const sel=selector(el);
      const style={};
      if(options.measurements) for(const key of props) style[key]=clip(s.getPropertyValue(key));
      const row={selector:sel,tag:el.localName,role:clip(el.getAttribute('role'),80),
        rect:{x:round(b.x+scrollX),y:round(b.y+scrollY),width:round(b.width),height:round(b.height)},style};
      rows.push(row);
      if(options.interactions && candidates.length<12 &&
        el.matches('a[href],button,[role="button"],[aria-expanded],summary') &&
        b.top>=0 && b.left>=0 && b.bottom<=innerHeight && b.right<=innerWidth &&
        !el.matches(':disabled,[aria-disabled="true"]')) {
        candidates.push({selector:sel,tag:el.localName,role:row.role,
          expanded:el.getAttribute('aria-expanded'),has_popup:el.getAttribute('aria-haspopup')});
      }
    }
    el=walker.nextNode();
  }
  const media=[], keyframes=[], visitedSheets=new Set();
  let cssRules=0, inaccessible=0, truncatedRules=false;
  function walkRules(rules,depth=0) {
    if(depth>8) return;
    for(const rule of rules) {
      if(++cssRules>3000) {truncatedRules=true;return;}
      if(rule.type===CSSRule.MEDIA_RULE && media.length<100) {
        let matches=null;try {matches=matchMedia(rule.conditionText).matches;}catch{}
        media.push({condition:clip(rule.conditionText),matches});
      }
      if(rule.type===CSSRule.KEYFRAMES_RULE && keyframes.length<60) {
        keyframes.push({name:clip(rule.name,100),frames:Array.from(rule.cssRules).slice(0,20).map(frame=>({
          offset:clip(frame.keyText,100),
          style:Object.fromEntries(Array.from(frame.style).slice(0,30).map(key=>[key,clip(frame.style.getPropertyValue(key))]))
        }))});
      }
      if(rule.type===CSSRule.IMPORT_RULE && rule.styleSheet) walkSheet(rule.styleSheet,depth+1);
      else if(rule.cssRules && rule.type!==CSSRule.KEYFRAMES_RULE) walkRules(rule.cssRules,depth+1);
    }
  }
  function walkSheet(sheet,depth=0) {
    if(depth>8 || visitedSheets.has(sheet) || cssRules>=3000) return;
    visitedSheets.add(sheet);
    try {walkRules(sheet.cssRules,depth);} catch {inaccessible++;}
  }
  if(options.measurements) for(const sheet of Array.from(document.styleSheets).slice(0,100)) walkSheet(sheet);
  const animations=options.measurements ? document.getAnimations().slice(0,60).map(a=>{
    const timing=a.effect?.getTiming();
    const numeric=v=>typeof v==='number' && Number.isFinite(v)?v:null;
    return {name:clip(a.animationName||a.transitionProperty||a.id,100),play_state:a.playState,
      current_time:numeric(a.currentTime),duration:numeric(timing?.duration),delay:numeric(timing?.delay),
      iterations:numeric(timing?.iterations),easing:clip(timing?.easing),infinite:timing?.iterations===Infinity,
      target:a.effect?.target instanceof Element?selector(a.effect.target):null};
  }):[];
  return {viewport:{width:innerWidth,height:innerHeight,device_pixel_ratio:devicePixelRatio,
      document_width:document.documentElement.scrollWidth,document_height:document.documentElement.scrollHeight,
      hover:matchMedia('(hover: hover)').matches},
    elements:options.measurements?rows:[], candidates, media_queries:media, keyframes, animations,
    limits:{visited_elements:visited,visible_sample:rows.length,dom_truncated:!!el,
      css_rules:Math.min(cssRules,3000),css_truncated:truncatedRules,inaccessible_stylesheets:inaccessible,
      stylesheet_limit:document.styleSheets.length>100}};
}
"""


def measure(page, measurements=True, interactions=True):
    return page.evaluate(SNAPSHOT_JS, {"measurements": measurements, "interactions": interactions})
