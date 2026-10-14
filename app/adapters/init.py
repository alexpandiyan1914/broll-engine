from app.config import settings
from .mock import MockFootage

def get_footage_sources():
    registry = {"mock": MockFootage}   # add "pexels", "pixabay" later
    return [registry[n.strip()]() for n in settings.footage_providers.split(",")]