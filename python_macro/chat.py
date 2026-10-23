"""Silent, client-relative chat dismissal for navigation captures."""
import cv2
import numpy as np


class ChatLocator:
    def __init__(self, assets):
        self.templates = {}
        for state in ("open", "closed"):
            image = cv2.imread(str(assets / f"chat-{state}.png"), cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise RuntimeError("Chat reference image is missing.")
            self.templates[state] = [cv2.resize(image, None, fx=s, fy=s)
                                     for s in (0.8, 1.0, 1.25, 1.5, 1.75, 2.0)]

    def __call__(self, frame):
        # Search only the Roblox top-left toolbar, not chat messages or game UI.
        roi = frame[:min(150, frame.shape[0]), :min(500, frame.shape[1]), :3]
        gray = cv2.cvtColor(np.ascontiguousarray(roi), cv2.COLOR_BGR2GRAY)
        best = {}
        for state, templates in self.templates.items():
            best[state] = (-1, None)
            for tile in templates:
                h, w = tile.shape
                if h > gray.shape[0] or w > gray.shape[1]:
                    continue
                _, score, _, p = cv2.minMaxLoc(cv2.matchTemplate(gray, tile, cv2.TM_CCOEFF_NORMED))
                if score > best[state][0]:
                    best[state] = (score, (p[0] + w // 2, p[1] + h // 2))
        state = max(best, key=lambda key: best[key][0])
        other = "closed" if state == "open" else "open"
        if best[state][0] < 0.9 or best[state][0] - best[other][0] < 0.08:
            return None, None
        return state, best[state][1]


class ChatSafeCapture:
    def __init__(self, capture, click, locate, stop):
        self.capture, self.click, self.locate, self.stop = capture, click, locate, stop

    def __call__(self):
        frame = self.capture()
        state, point = self.locate(frame)
        if state != "open" or self.stop.is_set():
            return frame
        for _ in range(2):
            if self.stop.is_set():
                return frame
            if self.click(*point, frame.shape) is False:
                self.stop.set()
                return frame
            for _ in range(6):
                if self.stop.wait(0.15):
                    return frame
                frame = self.capture()
                state, point = self.locate(frame)
                if state == "closed":
                    return frame
            # Retry only a freshly identified open icon, never a stale point.
            if state != "open":
                break
        self.stop.set()
        return frame
