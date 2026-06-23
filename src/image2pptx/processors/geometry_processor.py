from __future__ import annotations
import cv2
import numpy as np
from image2pptx.pipeline.context import PipelineContext

class GeometryProcessor:
    def run(self, ctx: PipelineContext) -> None:
        img = cv2.imread(str(ctx.artifacts["normalized"]))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        shapes=[]
        h,w=gray.shape
        for i,c in enumerate(contours[:200]):
            area=cv2.contourArea(c)
            if area < 300 or area > w*h*0.8: continue
            x,y,bw,bh = cv2.boundingRect(c)
            approx=cv2.approxPolyDP(c, 0.03*cv2.arcLength(c, True), True)
            if len(approx)==4:
                crop=img[y:y+bh,x:x+bw]
                color=np.median(crop.reshape(-1,3), axis=0).astype(int)
                shapes.append({"id":f"shape_{i}","kind":"rectangle","bbox":[x,y,x+bw,y+bh],"fill_color":"#%02x%02x%02x"%(color[2],color[1],color[0]),"confidence":0.65})
        lines=[]
        raw=cv2.HoughLinesP(edges,1,np.pi/180,threshold=80,minLineLength=40,maxLineGap=8)
        if raw is not None:
            for i,l in enumerate(raw[:100]):
                x1,y1,x2,y2=map(int,l[0]); lines.append({"id":f"line_{i}","points":[[x1,y1],[x2,y2]],"confidence":0.6})
        ctx.candidates["shapes"]=shapes; ctx.candidates["lines"]=lines
