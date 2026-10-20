from app.config import settings
from .mock import MockFootage
from .pexels import PexelsFootage
from .pixabay import PixabayFootage


def get_footage_sources():
    registry = {
        "mock": MockFootage,
        "pexels": PexelsFootage,
        "pixabay": PixabayFootage,
    }
    names = [n.strip() for n in settings.footage_providers.split(",") if n.strip()]