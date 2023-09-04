from dataclasses import dataclass
from datetime import datetime


@dataclass
class Stream:
    channel_name: str
    title: str
    started_at: datetime
