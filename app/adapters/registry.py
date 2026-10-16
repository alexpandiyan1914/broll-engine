from app.config import settings
from app.adapters.mock import MockFootage
from app.adapters.pixabay import PixabayFootage


def get_footage_sources():
    registry = {"mock": MockFootage, "pixabay": PixabayFootage}
    names = [n.strip() for n in settings.footage_providers.split(",") if n.strip()]
    return [registry[n]() for n in names]