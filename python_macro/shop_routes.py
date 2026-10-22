"""Per-map shop routes, separate from first-run unit-index paths."""
import json
from python_macro.pathing import decode_path

MAPS=('School Grounds','Flower Forest','Rose Kingdom','East Town')


class ShopRoutes:
    def __init__(self,root,defaults=None):
        self.root,self.defaults=root,defaults

    def path(self,map_name):
        if map_name not in MAPS:
            raise ValueError('Choose one of the four Expedition maps.')
        return self.root/(map_name.replace(' ','_')+'.json')

    def validate(self,data,map_name):
        if not isinstance(data,dict) or data.get('version')!=1 or data.get('map')!=map_name:
            raise ValueError('The route belongs to a different map or is invalid.')
        return dict(version=1,map=map_name,path=decode_path(data.get('path')))

    def load(self,map_name):
        path=self.path(map_name)
        if not path.exists() and self.defaults is not None:
            path=self.defaults/path.name
        if not path.exists():
            return None
        if path.stat().st_size>2_000_000:
            raise ValueError('Route file is too large.')
        return self.validate(json.loads(path.read_text(encoding='utf-8')),map_name)

    def save(self,map_name,raw):
        data=self.validate(dict(version=1,map=map_name,path=decode_path(raw)),map_name)
        path=self.path(map_name)
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data,indent=2),encoding='utf-8')
        temporary.replace(path)
        return path
