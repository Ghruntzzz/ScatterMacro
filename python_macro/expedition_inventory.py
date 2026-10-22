"""Visible hammer slots and payload health; never infer hidden inventory."""
import re
import cv2
import numpy as np
from python_macro.end_screen import center
from python_macro.story import normalize


def payload_health(matches):
    anchors=[m for m in matches if normalize(m.text)=='payload']
    readings=set()
    for anchor in anchors:
        x,y=center(anchor)
        height=max(p[1] for p in anchor.corners)-min(p[1] for p in anchor.corners)
        for match in matches:
            px,py=center(match)
            if abs(px-x)>max(60,height*5) or not 0<py-y<max(40,height*3):
                continue
            value=re.fullmatch(r'([\d,]+)\s*/\s*([\d,]+)',match.text.strip())
            if value:
                current,total=(int(s.replace(',','')) for s in value.groups())
                if total>0 and 0<=current<=total:
                    readings.add((current,total))
    return next(iter(readings)) if len(readings)==1 else None


class HammerInventory:
    def __init__(self,path):
        source=cv2.imread(str(path))
        if source is None:
            raise RuntimeError('Repair Hammer inventory reference is missing.')
        self.tiles=[cv2.resize(source,None,fx=s,fy=s) for s in (.6,.75,.85,1,1.25,1.5,1.75,2)]

    def find(self,frame):
        height,width=frame.shape[:2]
        top=int(height*.78)
        inventory=np.ascontiguousarray(frame[top:,:,:3])
        hits=[]
        for tile in self.tiles:
            h,w=tile.shape[:2]
            if h>inventory.shape[0] or w>width:
                continue
            scores=cv2.matchTemplate(inventory,tile,cv2.TM_CCOEFF_NORMED)
            for _ in range(10):
                _,score,_,(x,y)=cv2.minMaxLoc(scores)
                if score<.86:
                    break
                hits.append((score,(x+w//2,top+y+h//2),w,h))
                scores[max(0,y-h//2):y+h,max(0,x-w//2):x+w]=-1
        found=[]
        for score,point,w,h in sorted(hits,reverse=True):
            if all(abs(point[0]-p[0])>max(w,pw)*.5 or abs(point[1]-p[1])>max(h,ph)*.5
                   for p,pw,ph in found):
                found.append((point,w,h))
        return [p for p,_,_ in sorted(found,key=lambda item:item[0][0])][:10]
