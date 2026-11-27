"""Wheel-first scroll engine shared by isolated states and timelines."""
from time import monotonic, perf_counter

from .page_readiness import check_cancelled, pause, remaining_ms
from .scroll_detection import snapshot_scroll, classify, at_end


class ScrollEngine:
    def __init__(self,page,cancelled=lambda:False,mobile=False,diagnostics=None):
        self.page=page
        self.cancelled=cancelled
        self.mobile=mobile
        self.diagnostics=diagnostics
        self.targets={}
        self.modes=set()
        self.stalls=0
        self.transform_only=False
        self.last=None

    def _input(self,state,step):
        root=state["root"]
        w,h=state["viewport"]
        point=[w/2,h/2]
        axis="y"
        direction=1
        # Preserve vertical wheel input for transform-driven sites. Switch
        # only after an observed stall and an actual horizontal extent.
        if self.stalls:
            # When root is exhausted, consider visible nested scroll areas
            # only if the document has no vertical extent or that container
            # was already observed moving. Avoid sweeping arbitrary carousels.
            if root["max_y"]<=3 or root["y"]<root["max_y"]-3 or self.targets.get("document",set())=={"x"}:
                candidates=state["containers"]
            else:
                candidates=[c for c in state["containers"] if c["id"] in self.targets]
            # Alternate root and candidate retries to avoid pinning forever
            # to an inert/covered container.
            if candidates and self.stalls%2==1:
                for c in candidates:
                    if c["scrollable_y"] and c["y"]<c["max_y"]-3:
                        point=c["point"]
                        break
                    if c["scrollable_x"] and abs(c["x"])<c["max_x"]-3:
                        point=c["point"]
                        axis="x"
                        direction=-1 if c["rtl"] else 1
                        break
                else:
                    candidates=[]
            else:
                candidates=[]
            if not candidates and root["max_x"]>3 and abs(root["x"])<root["max_x"]-3 and (
                root["max_y"]<=3 or root["y"]<root["max_y"]-3 or "x" in self.targets.get("document",set())
            ):
                axis="x"
                direction=-1 if root["rtl"] else 1
        return point,axis,step*direction

    def step(self,step,settle_ms,deadline):
        check_cancelled(self.cancelled)
        initial=snapshot_scroll(self.page,self.diagnostics)
        if not remaining_ms(deadline):
            return None
        point,axis,delta=self._input(initial,step)
        self.page.mouse.move(*point)
        idle=snapshot_scroll(self.page,self.diagnostics)
        pause(self.page,deadline,self.cancelled,80)
        before=snapshot_scroll(self.page,self.diagnostics)
        if not remaining_ms(deadline):
            return None
        self.page.mouse.wheel(delta if axis=="x" else 0,delta if axis=="y" else 0)
        pause(self.page,deadline,self.cancelled,max(120,settle_ms))
        after=snapshot_scroll(self.page,self.diagnostics)
        observation=self._classify(before,after,idle)
        fallback=False
        # Same limited mobile fallback as the previous timeline: do not
        # bypass wheel-driven desktop animation or nested/horizontal motion.
        if (self.mobile and axis=="y" and not observation["progress"]
                and before["root"]["y"]<before["root"]["max_y"]-3
                and remaining_ms(deadline)>0):
            self.page.evaluate("(step)=>window.scrollBy(0,step)",step)
            pause(self.page,deadline,self.cancelled,max(120,settle_ms))
            after=snapshot_scroll(self.page,self.diagnostics)
            observation=self._classify(before,after,idle)
            fallback=True
        for change in observation["coordinate_changes"]:
            axes=self.targets.setdefault(change["target"],set())
            if abs(change["dx"])>2:
                axes.add("x")
            if abs(change["dy"])>2:
                axes.add("y")
        self.modes.update(observation["modes"])
        if observation["transform_count"] and not observation["coordinate_changes"]:
            self.transform_only=True
        self.stalls=0 if observation["progress"] else self.stalls+1
        observation.update(input_axis=axis,input_delta=delta,point=point,
                           fallback_used=fallback,root_before=before["root"],root_after=after["root"],
                           containers_after=after["containers"])
        self.last=observation
        return observation

    def _classify(self,before,after,idle):
        started=perf_counter()
        result=classify(before,after,idle)
        if self.diagnostics is not None:
            self.diagnostics.add_time("other_processing_ms",started)
        return result

    def end(self,state=None):
        return at_end(state or snapshot_scroll(self.page,self.diagnostics),self.targets)

    def summary(self):
        modes=sorted(self.modes)
        return {"mode":"hybrid" if len(modes)>1 else modes[0] if modes else "undetermined",
                "modes":modes,"targets":[{"target":k,"axes":sorted(v)} for k,v in self.targets.items()],
                "transform_only_progress":self.transform_only}

    def scroll_to(self,target,settle_ms,deadline):
        """Legacy scroll_y is an absolute document Y for ordinary pages.

        For non-document scroll, report observed movement and input distance,
        never pretend a transform or nested coordinate equals document Y.
        """
        initial=snapshot_scroll(self.page,self.diagnostics)
        observations=[]
        attempted=0
        for _ in range(24):
            check_cancelled(self.cancelled)
            if not remaining_ms(deadline):
                break
            state=snapshot_scroll(self.page,self.diagnostics)
            y=state["root"]["y"]
            if abs(y-target)<=2 and observations:
                break
            if attempted>=target and self.modes and "vertical" not in self.targets.get("document",set()) and "y" not in self.targets.get("document",set()):
                break
            # One or more bounded wheel inputs. Legacy target is positive.
            # Initial page normally starts at zero; do not silently backtrack
            # a page that already navigated to a deeper anchor.
            if y>target+2:
                break
            step=min(600,max(1,round(target-y))) if self.targets.get("document",set())=={"y"} or y>0 else min(600,max(1,target-attempted))
            observation=self.step(step,min(settle_ms,500),deadline)
            if observation is None:
                break
            attempted+=step
            observations.append(observation)
            if self.stalls>=3 or self.end():
                break
        pause(self.page,deadline,self.cancelled,settle_ms)
        final=snapshot_scroll(self.page,self.diagnostics)
        y=final["root"]["y"]
        moved=any(o["progress"] for o in observations)
        document_y="y" in self.targets.get("document",set())
        return {"before":{"scroll_y":initial["root"]["y"],"scroll_x":initial["root"]["x"]},
                "after":{"scroll_y":y,"scroll_x":final["root"]["x"]},
                "progress":moved,"target_reached":abs(y-target)<=2 if document_y else None,
                "target_semantics":"document_y" if document_y else "observed_wheel_input",
                "requested_y":target,"attempted_input_px":attempted,
                "steps":observations,**self.summary()}
