"""Elemental Boss Rush buffs, ranked independently of expedition cards."""
import time

from python_macro.expedition_cards import CardSelector, offered_cards
from python_macro.story import normalize
from python_macro.unit_actions import Icon
from python_macro.vision import Region

ELEMENTS = ('Light', 'Dark', 'Flame', 'Neutral', 'Hydro', 'Terra', 'Storm', 'Gale')
CARD_PRIORITY = tuple(f'{element} {buff}' for buff in ('Damage', 'Element Damage', 'Speed', 'Crit', 'Range', 'Resistance') for element in ELEMENTS)


def boss_card_order(values):
    values = values.split('|') if isinstance(values, str) else values or ()
    return list(dict.fromkeys([v for v in values if v in CARD_PRIORITY] + list(CARD_PRIORITY)))


class BossCardSelector(CardSelector):
    def __init__(self, assets, reader, client, capture, stop, log, priority=()):
        self.catalog = [dict(name=name, category='Element', tier=1) for name in CARD_PRIORITY]
        self.header = Icon(assets / 'boss-rush-card-screen.png', threshold=.85, crop=(406, 23, 114, 25))
        self.anvil_header = lambda frame: None
        self.reader, self.client, self.capture, self.stop, self.log = reader, client, capture, stop, log
        self.priority = boss_card_order(priority)
        self.selected = set()
        self.last_probe = self.last_header_probe = 0

    def choose(self, matches):
        cards = offered_cards(matches, self.catalog)
        return min(cards, key=lambda card: self.priority.index(card['name'])) if cards else None

    def handle(self, frame):
        if self.header(frame) is None:
            if time.monotonic() - self.last_header_probe < .8:
                return False
            self.last_header_probe = time.monotonic()
            h, w = frame.shape[:2]
            matches = self.reader.read(frame, Region(w // 3, 0, w // 3, h // 3),
                                       scale=2, max_variants=1, min_confidence=.65,
                                       cancelled=self.stop.is_set)
            if not any(normalize(m.text) == 'pickcard' for m in matches):
                return False
            self.last_probe = 0
        return super().handle(frame)
