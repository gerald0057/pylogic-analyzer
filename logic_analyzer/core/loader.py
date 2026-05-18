import numpy as np


class Waveform:
    def __init__(self, times, signals, column_names):
        self.times = times.astype(np.float64)
        self.signals = signals.astype(np.uint8)
        self.column_names = list(column_names)
        self.clipped = False

    @classmethod
    def load(cls, filepath):
        with open(filepath, 'r') as f:
            skiprows = 0
            for line in f:
                if line.startswith(';'):
                    skiprows += 1
                else:
                    break

        raw = np.loadtxt(filepath, delimiter=',', skiprows=skiprows + 1, dtype=str)
        column_names = [c.strip() for c in raw[0]]
        data = raw[1:].astype(np.float64)

        times = data[:, 0]
        signals = data[:, 1:].astype(np.uint8)

        return cls(times, signals, column_names[1:])

    def get_signal(self, name):
        idx = self.column_names.index(name)
        return self.signals[:, idx]

    def slice(self, start_time=None, end_time=None):
        i0 = 0 if start_time is None else int(np.searchsorted(self.times, start_time, side='left'))
        i1 = len(self.times) if end_time is None else int(np.searchsorted(self.times, end_time, side='right'))

        w = Waveform(self.times[i0:i1], self.signals[i0:i1], self.column_names)
        w.clipped = True
        return w
