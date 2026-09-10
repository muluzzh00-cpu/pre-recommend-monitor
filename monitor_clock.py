from datetime import datetime
from zoneinfo import ZoneInfo

class PeriodEnded(Exception):
    pass

class MonitorClock:
    def __init__(self, settings, now=None):
        self.settings = settings['monitoring']
        self.tz = ZoneInfo(self.settings['timezone'])
        self._now = now
    def now(self):
        return self._now.astimezone(self.tz) if self._now else datetime.now(self.tz)
    def status(self):
        start = datetime.fromisoformat(self.settings['start_date']).replace(tzinfo=self.tz)
        end = datetime.fromisoformat(self.settings['end_date']).replace(tzinfo=self.tz)
        return 'ended' if self.now() > end else 'before' if self.now() < start else 'active'
    def guard(self):
        if self.status() != 'active':
            raise PeriodEnded('Monitoring period has ended.' if self.status() == 'ended' else 'Monitoring period has not started.')
