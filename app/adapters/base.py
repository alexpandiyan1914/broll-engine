from dataclasses import dataclass
from typing import Protocol

@dataclass
class ClipCandidate:
    clip_id: str
    source: str
    url: str
    download_url: str
    duration: float
    width: int
    height: int
    licence: str
    author: str
    ai_generated: bool = False

class FootageSource(Protocol):
    name: str
    def search(self, query: str, orientation: str, limit: int = 8) -> list[ClipCandidate]: ...