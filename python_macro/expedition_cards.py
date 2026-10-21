"""Category-ranked card selection with per-run history and verified buttons."""
import json
from python_macro.story import normalize
from python_macro.end_screen import center
from python_macro.unit_actions import Icon
from python_macro.vision import Region

DEFAULT_PRIORITY=('Economy','Buff','DOT','Followup Attack','Payload','Summon','Elementalist')


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
        right=(xs[i+1]+bx)/2 if i<2 else float('inf')
        titles=[m for m in matches if normalize(m.text) in names
                and left<center(m)[0]<right and center(m)[1]<by]
        if len(titles)!=1:
            return []
        cards.append(dict(names[normalize(titles[0].text)],point=(bx,by)))
    return cards if len({c['name'] for c in cards})==3 else []


class CardSelector:
    def __init__(self,assets,reader,client,capture,stop,log,priority=DEFAULT_PRIORITY):
        self.catalog=json.loads((assets/'expedition-card-catalog.json').read_text())['cards']
        self.header=Icon(assets/'expedition-card-screen.png',threshold=.85,crop=(352,30,134,22))
        self.reader,self.client,self.capture,self.stop,self.log=reader,client,capture,stop,log
        self.priority=priority_order(priority)
        self.selected=set()

    def reset(self):
        self.selected.clear()

    def handle(self,frame):
        if self.header(frame) is None:
            return False
        pending=None
        absent=0
        logged=False
        while not self.stop.is_set():
            if self.header(frame) is None:
                absent+=1
                if absent>=2:
                    if pending:
                        self.selected.add(pending)
                    return True
            else:
                absent=0
                if pending is None:
                    h,w=frame.shape[:2]
                    matches=self.reader.read(frame,Region(0,0,w,h),scale=2,max_variants=1,
                                             min_confidence=.65,cancelled=self.stop.is_set)
                    card=choose_card(offered_cards(matches,self.catalog),self.priority,self.selected)
                    if card is not None:
                        if self.stop.is_set() or self.client.direct_click(*card['point'],frame.shape) is False:
                            raise InterruptedError()
                        pending=card['name']
                        self.log('Selecting '+pending+'.')
                    elif not logged:
                        self.log('Waiting for readable card choices.')
                        logged=True
            if self.stop.wait(.15):
                raise InterruptedError()
            frame=self.capture()
        raise InterruptedError()
