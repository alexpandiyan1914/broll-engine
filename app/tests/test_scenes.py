from app.pipeline.scenes import words_to_scenes
from app.pipeline.captions import build_srt


def W(word, s, e):
    return {"word": word, "start": s, "end": e}


WORDS = [W("Save", 0.2, 0.5), W("money", 0.5, 1.0), W("now.", 1.0, 3.0),
         W("Track", 3.2, 3.6), W("spending", 3.6, 4.2), W("weekly.", 4.2, 6.5)]


def test_scenes_cover_all_audio_and_split_on_sentences():
    sc = words_to_scenes(WORDS, 7.0, min_len=2.0)
    assert [s["text"] for s in sc] == ["Save money now.", "Track spending weekly."]
    assert sc[0]["start"] == 0.0 and sc[-1]["end"] == 7.0
    assert sc[0]["end"] == sc[1]["start"]


def test_short_scenes_are_merged():
    sc = words_to_scenes(WORDS, 7.0, min_len=5.0)
    assert len(sc) == 1


def test_srt_format():
    srt = build_srt(WORDS)
    assert "00:00:00,200 --> 00:00:03,000" in srt