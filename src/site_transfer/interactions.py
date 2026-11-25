"""Bounded hover-only observation; never click, type, submit or authenticate."""
STATE_JS = r"""
(selector) => {
  const el=document.querySelector(selector);
  if(!el) return null;
  const s=getComputedStyle(el), b=el.getBoundingClientRect();
  const keys=['color','background-color','border-top-color','box-shadow','opacity','transform',
              'cursor','text-decoration-line','outline-color','visibility','display'];
  return {style:Object.fromEntries(keys.map(k=>[k,s.getPropertyValue(k).slice(0,240)])),
          rect:{x:b.x,y:b.y,width:b.width,height:b.height},
          expanded:el.getAttribute('aria-expanded')};
}
"""


def inspect_interactions(page, snapshot):
    result = {"candidates": snapshot["candidates"], "hover": [],
              "limitations": ["No click, form submission, focus, scroll-driven or touch interaction is attempted."]}
    if not snapshot["viewport"]["hover"]:
        result["limitations"].append("Hover unavailable on this viewport")
        return result
    baseline_url = page.url
    for candidate in snapshot["candidates"][:4]:
        selector = candidate["selector"]
        try:
            page.mouse.move(0, 0)
            page.wait_for_timeout(100)
            before = page.evaluate(STATE_JS, selector)
            if before is None:
                raise ValueError("Element disappeared")
            rect = before["rect"]
            viewport = snapshot["viewport"]
            if not (rect["x"] >= 0 and rect["y"] >= 0
                    and rect["x"] + rect["width"] <= viewport["width"]
                    and rect["y"] + rect["height"] <= viewport["height"]):
                raise ValueError("Element moved outside viewport")
            page.mouse.move(rect["x"] + rect["width"]/2, rect["y"] + rect["height"]/2)
            page.wait_for_timeout(350)
            if page.url != baseline_url:
                raise ValueError("Page changed during hover")
            after = page.evaluate(STATE_JS, selector)
            if after is None:
                raise ValueError("Element disappeared")
            changes = {key: {"before": value, "after": after["style"][key]}
                       for key, value in before["style"].items() if value != after["style"][key]}
            result["hover"].append({"selector": selector, "status": "observed", "changes": changes,
                                    "before": before, "after": after, "sample_after_ms": 350})
        except Exception as exc:
            result["hover"].append({"selector": selector, "status": "unavailable", "error": str(exc)[:240]})
        if page.url != baseline_url:
            break
    return result
