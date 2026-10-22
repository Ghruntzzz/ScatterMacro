"""Six gated fights followed by a separately configured boss arena."""
import time

from python_macro.challenges import ChallengeFlow
from python_macro.shop_routes import ShopRoutes
from python_macro.unit_actions import Icon,UnitIndexer,UnitPanel
from python_macro.pathing import replay_path
from python_macro.vision import Region,StartButtonLocator
from python_macro.story import normalize
from python_macro.end_screen import center


class GateRoutes(ShopRoutes):
    names=tuple('Gate '+str(n) for n in range(1,7))


def matches_details(matches):
    text=normalize(' '.join(m.text for m in matches))
    return ('bossrush' in text and 'district7' in text and 'hardmode' in text
            and not any(t in text for t in ('selectstage','specialgamemode','gainedrewards')))


class GateComplete(Exception):
    pass


class RunComplete(Exception):
    pass


class BossRushFlow(ChallengeFlow):
    def __init__(self,capture,client,reader,stop,log,assets,routes):
        super().__init__(capture,client,reader,stop,log,assets,{})
        self.assets,self.routes=assets,routes
        self.mode_button=Icon(assets/'boss-rush-button.png',threshold=.85)
        self.enter=Icon(assets/'boss-rush-enter.png',threshold=.85)
        self.choice=Icon(assets/'boss-rush-choice.png',threshold=.85,crop=(2,0,237,32))
        self.continue_icon=Icon(assets/'boss-rush-continue.png',threshold=.87)
        self.fight_icon=Icon(assets/'boss-rush-fight.png',threshold=.87)
        self.game_start=StartButtonLocator(assets/'start-game-template.png')

    def navigate(self,find_play):
        mode=lambda f:self.mode_button(f)
        return (self.press('Play',find_play,lambda a,b:mode(a) is not None)
                and self.press('Boss Rush',mode,lambda a,b:self.text('Select Stage')(a) is not None)
                and self.press('Select Stage',self.text('Select Stage'),lambda a,b:self.start(a) is not None)
                and self.press('Start',self.start,lambda a,b:self.start(a) is None))

    def wait_details(self):
        confirmed=0
        while not self.stop.is_set():
            frame=self.capture()
            h,w=frame.shape[:2]
            matches=self.reader.read(frame,Region(0,0,w,h),scale=2,max_variants=2,
                                     min_confidence=.65,cancelled=self.stop.is_set)
            valid=matches_details(matches)
            confirmed=confirmed+1 if valid else 0
            if confirmed>=2:
                return True
            if self.stop.wait(.15):
                return False
        return False

    def enter_gate(self,number):
        route=self.routes.load('Gate '+str(number))
        if route is None:
            raise RuntimeError(f'Record Gate {number} before starting Boss Rush.')
        self.log(f'Navigating to Gate {number}.')
        replay_path(route['path'],self.client,self.stop)
        from python_macro.story_verified import click_and_confirm
        def enter_key(x,y,shape):
            return self.client.hold_key('E',.1)
        return click_and_confirm('Gate entrance',self.enter,
                                 lambda a,b:self.game_start(a) is not None,
                                 self.capture,enter_key,self.stop,self.log,timeout=30)

    def decision_target(self,frame,gate):
        if self.choice(frame) is None:
            return None
        label='Fight Boss' if gate==6 else 'Continue'
        hit=(self.fight_icon if gate==6 else self.continue_icon)(frame)
        if hit is None:
            return None
        self.text(label)(frame)
        x,y,w,h=hit
        points=[center(m) for m in self.ocr.matches if normalize(m.text)==normalize(label)
                and abs(center(m)[0]-x)<=w/2 and abs(center(m)[1]-y)<=h/2]
        return points[0] if len(points)==1 else None

    def decide(self,gate):
        label='Fight Boss' if gate==6 else 'Continue'
        if not self.press(label,lambda f:self.decision_target(f,gate),
                          lambda a,b:self.choice(a) is None):
            return False
        self.client.park_cursor(self.capture().shape)
        return gate==6 or not self.stop.wait(3)

    def run(self,find_play,on_profile,entries_provider,status,monitor_capture,reward_dir,notifier):
        from python_macro.match_monitor import MatchMonitor
        from python_macro.story_ingame import start_game,finish_match
        # Validate every route before navigating; never strand a run at a missing gate.
        for name in self.routes.names:
            if self.routes.load(name) is None:
                raise RuntimeError(f'Record {name} in Gate Routes before starting Boss Rush.')
        if not self.navigate(find_play):
            return
        monitor=MatchMonitor(monitor_capture,self.assets,status)
        monitor.start()
        first_run=True
        try:
            while not self.stop.is_set():
                on_profile('Gate map')
                if not self.wait_details() or not self.client.setup_camera():
                    return
                if not start_game(self.capture,self.client,self.stop,self.assets):
                    return
                started=time.monotonic()
                status(dict(new_run=True,wave=None))
                monitor.reset()
                boss=False
                last_poll=[0.0]
                def checkpoint():
                    state=monitor.snapshot()
                    if state.get('error'):
                        raise RuntimeError(state['error'])
                    if state.get('outcome'):
                        raise RunComplete()
                    if not boss and time.monotonic()-last_poll[0]>=.15:
                        last_poll[0]=time.monotonic()
                        if self.choice(self.capture()) is not None:
                            raise GateComplete()
                    return state.get('wave')
                def phase(place_units):
                    entries=entries_provider()
                    indexer=UnitIndexer(entries,self.client,self.capture,UnitPanel(self.reader,self.stop,self.assets),
                                        self.stop,self.log,heartbeat=checkpoint,allow_paths=first_run,
                                        allow_incomplete=True)
                    if not place_units:
                        indexer.completed.update(i for i,e in enumerate(entries)
                                                 if not e.get('path') or e.get('path_repeat','Once')!='Repeated')
                    while not self.stop.is_set():
                        wave=checkpoint()
                        indexer.entries=entries_provider()
                        index=indexer.next_ready(wave[0] if wave else None)
                        if index is not None:
                            indexer.run(index)
                        if self.stop.wait(.05):
                            return
                try:
                    for gate in range(1,7):
                        if not self.enter_gate(gate) or not start_game(self.capture,self.client,self.stop,self.assets):
                            return
                        monitor.reset()
                        try:
                            phase(gate==1)
                        except GateComplete:
                            pass
                        if self.stop.is_set() or not self.decide(gate):
                            return
                    boss=True
                    on_profile('Boss map')
                    if not start_game(self.capture,self.client,self.stop,self.assets):
                        return
                    monitor.reset()
                    phase(True)
                except RunComplete:
                    pass
                if self.stop.is_set():
                    return
                if not finish_match(self.capture,self.client,self.reader,self.stop,self.log,status,reward_dir,
                                    started,self.game_start,on_result=notifier.send):
                    return
                first_run=False
        finally:
            monitor.close()
