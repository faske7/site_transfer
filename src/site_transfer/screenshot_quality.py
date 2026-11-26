"""Decode and classify PNG evidence, independent of Playwright."""
from io import BytesIO
from PIL import Image


def inspect_png(data, max_pixels=40_000_000):
    """Reject corrupt/empty/uniform images; report sparse contrast separately."""
    if not data:
        return {"status":"invalid","code":"empty_png"}
    try:
        with Image.open(BytesIO(data)) as im:
            w,h=im.size
            if im.format!="PNG":
                return {"status":"invalid","code":"not_png"}
            if not w or not h or w*h>max_pixels:
                return {"status":"invalid","code":"pixel_budget","image_size":[w,h]}
            im.verify()
        with Image.open(BytesIO(data)) as im:
            im.load()
            if im.mode=="RGB":
                rgb=im
            elif "A" in im.getbands() or "transparency" in im.info:
                rgba=im.convert("RGBA")
                rgb=Image.new("RGB",rgba.size,"white")
                rgb.paste(rgba,mask=rgba.getchannel("A"))
            else:
                rgb=im.convert("RGB")
            extrema=rgb.getextrema()
            if all(lo==hi for lo,hi in extrema):
                code="white_png" if all(lo==255 for lo,_ in extrema) else "uniform_png"
                return {"status":"invalid","code":code,"image_size":[w,h]}
            rgb.thumbnail((256,256))
            raw=rgb.tobytes()
            pixels=zip(raw[0::3], raw[1::3], raw[2::3])
            count=rgb.width*rgb.height
            near_white=sum(min(p)>=248 for p in pixels)/count
            return {"status":"warning" if near_white>=.995 else "valid",
                    "code":"low_contrast" if near_white>=.995 else "content_detected",
                    "image_size":[w,h],"near_white_fraction":round(near_white,6)}
    except (OSError,ValueError,SyntaxError,Image.DecompressionBombError):
        return {"status":"invalid","code":"corrupt_png"}
