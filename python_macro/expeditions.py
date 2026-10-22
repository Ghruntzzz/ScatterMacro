"""Expedition navigation and serialized handling of recurring match controls."""
import re
import time

from python_macro.challenges import ChallengeFlow
from python_macro.story import normalize
from python_macro.story_verified import changed_screen
from python_macro.unit_actions import Icon
from python_macro.vision import StartButtonLocator

MAPS=('School Grounds','Flower Forest','Rose Kingdom','East Town')


class ExpeditionFlow(ChallengeFlow):
    def __init__(self,capture,client,reader,stop,log,assets,map_name,difficulty,priority=None):
        if map_name not in MAPS or str(difficulty) not in ('1','2','3'):
            raise ValueError('Choose an Expedition map and difficulty 1-3.')
        super().__init__(capture,client,reader,stop,log,assets,{})
        self.map_name,self.difficulty=map_name,int(difficulty)
        self.expedition=Icon(assets/'expedition-button.png',threshold=.88)
        self.plus=Icon(assets/'expedition-difficulty.png',threshold=.9,crop=(170,32,43,42))
        self.minus=Icon(assets/'expedition-difficulty.png',threshold=.9,crop=(17,32,42,42))
        self.continue_button=Icon(assets/'expedition-continue.png',threshold=.9)
        self.confirm=Icon(assets/'expedition-confirm.png',threshold=.9)
        self.settings=Icon(assets/'expedition-settings.png',threshold=.92)
        self.teleport_row=Icon(assets/'expedition-teleport-row.png',threshold=.88)
        self.teleport=Icon(assets/'expedition-teleport.png',threshold=.92)
        self.close_icon=Icon(assets/'unit-close.png',threshold=.9)
        self.game_start=StartButtonLocator(assets/'start-game-template.png')
        self.last_service=0
        from python_macro.expedition_cards import CardSelector
        self.cards=CardSelector(assets,reader,client,capture,stop,log,priority)
        self.card_run=None

    def difficulty_reading(self,frame):
        point=self.ocr.unique(frame,lambda text:re.fullmatch(r'difficulty[123]',normalize(text)) is not None)
        if point is None:
            return None
        match=next(m for m in self.ocr.matches if re.fullmatch(r'difficulty[123]',normalize(m.text)))
        return int(normalize(match.text)[-1]),point

    def set_difficulty(self):
        for _ in range(4):
            reading=self.difficulty_reading(self.capture())
            if reading is None:
                raise RuntimeError('Could not read Expedition difficulty. No adjustment was clicked.')
            value,_=reading
            if value==self.difficulty:
                return True
            direction=1 if value<self.difficulty else -1
            def target(frame):
                current=self.difficulty_reading(frame)
                if current is None or current[0]!=value:
                    return None
                hit=(self.plus if direction>0 else self.minus)(frame)
                if hit is None:
                    return None
                x,y,w,h=hit
                px,py=current[1]
                if not 0<(x-px)*direction<w*5 or abs(y-py)>h*2:
                    return None
                return x,y
            if not self.press('Difficulty',target,
                              lambda after,before:self.difficulty_reading(after) is not None
                              and self.difficulty_reading(after)[0]==value+direction):
                return False
        raise RuntimeError('Expedition difficulty did not reach the selected value.')

    def navigate(self,find_play):
        expedition=lambda frame:self.expedition(frame) or self.text('Expedition','Expeditions')(frame)
        if not self.press('Play',find_play,lambda after,before:expedition(after) is not None):
            return False
        if not self.press('Expedition',expedition,
                          lambda after,before:self.text(self.map_name)(after) is not None):
            return False
        if not self.press(self.map_name,self.text(self.map_name),
                          lambda after,before:self.difficulty_reading(after) is not None):
            return False
        if not self.set_difficulty():
            return False
        if not self.press('Select Stage',self.text('Select Stage'),
                          lambda after,before:self.start(after) is not None):
            return False
        return self.press('Start',self.start,
                          lambda after,before:self.start(after) is None and changed_screen(before,after))

    def service(self,indexer):
        # Inputs stay on the unit worker thread, never race background monitors.
        if indexer is not self.card_run:
            self.card_run=indexer
            self.cards.reset()
        now=time.monotonic()
        if now-self.last_service<.25 or self.stop.is_set():
            return
        self.last_service=now
        frame=self.capture()
        if self.cards.handle(frame):
            active=getattr(indexer,'active_index',None)
            point=indexer.placed.get(active) if active is not None else None
            if point is not None and not self.stop.is_set():
                self.client.direct_click(*point,self.capture().shape)
            return
        hit=self.game_start(frame)
        if hit is not None:
            self.client.direct_click(*hit[:2],frame.shape)
            return
        if not indexer.all_done():
            return
        if self.confirm(frame) is not None:
            target=self.text('Continue')(frame)
        elif self.continue_button(frame) is not None:
            target=self.text('Continue')(frame)
        else:
            return
        if target is not None and not self.stop.is_set():
            self.client.direct_click(*target,frame.shape)

    def return_to_payload(self):
        if not self.press('Settings',self.settings,
                          lambda after,before:self.text('Settings')(after) is not None):
            return False
        def teleport_target(frame):
            row=self.teleport_row(frame)
            if row is None:
                return None
            x,y,w,h=row
            left=max(0,int(x+w*.25))
            top=max(0,int(y-h/2))
            crop=frame[top:int(y+h/2),left:int(x+w/2)]
            hit=self.teleport(crop) if crop.size else None
            return (left+hit[0],top+hit[1]) if hit is not None else None
        from python_macro.story_verified import click_once
        if not click_once('Teleport To Spawn',teleport_target,self.capture,self.client.direct_click,self.stop):
            return False
        def close_settings(frame):
            if self.text('Settings')(frame) is None:
                return None
            hit=self.close_icon(frame)
            return hit[:2] if hit is not None else None
        return self.press('Close Settings',close_settings,
                          lambda after,before:self.text('Settings')(after) is None)
