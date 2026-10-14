from .base import ClipCandidate

class MockFootage:
    name = "mock"
    def search(self, query, orientation, limit=8):
        return [ClipCandidate(f"mock-{i}-{query[:10]}", "mock", "https://example.test",
                "https://example.test/clip.mp4", 6.0, 1920, 1080,
                "mock-licence", "tester") for i in range(limit)]