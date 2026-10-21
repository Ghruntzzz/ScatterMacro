"""Validated, timed WASD and relative-mouse paths. No arbitrary key playback."""
import json
import math
import time

MODES = ('Keyboard','Mouse','Both')
MAX_SECONDS = 300


def decode_path(raw):
    try:
        data=json.loads(raw) if isinstance(raw,str) else raw
        if not isinstance(data,dict) or data.get('version') != 1 or data.get('mode') not in MODES:
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
                valid=len(event)==4 and event[2] in 'WASD' and len(event[2])==1 and event[3] in (0,1) and data['mode']!='Mouse'
            elif kind=='look':
                valid=len(event)==3 and event[2] in (0,1) and data['mode']!='Keyboard'
            elif kind=='mouse':
                valid=len(event)==4 and all(isinstance(v,int) and abs(v)<=32767 for v in event[2:]) and data['mode']!='Keyboard'
            else:
                valid=False
            if not valid:
                raise ValueError()
        return data
    except (TypeError,KeyError,ValueError):
        raise ValueError('Invalid recorded path. Record the path again.') from None


class PathRecording:
    def __init__(self,mode,clock=time.monotonic):
        if mode not in MODES:
            raise ValueError('Choose Keyboard, Mouse, or Both.')
        self.mode,self.clock=mode,clock
        self.last=clock()
        self.elapsed=0.0
        self.events=[]
        self.keys=set()
        self.look=False
        self.focused=False

    def sample(self,focused,keys=(),look=False,dx=0,dy=0):
        now=self.clock()
        if self.focused and focused:
            self.elapsed=min(MAX_SECONDS,self.elapsed+max(0,now-self.last))
        self.last=now
        self.focused=focused
        keys=set(keys).intersection('WASD') if focused and self.mode!='Mouse' else set()
        look=bool(look and focused and self.mode!='Keyboard')
        at=round(self.elapsed,5)
        for key in sorted(self.keys.symmetric_difference(keys)):
            self.events.append([at,'key',key,int(key in keys)])
        if look!=self.look:
            self.events.append([at,'look',int(look)])
        self.keys,self.look=keys,look
        if focused and self.mode!='Keyboard' and (dx or dy):
            if abs(dx)<=32767 and abs(dy)<=32767:
                previous=self.events[-1] if self.events else None
                if (previous is not None and previous[1]=='mouse' and int(previous[0]*100)==int(at*100)
                        and abs(previous[2]+dx)<=32767 and abs(previous[3]+dy)<=32767):
                    previous[2]+=int(dx)
                    previous[3]+=int(dy)
                else:
                    self.events.append([at,'mouse',int(dx),int(dy)])
        return self.elapsed < MAX_SECONDS and len(self.events)<59990

    def finish(self):
        self.sample(False)
        if not self.events:
            return ''
        data=dict(version=1,mode=self.mode,duration=max(.001,round(self.elapsed,5)),events=self.events)
        decode_path(data)
        return json.dumps(data,separators=(',',':'))


def replay_path(raw,client,stop,heartbeat=lambda:None,clock=time.monotonic):
    data=decode_path(raw)
    held=set()
    look=False
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
            elif kind=='look':
                look=bool(event[2])
                client._send_mouse(0x0008 if look else 0x0010)
            else:
                client._send_mouse(0x0001,dx=event[2],dy=event[3])
        wait_until(data['duration'])
    finally:
        errors=[]
        for key in sorted(held):
            try:
                client._key(key,release=True)
            except (OSError,RuntimeError) as error:
                errors.append(error)
        if look:
            try:
                client._send_mouse(0x0010)
            except (OSError,RuntimeError) as error:
                errors.append(error)
        if errors:
            raise errors[0]
