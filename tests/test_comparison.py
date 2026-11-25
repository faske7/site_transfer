import pytest
from PIL import Image
from site_transfer.comparison import compare_pixels, compare_runs, sampled_structure
from site_transfer.manifest import digest


def image(path, color, size=(10,10)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB",size,color).save(path)
    return path


def test_identical(tmp_path):
    a=image(tmp_path/"a.png","white")
    result=compare_pixels(a,a,tmp_path/"diff.png")
    assert result["changed_percent"] == 0
    assert result["passes"]


def test_changed(tmp_path):
    a=image(tmp_path/"a.png","white")
    b=image(tmp_path/"b.png","black")
    result=compare_pixels(a,b,tmp_path/"diff.png")
    assert result["changed_percent"] == 100
    assert result["difference_bounds"] == [0,0,10,10]
    assert not result["passes"]


def test_tolerance(tmp_path):
    a=image(tmp_path/"a.png",(100,100,100))
    b=image(tmp_path/"b.png",(116,100,100))
    assert compare_pixels(a,b,tmp_path/"diff.png")["passes"]


def test_dimensions(tmp_path):
    a=image(tmp_path/"a.png","white")
    b=image(tmp_path/"b.png","white",(10,20))
    result=compare_pixels(a,b,tmp_path/"diff.png")
    assert result["changed_percent"] == 50
    assert not result["dimensions_match"]
    assert not result["passes"]


def job(root, name, url):
    path=image(root/"screenshots"/"a.png","white")
    return {"id":name,"status":"completed","manifest":{"artifacts":[{"url":url,"viewport":"desktop",
        "width":1440,"height":900,"path":"screenshots/a.png","sha256":digest(path)}]}}


def test_cross_origin_match(tmp_path):
    a,b=tmp_path/"a",tmp_path/"b"
    left,right=job(a,"a","https://example.com/"),job(b,"b","https://example.org/")
    report=compare_runs(left,right,a,b,tmp_path/"output")
    assert report["passes"]
    assert report["pairs"][0]["structure"] is None


def test_unmatched(tmp_path):
    a,b=tmp_path/"a",tmp_path/"b"
    left,right=job(a,"a","https://example.com/a"),job(b,"b","https://example.org/b")
    with pytest.raises(ValueError,match="No matching"):
        compare_runs(left,right,a,b,tmp_path/"output")


def test_checksum(tmp_path):
    a,b=tmp_path/"a",tmp_path/"b"
    left,right=job(a,"a","https://example.com/"),job(b,"b","https://example.org/")
    image(b/"screenshots"/"a.png","black")
    with pytest.raises(ValueError,match="checksum"):
        compare_runs(left,right,a,b,tmp_path/"output")


def test_structure():
    def entry(x):
        return {"elements":[{"selector":"html > body","rect":{"x":x,"y":0,"width":100,"height":100},"style":{}}]}
    result=sampled_structure(entry(0),entry(5))
    assert result["changed"] == 1
    assert result["examples"][0]["rect_delta"]["x"] == 5
    assert sampled_structure({"elements":[]},entry(0)) is None
