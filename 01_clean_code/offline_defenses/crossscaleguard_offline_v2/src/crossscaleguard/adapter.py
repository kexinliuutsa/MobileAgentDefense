"""Native duck-typed event/action interface; event times are seconds and microseconds."""
class Event:
    __slots__ = ("t", "time", "timestamp", "timestamp_us", "x", "y")

    def __init__(self, t, x, y):
        # getevent timestamp is in seconds; frozen feature extractor expects microseconds.
        self.t = float(t)
        self.time = float(t)
        self.timestamp = float(t)
        self.timestamp_us = float(t) * 1_000_000.0
        self.x = float(x)
        self.y = float(y)

class Action:
    __slots__ = (
        "events", "points",
        "start_time", "end_time", "duration",
        "start_x", "start_y", "end_x", "end_y",
        "displacement", "path_length", "mean_speed",
        "type", "action_type",
    )

    def __init__(self, gesture):
        self.events = [Event(t, x, y) for t, x, y in gesture["points"]]
        self.points = self.events

        self.start_time = float(gesture["start_time"])
        self.end_time = float(gesture["end_time"])
        self.duration = float(gesture["duration"])

        self.start_x = float(gesture["start_x"])
        self.start_y = float(gesture["start_y"])
        self.end_x = float(gesture["end_x"])
        self.end_y = float(gesture["end_y"])

        self.displacement = float(gesture["displacement"])
        self.path_length = float(gesture["path_length"])
        self.mean_speed = float(gesture["mean_speed"])

        self.type = "swipe" if self.displacement > 5 else "tap"
        self.action_type = self.type

    def __iter__(self):
        return iter(self.events)

    def __len__(self):
        return len(self.events)

    def __getitem__(self, i):
        return self.events[i]

def to_native_session(gestures):
    return [Action(g) for g in gestures]
