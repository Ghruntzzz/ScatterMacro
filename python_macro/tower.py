"""Tower lobby navigation; floor numbers are read, never hard-coded."""
import re

from python_macro.challenges import ChallengeFlow
from python_macro.end_screen import center
from python_macro.story import normalize
from python_macro.story_verified import changed_screen
from python_macro.unit_actions import Icon
from python_macro.vision import Region


def visible_floors(matches):
    floors=[]
    for label in matches:
        text=normalize(label.text)
        combined=re.fullmatch(r'floor([1-9][0-9]{0,3})',text)
        if combined:
            floors.append((int(combined[1]),center(label)))
            continue
        if text!='floor':
            continue
        x,y=center(label)
        height=max(p[1] for p in label.corners)-min(p[1] for p in label.corners)
        width=max(p[0] for p in label.corners)-min(p[0] for p in label.corners)
        numbers=[m for m in matches if re.fullmatch(r'[1-9][0-9]{0,3}',m.text.strip())
                 and abs(center(m)[0]-x)<max(width,20)
                 and y<center(m)[1]<y+max(height,12)*4]
        if numbers:
            closest=min(numbers,key=lambda m:center(m)[1]-y)
            floors.append((int(closest.text),center(closest)))
    return floors


class TowerFlow(ChallengeFlow):
    def __init__(self,capture,client,reader,stop,log,assets,tower_type):
        if tower_type not in ('Trait Tower','Traitless Tower'):
            raise ValueError('Choose Trait Tower or Traitless Tower.')
        super().__init__(capture,client,reader,stop,log,assets,{})
        self.tower_type=tower_type
        self.tower_button=Icon(assets/'tower-button.png',threshold=.85)
        # Static headings only: floor numbers and artwork change with progression.
        self.tab_icons={
            'Trait Tower':Icon(assets/'tower-trait-tab.png',threshold=.88,crop=(143,8,44,14)),
            'Traitless Tower':Icon(assets/'tower-traitless-tab.png',threshold=.88,crop=(103,6,81,16)),
        }
        self.floor_frame,self.floor_options=None,[]

    def tower_target(self,frame):
        return self.tower_button(frame) or self.text('Tower')(frame)

    def tower_tab(self,frame):
        label='Tower' if self.tower_type=='Trait Tower' else 'Traitless Tower'
        return self.tab_icons[self.tower_type](frame) or self.text(label)(frame)

    def floors(self,frame):
        if frame is not self.floor_frame:
            h,w=frame.shape[:2]
            matches=self.reader.read(frame,Region(0,0,w,h),scale=2,max_variants=1,
                                     min_confidence=.65,cancelled=self.stop.is_set)
            self.floor_frame,self.floor_options=frame,visible_floors(matches)
            self.ocr.last_frame,self.ocr.matches=frame,matches
        return self.floor_options

    def highest_floor(self,frame):
        floors=self.floors(frame)
        if not floors:
            return None
        highest=max(number for number,_ in floors)
        points={point for number,point in floors if number==highest}
        return next(iter(points)) if len(points)==1 else None

    def wait_map(self,map_names):
        self.log('Waiting for Tower match details.')
        previous=None
        while not self.stop.is_set():
            frame=self.capture()
            h,w=frame.shape[:2]
            matches=self.reader.read(frame,Region(w//2,0,w-w//2,h),scale=2,max_variants=1,
                                     min_confidence=.65,cancelled=self.stop.is_set)
            text=normalize(' '.join(m.text for m in matches))
            found=[name for name in map_names if normalize(name) in text]
            current=found[0] if len(found)==1 and 'tower' in text else None
            if current and current==previous:
                return current
            previous=current
            if self.stop.wait(.15):
                return None
        return None

    def navigate(self,find_play):
        if not self.press('Play',find_play,
                          lambda after,before:self.tower_target(after) is not None):
            return False
        if not self.press('Tower',self.tower_target,
                          lambda after,before:self.text('Traitless Tower')(after) is not None):
            return False
        if not self.press(self.tower_type,self.tower_tab,
                          lambda after,before:changed_screen(before,after) and bool(self.floors(after))):
            return False
        self.log('Selecting highest visible floor.')
        if not self.press('Floor',self.highest_floor,
                          lambda after,before:self.text('Select Stage')(after) is not None):
            return False
        if not self.press('Select Stage',self.text('Select Stage'),
                          lambda after,before:self.start(after) is not None):
            return False
        if not self.press('Start',self.start,
                          lambda after,before:self.start(after) is None and changed_screen(before,after)):
            return False
        self.log('Tower navigation complete.')
        return True
