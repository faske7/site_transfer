"""Walk the document in bounded viewport steps; restore original scroll."""
from .page_readiness import check_cancelled, pause, remaining_ms

MAX_STEPS=16
MAX_DISTANCE=16000

def smart_scroll(page, deadline, cancelled):
    start=page.evaluate("() => ({x:scrollX,y:scrollY})")
    steps=0
    reached_bottom=False
    try:
        while steps<MAX_STEPS and remaining_ms(deadline):
            check_cancelled(cancelled)
            info=page.evaluate("""() => ({y:scrollY,h:innerHeight,
                bottom:Math.max(0,document.documentElement.scrollHeight-innerHeight)})""")
            if info["y"]>=info["bottom"]-2:
                reached_bottom=True
                break
            y=min(info["bottom"],info["y"]+max(1,int(info["h"]*.8)),start["y"]+MAX_DISTANCE)
            if y<=info["y"]:
                break
            page.evaluate("(y) => window.scrollTo({top:y,behavior:'instant'})",y)
            steps+=1
            pause(page,deadline,cancelled,200)
        if not reached_bottom and remaining_ms(deadline):
            reached_bottom=page.evaluate("() => scrollY >= Math.max(0,document.documentElement.scrollHeight-innerHeight)-2")
        return {"steps":steps,"reached_bottom":reached_bottom,
                "status":"complete" if reached_bottom else "bounded"}
    finally:
        page.evaluate("(p) => window.scrollTo({left:p.x,top:p.y,behavior:'instant'})",start)
