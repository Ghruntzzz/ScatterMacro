"""Challenge selection using live availability, with Story's match engine."""
from dataclasses import dataclass
import re
import time

from python_macro.end_screen import center
from python_macro.story import normalize
from python_macro.story_verified import FastText, click_and_confirm, changed_screen
from python_macro.unit_actions import Icon
from python_macro.vision import Region, StartButtonLocator

ORDER = ('weekly','daily','regular1','regular2','regular3')


def category(key):
    return 'regular' if key.startswith('regular') else key


def reset_seconds(text):
    match = re.search(r'(\d{1,3}):(\d{2})(?::(\d{2}))?',text)
    if not match:
        return None
    parts = [int(n) for n in match.groups() if n is not None]
    if any(n >= 60 for n in parts[1:]):
        return None
    return sum(n*60**i for i,n in enumerate(reversed(parts)))


@dataclass
class Card:
    key: str
    map_name: str
    act: str
    point: tuple
    remaining: int | None
    reset: int | None


def menu_data(matches):
    tabs = {}
    cards = []
    for kind in ('weekly','daily','regular'):
        anchors = [m for m in matches if normalize(m.text) == kind+'challenge']
        if not anchors:
            continue
        anchor = min(anchors,key=lambda m:center(m)[0])
        x,y = center(anchor)
        height = max(p[1] for p in anchor.corners)-min(p[1] for p in anchor.corners)
        nearby = [m.text for m in matches if abs(center(m)[0]-x) < height*8
                  and y < center(m)[1] < y+height*4]
        compact = normalize(' '.join(nearby))
        available = 'rewardsavailable' in compact and 'unavailable' not in compact
        reset = next((reset_seconds(t) for t in nearby if reset_seconds(t) is not None),None)
        tabs[kind] = dict(point=(x,y),available=available,reset=reset,x=x,height=height)
    headers = []
    for match in matches:
        text=re.sub(r'#\s*[\]Il|]\s*$','#1',match.text)
        found = re.fullmatch(r'(regular|daily|weekly)challenge([123])',normalize(text))
        if found:
            headers.append((match,found[1],found[2]))
    for header,kind,number in headers:
        hx,hy = center(header)
        tab = tabs.get(kind)
        if tab is None or not tab['available']:
            continue
        lower = min([center(m)[1] for m,k,n in headers if center(m)[1] > hy+10] or [hy+tab['height']*10])
        row = [m for m in matches if center(m)[0] > tab['x']+tab['height']*5
               and hy <= center(m)[1] < lower]
        routes = []
        for match in row:
            route = re.fullmatch(r'(.+?)\s*[-–]?\s*Act\s*([1-5])',match.text.strip(),re.I)
            if route:
                routes.append((match,route[1].rstrip(' -–'),f'Act {route[2]}'))
        if len(routes) != 1:
            continue
        remaining = None
        for match in row:
            limit = re.search(r'(\d+)\s*/\s*10\b',match.text)
            if limit and 'limit' in normalize(match.text):
                remaining = int(limit[1])
        if any('unavailable' in normalize(m.text) for m in row):
            continue
        match,map_name,act = routes[0]
        cards.append(Card(kind+number if kind=='regular' else kind,map_name,act,
                          center(match),remaining,tab['reset']))
    return tabs,cards


class ChallengeFlow:
    def __init__(self,capture,client,reader,stop,log,assets,settings,clock=time.monotonic):
        self.capture,self.client,self.reader,self.stop,self.log = capture,client,reader,stop,log
        self.settings,self.clock = settings,clock
        self.enabled = [key for key in ORDER if settings.get('challenge_'+key,'1') == '1']
        self.ocr = FastText(reader,stop)
        self.start = StartButtonLocator(assets/'start-button-template.png')
        self.party = Icon(assets/'view-party.png',threshold=.85)
        self.change = Icon(assets/'change-gamemode.png',threshold=.85)
        self.challenge = Icon(assets/'challenge-button.png',threshold=.85)
        self.back = Icon(assets/'challenge-back.png',threshold=.85)
        # Only the static label/status strip participates, never the reset timer.
        self.tab_icons = {kind:Icon(assets/('challenge-'+kind+'.png'),threshold=.88,
                                   crop=(6,6,160,34)) for kind in ('regular','daily')}
        self.weekly_unavailable = Icon(assets/'challenge-weekly-unavailable.png',threshold=.88,
                                       crop=(6,6,160,34))
        self.menu_frame, self.menu_result = None, None
        self.cooldowns = {}
        self.current = None
        self.wins = {}
        self.expires = {}
        self.budget = {}

    def read_menu(self,frame=None):
        frame = self.capture() if frame is None else frame
        if frame is self.menu_frame:
            return self.menu_result
        h,w = frame.shape[:2]
        matches = self.reader.read(frame,Region(0,0,w,h),scale=2,max_variants=1,
                                   min_confidence=.6,cancelled=self.stop.is_set)
        self.menu_frame, self.menu_result = frame, menu_data(matches)
        self.ocr.last_frame,self.ocr.matches=frame,matches
        return self.menu_result

    def cooldown(self,frame):
        point=self.ocr.unique(frame,lambda text:'availablein' in normalize(text))
        if point is None:
            return None
        text=next(m.text for m in self.ocr.matches if 'availablein' in normalize(m.text))
        return reset_seconds(text) or 30

    def challenge_target(self,frame):
        return self.challenge(frame) or self.text('Challenge','Challenges')(frame)

    def back_target(self,frame):
        return self.back(frame) or self.text('Back')(frame)

    def tab_target(self,kind,frame):
        icon=self.tab_icons.get(kind)
        if icon is not None:
            point=icon(frame)
            if point is not None:
                return point
        if kind=='weekly' and self.weekly_unavailable(frame) is not None:
            return None
        tab=self.read_menu(frame)[0].get(kind)
        return tab['point'] if tab and tab['available'] else None

    def text(self,*labels):
        names = {normalize(label) for label in labels}
        return lambda frame:self.ocr.unique(frame,lambda text:normalize(text) in names)

    def press(self,label,locate,advanced=None):
        check=advanced or (lambda after,before:changed_screen(before,after))
        def confirmed(after,before):
            if check(after,before):
                self.transition_frame=after
                return True
            return False
        return click_and_confirm(label,locate,confirmed,
                                 self.capture,self.client.start_click if label=='Start' else self.client.direct_click,
                                 self.stop,self.log,timeout=30,stable_seconds=.45 if label=='Start' else 0)

    def open_menu(self,find_play):
        if len(self.read_menu()[0]) == 3:
            return True
        if not self.press('Play',find_play,lambda after,before:self.challenge_target(after) is not None):
            return False
        return self.press('Challenge',self.challenge_target,
                          lambda after,before:len(self.read_menu(after)[0])==3)

    def identity(self,card):
        return card.key,normalize(card.map_name),card.act

    def permitted(self,card):
        identity = self.identity(card)
        now = self.clock()
        if now < self.cooldowns.get(identity,0):
            return False
        if now >= self.expires.get(identity,float('inf')):
            self.wins.pop(identity,None)
            self.budget.pop(identity,None)
            self.expires.pop(identity,None)
        cap = min(10,card.remaining) if card.remaining is not None else (10 if card.key.startswith('regular') else 1)
        self.budget.setdefault(identity,cap)
        return self.wins.get(identity,0) < self.budget[identity] and cap > 0

    def completed(self):
        if self.current is None:
            return
        identity=self.identity(self.current)
        self.wins[identity]=self.wins.get(identity,0)+1
        fallback=604800 if self.current.key=='weekly' else 86400
        self.expires.setdefault(identity,self.clock()+max(1,self.current.reset or fallback))

    def select(self):
        if not self.enabled:
            raise RuntimeError('Select at least one Challenge in the dashboard.')
        waiting=False
        while not self.stop.is_set():
            for key in self.enabled:
                kind=category(key)
                tabs,cards=self.read_menu()
                if len(tabs)!=3:
                    raise RuntimeError('Could not read the Challenge menu. No challenge was clicked.')
                if not tabs[kind]['available']:
                    continue
                # Resolve tab coordinates again rather than reusing a previous menu frame.
                def tab_target(frame):
                    return self.tab_target(kind,frame)
                if not any(category(c.key)==kind for c in cards):
                    if not self.press(kind.title()+' Challenge',tab_target,
                        lambda after,before:any(category(c.key)==kind for c in self.read_menu(after)[1])):
                        return None
                    _,cards=self.read_menu(getattr(self,'transition_frame',None))
                card=next((c for c in cards if c.key==key and self.permitted(c)),None)
                if card is None:
                    continue
                if card.reset is not None:
                    self.expires.setdefault(self.identity(card),self.clock()+max(1,card.reset))
                def card_target(frame):
                    return next((c.point for c in self.read_menu(frame)[1]
                                 if c.key==key and self.identity(c)==self.identity(card) and self.permitted(c)),None)
                self.log('Selecting '+key.replace('regular','Regular Challenge #').title()+'.')
                if not self.press('Challenge stage',card_target,
                                  lambda after,before:self.cooldown(after) is not None or self.text('Select Stage')(after) is not None):
                    return None
                frame=getattr(self,'transition_frame',None)
                seconds=self.cooldown(frame if frame is not None else self.capture())
                if seconds is not None:
                    self.cooldowns[self.identity(card)]=self.clock()+seconds
                    self.log('Challenge is on cooldown. Moving to the next challenge.')
                    if not self.press('Back',self.back_target,
                                      lambda after,before:self.back_target(after) is None and bool(self.read_menu(after)[1])):
                        return None
                    continue
                if not self.press('Select Stage',self.text('Select Stage'),
                                  lambda after,before:self.start(after) is not None):
                    return None
                if not self.press('Start',self.start,
                                  lambda after,before:self.start(after) is None and changed_screen(before,after)):
                    return None
                self.current=card
                return card
            if not waiting:
                self.log('Selected challenges are unavailable. Waiting for reset.')
                waiting=True
            if self.stop.wait(30):
                return None

    def return_to_menu(self):
        self.completed()
        if not self.press('View Party',lambda f:self.party(f) or self.text('View Party')(f),
                          lambda after,before:self.change(after) is not None or self.text('Change Gamemode','Change Mode')(after) is not None):
            return False
        if not self.press('Change Gamemode',lambda f:self.change(f) or self.text('Change Gamemode','Change Mode')(f),
                          lambda after,before:self.challenge_target(after) is not None):
            return False
        return self.press('Challenge',self.challenge_target,
                          lambda after,before:len(self.read_menu(after)[0])==3)


def run_challenges(capture,client,reader,stop,log,assets,settings,entries,status,
                   monitor_capture,reward_dir,entries_provider,notifier,find_play,route_entries=None):
    from python_macro.story_ingame import run_story_ingame,prepare_match
    flow=ChallengeFlow(capture,client,reader,stop,log,assets,settings)
    if not flow.enabled:
        raise RuntimeError('Select at least one Challenge in the dashboard.')
    card=None
    previous=None
    deadline=time.monotonic()+3
    while not stop.is_set():
        frame=capture()
        # A selected menu card also contains a Challenge name and map/act.
        # Never mistake that preview for the in-match HUD.
        if len(flow.read_menu(frame)[0])==3:
            if stop.wait(max(0,deadline-time.monotonic())):
                return
            break
        h,w=frame.shape[:2]
        matches=reader.read(frame,Region(w//2,0,w-w//2,h),scale=2,max_variants=1,
                            min_confidence=.7,cancelled=stop.is_set)
        current=active_challenge(matches)
        if current is not None and previous is not None and (current.key,current.map_name,current.act)==(previous.key,previous.map_name,previous.act):
            card=current
            if card.key in ORDER and card.key not in flow.enabled:
                raise RuntimeError('The current Challenge is disabled in your settings.')
            flow.current=card
            break
        previous=current
        remaining=deadline-time.monotonic()
        if remaining<=0 or stop.wait(min(.1,remaining)):
            break
    in_match=card is not None
    if not in_match:
        if stop.is_set() or not flow.open_menu(find_play):
            return
        card=flow.select()
    if card is None:
        return
    def set_route(card):
        notifier.settings.update(map=card.map_name,act=card.act,difficulty='Hard',mode='Challenges')
        route[0]=card
    route=[card]
    def challenge_entries():
        current=route[0]
        if route_entries is not None:
            return route_entries(current.map_name,current.act)
        return entries_provider() if entries_provider else entries
    set_route(card)
    def next_match():
        if not flow.return_to_menu():
            return False
        card=flow.select()
        if card is None:
            return False
        set_route(card)
        return prepare_match(card.map_name,card.act,'Hard',capture,client,reader,stop,log,mode='Challenge')
    run_story_ingame(card.map_name,card.act,'Hard',capture,client,reader,stop,log,assets,entries,status,
                     monitor_capture=monitor_capture,reward_dir=reward_dir,entries_provider=challenge_entries,
                     mode='Challenge',on_result=notifier.send,next_match=next_match,match_confirmed=in_match)


def active_challenge(matches):
    text=' '.join(m.text for m in matches)
    if 'challenge' not in normalize(text):
        return None
    if any(marker in normalize(text) for marker in ('rewardsavailable','resetsin','beforenextreset','beforethenextreset')):
        return None
    key='unknown'
    found=re.search(r'(weekly|daily|regular)\s*challenge\s*#?\s*([123])?',text,re.I)
    if found:
        kind=found[1].lower()
        key=kind+(found[2] or '') if kind=='regular' else kind
    routes=[]
    for match in matches:
        line=re.sub(r'(?:weekly|daily|regular)?\s*challenges?\s*#?\s*[123]?','',match.text,flags=re.I).strip()
        route=re.fullmatch(r'(.+?)\s*[-–]?\s*Act\s*([1-5])',line,re.I)
        if route:
            routes.append((route[1].rstrip(' -–'),f'Act {route[2]}'))
    if len(routes)==1:
        return Card(key,*routes[0],(0,0),None,None)
    return None
