"""Bounded asset inventory, without downloading or redistributing source bytes."""
from urllib.parse import urlsplit, urlunsplit

ASSET_JS = r"""
() => {
  const found=[];
  let truncated=false;
  function add(kind,url,detail='') {
    if(found.length>=500) {truncated=true;return;}
    found.push({kind,url:String(url||'').slice(0,2048),detail:String(detail).slice(0,200)});
  }
  const nodes=document.querySelectorAll('img,video,audio,source,svg,link[rel~="icon"],link[rel="stylesheet"]');
  for(const el of Array.from(nodes).slice(0,500)) {
    if(el.localName==='svg') add('inline-svg','', 'DOM SVG; markup not copied');
    else if(el.localName==='link') add(el.rel.includes('icon')?'icon':'stylesheet',el.href);
    else add(el.localName==='img'?'image':'media',el.currentSrc||el.src||el.getAttribute('src'),el.localName);
    if(el.localName==='video' && el.poster) add('image',el.poster,'poster');
  }
  const resourceEntries=performance.getEntriesByType('resource');
  for(const entry of resourceEntries.slice(0,500)) {
    if(['img','image','css','link','video','audio'].includes(entry.initiatorType) ||
       /\.(woff2?|ttf|otf|svg|png|jpe?g|webp|avif|gif|ico)(?:[?#]|$)/i.test(entry.name))
      add('network-resource',entry.name,entry.initiatorType);
  }
  const all=document.querySelectorAll('*');
  for(const el of Array.from(all).slice(0,500)) {
    const bg=getComputedStyle(el).backgroundImage;
    for(const match of bg.matchAll(/url\(["']?(.*?)["']?\)/g)) add('background-image',match[1]);
  }
  for(const font of Array.from(document.fonts||[]).slice(0,100))
    add('font-face','', [font.family,font.weight,font.style,font.status].join(' / '));
  return {items:found,truncated:truncated||nodes.length>500||all.length>500||resourceEntries.length>500};
}
"""


def safe_source(value):
    """Remove query, fragment and credentials; never retain inline payloads."""
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            return None
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except (ValueError, TypeError):
        return None


def inventory(page, url, viewport):
    raw = page.evaluate(ASSET_JS)
    rows = []
    seen = set()
    for item in raw["items"][:500]:
        kind = item["kind"]
        source = safe_source(item["url"])
        detail = item["detail"] if kind in ("font-face", "inline-svg") else ""
        key = (kind, source, detail)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"kind": kind, "source": source, "detail": detail,
                     "license": "unknown", "redistribution": "not_authorized",
                     "downloaded": False, "sha256": None})
    return {"url": safe_source(url), "viewport": viewport, "items": rows, "truncated": raw["truncated"]}


def combine(reports):
    unique = {}
    for report in reports:
        for item in report["items"]:
            key = (item["kind"], item["source"], item["detail"])
            row = unique.setdefault(key, {**item, "observed_on": []})
            row["observed_on"].append({"url": report["url"], "viewport": report["viewport"]})
    return {"schema_version": 1, "policy": "Inventory only; verify licenses before reuse. URLs omit query and fragment; no source bytes or byte hashes collected.",
            "count": len(unique), "reports": len(reports), "truncated": any(r["truncated"] for r in reports),
            "items": list(unique.values())}
