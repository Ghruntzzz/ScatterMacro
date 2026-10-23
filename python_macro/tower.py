"""Tower lobby navigation; floor numbers are read, never hard-coded."""
import re
import time

from python_macro.challenges import ChallengeFlow
from python_macro.end_screen import center
from python_macro.story import normalize
from python_macro.story_verified import changed_screen, click_once
from python_macro.unit_actions import Icon
from python_macro.vision import Region


def visible_floors(matches):
    floors=[]
    for label in matches:
        text=normalize(label.text)
        x,y=center(label)
        height=max(p[1] for p in label.corners)-min(p[1] for p in label.corners)
        # Tab cards also say Floor N. Their nearby Tower heading distinguishes
        # them from the selectable floors in the main tower view.
        if any(normalize(m.text) in ('tower','traitlesstower')
               and abs(center(m)[0]-x)<max(100,height*5)
               and 0<y-center(m)[1]<max(45,height*3) for m in matches):
            continue
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
        self.next_floor=Icon(assets/'tower-next-floor.png',threshold=.85)
        self.repeat_floor=Icon(assets/'tower-repeat-floor.png',threshold=.85)

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
            excluded=[]
            for kind,icon in self.tab_icons.items():
                hit=icon(frame)
                if hit is not None:
                    x,y,width,_=hit
                    scale=width/(44 if kind=='Trait Tower' else 81)
                    excluded.append((x-170*scale,y-25*scale,x+65*scale,y+125*scale))
            options=[(number,point) for number,point in visible_floors(matches)
                     if not any(left<=point[0]<=right and top<=point[1]<=bottom
                                for left,top,right,bottom in excluded)]
            self.floor_frame,self.floor_options=frame,options
            self.ocr.last_frame,self.ocr.matches=frame,matches
        return self.floor_options

    def highest_floor(self,frame):
        floors=self.floors(frame)
        if not floors:
            return None
        highest=max(number for number,_ in floors)
        points={point for number,point in floors if number==highest}
        return next(iter(points)) if len(points)==1 else None

    def wait_map(self,map_names,timeout=None):
        self.log('Waiting for Tower match details.')
        previous=None
        deadline=time.monotonic()+timeout if timeout is not None else float('inf')
        while not self.stop.is_set():
            frame=self.capture()
            h,w=frame.shape[:2]
            matches=self.reader.read(frame,Region(w//2,0,w-w//2,h),scale=2,max_variants=1,
                                     min_confidence=.65,cancelled=self.stop.is_set)
            text=normalize(' '.join(m.text for m in matches))
            found=[name for name in map_names if normalize(name) in text]
            result=any(word in text for word in ('gainedrewards','gamestats','nextfloor','repeatfloor','selectstage'))
            current=found[0] if len(found)==1 and 'tower' in text and not result else None
            if current and current==previous:
                return current
            previous=current
            if time.monotonic()>=deadline:
                return None
            if self.stop.wait(.15):
                return None
        return None

    def transition(self,outcome,map_names,on_map):
        if outcome not in ('victory','defeat'):
            return False
        label='Next Floor' if outcome=='victory' else 'Repeat Floor'
        self.log('Advancing floor.' if outcome=='victory' else 'Repeating floor.')
        start_game=self.game_start
        # The two buttons have nearly identical grayscale shapes. Require the
        # exact outcome-specific text instead of accepting an image-only hit.
        if not self.press(label,self.text(label),
                          lambda after,before:start_game(after) is not None):
            return False
        map_name=self.wait_map(map_names)
        if map_name is None:
            return False
        on_map(map_name)
        return (outcome=='defeat' or self.client.setup_camera()) and not self.stop.is_set()

    def run(self,find_play,map_names,on_map,entries_provider,status,monitor_capture,reward_dir,notifier,assets):
        from python_macro.story_ingame import run_matches
        from python_macro.vision import StartButtonLocator
        self.game_start=StartButtonLocator(assets/'start-game-template.png')
        map_name=self.wait_map(map_names,timeout=3)
        in_match=map_name is not None
        if not in_match:
            if not self.navigate(find_play):
                return
            map_name=self.wait_map(map_names)
        if map_name is None or self.stop.is_set():
            return
        on_map(map_name)
        if not self.client.setup_camera() or self.stop.is_set():
            return
        run_matches(self.capture,self.client,self.reader,self.stop,self.log,assets,[],status,
                    monitor_capture,reward_dir,entries_provider,allow_active=in_match,
                    on_result=notifier.send,
                    transition_match=lambda outcome:self.transition(outcome,map_names,on_map))

    def navigate(self,find_play):
        if not self.press('Play',find_play,
                          lambda after,before:self.tower_target(after) is not None):
            return False
        if not self.press('Tower',self.tower_target,
                          lambda after,before:self.text('Traitless Tower')(after) is not None):
            return False
        # Selecting an already active tab may not change the screen at all.
        # Click once, then let the floor step wait for its own target.
        if not click_once(self.tower_type,self.tower_tab,self.capture,
                          self.client.direct_click,self.stop):
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
