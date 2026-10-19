"""Independent read-only HUD/end-screen worker; never injects input."""
from threading import Event, Lock, Thread
import time

from python_macro.end_screen import EndScreenReader


class MatchMonitor:
    def __init__(self, capture, assets, status, reader_factory=None):
        self.capture, self.assets, self.status = capture, assets, status
        self.reader_factory = reader_factory
        self.stop = Event()
        self.lock = Lock()
        self.state = {"wave": None, "reward": False, "outcome": None}
        self.generation = 0
        self.enabled = False
        self.thread = Thread(target=self.run, name="match-monitor", daemon=True)

    def start(self):
        self.thread.start()

    def reset(self):
        with self.lock:
            self.generation += 1
            self.enabled = True
            self.state = {"wave": None, "reward": False, "outcome": None}

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def close(self):
        self.stop.set()
        self.thread.join()

    def run(self):
        from python_macro.ocr import TextReader
        from python_macro.story_ingame import HudReader
        try:
            reader = (self.reader_factory or TextReader)()
            hud = HudReader(reader, self.stop, self.assets)
            end = EndScreenReader(reader, self.stop)
            previous_wave = previous_result = None
            last_generation = -1
            while not self.stop.is_set():
                with self.lock:
                    generation = self.generation
                    enabled = self.enabled
                if not enabled:
                    if self.stop.wait(.1):
                        return
                    continue
                if generation != last_generation:
                    previous_wave = previous_result = None
                    hud.wave_region = None
                    last_generation = generation
                frame = self.capture()
                if frame is None:
                    if self.stop.wait(.15):
                        return
                    continue
                wave = hud.wave(frame)
                trusted = wave if wave is not None and wave == previous_wave else None
                previous_wave = wave
                reading = end.read(frame)
                outcome = reading["outcome"] if reading["outcome"] == previous_result else None
                previous_result = reading["outcome"]
                with self.lock:
                    if generation != self.generation or self.stop.is_set():
                        continue
                    self.state.update(wave=trusted or self.state["wave"],
                                      reward=reading["reward"],
                                      outcome=outcome or self.state["outcome"],
                                      observed=time.monotonic())
                    self.status({"wave": trusted, "yen": None, "eligible_indexes": []})
                if self.stop.wait(.15):
                    return
        except Exception as error:
            with self.lock:
                self.state["error"] = str(error)
