"""Conservative trait and anvil planning; unknown prices never authorize buys."""
from dataclasses import dataclass

TRAITS=('Unbound','Foresaken','Draconic','Primordial')


@dataclass(frozen=True)
class ShopItem:
    name: str
    price: int | None
    point: tuple


def purchase_plan(items,yen):
    if not isinstance(yen,int) or isinstance(yen,bool) or yen<0:
        return []
    traits=[item for item in items if item.name in TRAITS]
    choices=sorted(traits,key=lambda item:TRAITS.index(item.name))
    if not traits:
        choices.extend(item for item in items if item.name=='Anvil')
    plan=[]
    for item in choices:
        if isinstance(item.price,int) and not isinstance(item.price,bool) and 0<item.price<=yen:
            plan.append(item)
            yen-=item.price
    return plan


def next_purchase(items,yen):
    """Execute at most one returned item, then reread stock, prices and balance.

    Anvils have no per-stock cap: a later scan can offer the same anvil at its
    increased price. A previous plan must never be replayed as a purchase batch.
    """
    plan=purchase_plan(items,yen)
    return plan[0] if plan else None


def should_refresh(items,refreshes_left,already_refreshed):
    return (not already_refreshed and isinstance(refreshes_left,int) and refreshes_left>0
            and not any(item.name in (*TRAITS,'Anvil') for item in items))
