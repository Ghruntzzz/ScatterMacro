"""Validated, timed WASD-only paths."""
import json
import math
import time

MAX_SECONDS = 300


def decode_path(raw):
    try:
        data=json.loads(raw) if isinstance(raw,str) else raw
        if not isinstance(data,dict) or data.get('version') != 1 or data.get('mode') != 'Keyboard':
            raise ValueError()
        duration=data['duration']
        if not isinstance(duration,(int,float)) or not math.isfinite(duration) or not 0 < duration <= MAX_SECONDS:
            raise ValueError()
        events=data['events']
        if not isinstance(events,list) or not 1 <= len(events) <= 60000:
            raise ValueError()
        previous=0
        for event in events:
            if not isinstance(event,list) or len(event)<3:
                raise ValueError()
            at,kind=event[:2]
            if not isinstance(at,(int,float)) or not math.isfinite(at) or not previous <= at <= duration:
                raise ValueError()
            previous=at
            if kind=='key':
                valid=len(event)==4 and event[2] in 'WASD' and len(event[2])==1 and event[3] in (0,1)
            else:
                valid=False
            if not valid:
                raise ValueError()
        return data
    except (TypeError,KeyError,ValueError):
        raise ValueError('Invalid recorded path. Record the path again.') from None


class PathRecording:
    def __init__(self,clock=time.monotonic):
        self.clock=clock
        self.last=clock()
        self.elapsed=0.0
        self.events=[]
        self.keys=set()
        self.focused=False

    def sample(self,focused,keys=()):
        now=self.clock()
        if self.focused and focused:
            self.elapsed=min(MAX_SECONDS,self.elapsed+max(0,now-self.last))
        self.last=now
        self.focused=focused
        keys=set(keys).intersection('WASD') if focused else set()
        at=round(self.elapsed,5)
        for key in sorted(self.keys.symmetric_difference(keys)):
            self.events.append([at,'key',key,int(key in keys)])
        self.keys=keys
        return self.elapsed < MAX_SECONDS and len(self.events)<59990

    def finish(self):
        self.sample(False)
        if not self.events:
            return ''
        data=dict(version=1,mode='Keyboard',duration=max(.001,round(self.elapsed,5)),events=self.events)
        decode_path(data)
        return json.dumps(data,separators=(',',':'))


def replay_path(raw,client,stop,heartbeat=lambda:None,clock=time.monotonic):
    data=decode_path(raw)
    held=set()
    started=clock()
    pause_start=getattr(client,'focus_pause_time',0.0)
    def wait_until(at):
        while True:
            if stop.is_set():
                raise InterruptedError()
            heartbeat()
            client.check_focus()
            paused=getattr(client,'focus_pause_time',0.0)-pause_start
            remaining=at-(clock()-started-paused)
            if remaining<=0:
                return
            if stop.wait(min(.01,remaining)):
                raise InterruptedError()
    try:
        for event in data['events']:
            wait_until(event[0])
            kind=event[1]
            if kind=='key':
                key,down=event[2:]
                if down:
                    held.add(key)
                client._key(key,release=not down)
                if not down:
                    held.discard(key)
        wait_until(data['duration'])
    finally:
        errors=[]
        for key in sorted(held):
            try:
                client._key(key,release=True)
            except (OSError,RuntimeError) as error:
                errors.append(error)
        if errors:
            raise errors[0]
