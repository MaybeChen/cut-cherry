from PIL import Image, ImageDraw
from pptx import Presentation
from image2pptx.config.settings import load_settings
from image2pptx.pipeline.orchestrator import ImageToPptxPipeline

def test_cpu_pipeline_creates_openable_pptx(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/"config").mkdir()
    (tmp_path/"config"/"default.yaml").write_text("runtime:\n  device: cpu\noutput:\n  root_dir: outputs\n", encoding="utf-8")
    img=Image.new("RGB", (640,360), "white"); d=ImageDraw.Draw(img); d.rectangle((50,50,250,150), outline="black", width=3); d.line((260,100,420,100), fill="black", width=3)
    src=tmp_path/"fixture.png"; img.save(src)
    res=ImageToPptxPipeline(load_settings(device="cpu")).run(src)
    assert res.pptx_path.exists(); assert res.ir_path.exists()
    prs=Presentation(str(res.pptx_path)); assert len(prs.slides) == 1
