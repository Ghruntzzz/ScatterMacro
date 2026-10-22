"""Category-ranked card selection with per-run history and verified buttons."""
import json
import time
from python_macro.story import normalize
from python_macro.end_screen import center
from python_macro.unit_actions import Icon
from python_macro.vision import Region

DEFAULT_PRIORITY=('Economy','Buff','DOT','Followup Attack','Payload','Summon','Elementalist')
ANVIL_PRIORITY=('Exp Multiplier','Range','Spa','Element Damage','Damage','Archetype Damage',
                'Summon Health','Critical Damage','Critical Chance','Bonus Match Rewards',
                'Follow-Up Damage','DoT DMG Dealt','Yen Generation','Payload Health','Summon Damage')


def anvil_order(values):
    values=values.split('|') if isinstance(values,str) else values or ()
    return list(dict.fromkeys([v for v in values if v in ANVIL_PRIORITY]+list(ANVIL_PRIORITY)))


def priority_order(values):
    values=values.split('|') if isinstance(values,str) else values or ()
    return list(dict.fromkeys([v for v in values if v in DEFAULT_PRIORITY]+list(DEFAULT_PRIORITY)))


def choose_card(cards,priority,selected):
    candidates=[c for c in cards if c['name'] not in selected] or cards
    order=priority_order(priority)
    return min(candidates,key=lambda c:(order.index(c['category']),-c['tier'])) if candidates else None


def offered_cards(matches,catalog):
    names={normalize(c['name']):c for c in catalog}
    buttons=sorted([m for m in matches if normalize(m.text)=='selectupgrade'],key=lambda m:center(m)[0])
    if len(buttons)!=3:
        return []
    xs=[center(b)[0] for b in buttons]
    cards=[]
    for i,button in enumerate(buttons):
        bx,by=center(button)
        left=(xs[i-1]+bx)/2 if i else float('-inf')
        right=(xs[i+1]+bx)/2 if i<len(buttons)-1 else float('inf')
        rarity=[center(m)[1] for m in matches if left<center(m)[0]<right
                and normalize(m.text) in ('commonupgrade','rareupgrade','epicupgrade','legendaryupgrade','mythicupgrade')
                and center(m)[1]<by]
        title_bottom=min(rarity) if rarity else by
        titles=[m for m in matches if normalize(m.text) in names
                and left<center(m)[0]<right and center(m)[1]<title_bottom]
        if len(titles)!=1:
            return []
        cards.append(dict(names[normalize(titles[0].text)],point=(bx,by)))
    return cards if len({c['name'] for c in cards})==len(cards) else []


class CardSelector:
    def __init__(self,assets,reader,client,capture,stop,log,priority=DEFAULT_PRIORITY):
        self.catalog=json.loads((assets/'expedition-card-catalog.json').read_text())['cards']
        self.header=Icon(assets/'expedition-card-screen.png',threshold=.85,crop=(352,30,134,22))
        self.anvil_header=Icon(assets/'expedition-anvil-screen.png',threshold=.85,crop=(360,50,148,47))
        self.reader,self.client,self.capture,self.stop,self.log=reader,client,capture,stop,log
        self.priority=priority_order(priority)
        self.selected=set()
        self.anvil_priority=anvil_order(None)
        self.last_probe=0

    def read_choices(self,frame):
        h,w=frame.shape[:2]
        matches=self.reader.read(frame,Region(0,0,w,h),scale=2,max_variants=3,
                                min_confidence=.65,cancelled=self.stop.is_set)
        if self.choose(matches) is not None:
            return matches
        buttons=sorted([m for m in matches if normalize(m.text)=='selectupgrade'],key=lambda m:center(m)[0])
        if len(buttons)!=3:
            return matches
        names={normalize(c['name']) for c in self.catalog}|{normalize(n) for n in ANVIL_PRIORITY}
        result=[m for m in matches if normalize(m.text) not in names]
        xs=[center(b)[0] for b in buttons]
        for i,button in enumerate(buttons):
            left=int((xs[i-1]+xs[i])/2) if i else 0
            right=int((xs[i+1]+xs[i])/2) if i<2 else w
            close=self.reader.read(frame,Region(left,0,right-left,max(1,center(button)[1])),
                                   scale=3,max_variants=3,min_confidence=.65,cancelled=self.stop.is_set)
            titles=[m for m in close if normalize(m.text) in names]
            result.extend(titles)
        return result

    def choose(self,matches):
        cards=offered_cards(matches,self.catalog)
        if cards:
            return choose_card(cards,self.priority,self.selected)
        anvils=offered_cards(matches,[dict(name=n,category='Anvil',tier=1) for n in ANVIL_PRIORITY])
        return min(anvils,key=lambda c:self.anvil_priority.index(c['name'])) if anvils else None

    def reset(self):
        self.selected.clear()

    def handle(self,frame):
        matches=None
        if self.header(frame) is None and self.anvil_header(frame) is None:
            if time.monotonic()-self.last_probe<.7:
                return False
            self.last_probe=time.monotonic()
            matches=self.read_choices(frame)
            if sum(normalize(m.text)=='selectupgrade' for m in matches)!=3:
                return False
        pending=None
        clicked=0
        absent=0
        logged=False
        while not self.stop.is_set():
            matches=matches if matches is not None else self.read_choices(frame)
            visible=(self.header(frame) is not None or self.anvil_header(frame) is not None
                     or sum(normalize(m.text)=='selectupgrade' for m in matches)==3)
            if not visible:
                absent+=1
                if absent>=2:
                    if pending and pending not in ANVIL_PRIORITY:
                        self.selected.add(pending)
                    return True
            else:
                absent=0
                if pending is None or time.monotonic()-clicked>=2:
                    card=self.choose(matches)
                    if card is not None:
                        if pending is not None and card['name']!=pending:
                            pending=None
                        if self.stop.is_set() or self.client.direct_click(*card['point'],frame.shape) is False:
                            raise InterruptedError()
                        self.client.park_cursor(frame.shape)
                        pending=card['name']
                        clicked=time.monotonic()
                        self.log('Selecting '+pending+'.')
                    elif not logged:
                        self.log('Waiting for readable card choices.')
                        logged=True
            if self.stop.wait(.15):
                raise InterruptedError()
            frame=self.capture()
            matches=None
        raise InterruptedError()
