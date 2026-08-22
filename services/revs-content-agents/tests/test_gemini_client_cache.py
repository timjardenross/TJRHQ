import io

from PIL import Image

import src.integrations.gemini_client as gc


def _fake_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="JPEG")
    return buf.getvalue()


def test_generate_image_caches_identical_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_CACHE_DIR", tmp_path)
    fake_bytes = _fake_jpeg_bytes()
    calls = []
    monkeypatch.setattr(gc, "_call_generate_image", lambda p, a, r: calls.append(1) or fake_bytes)

    img1 = gc.generate_image("a prompt", "1:1", "1K")
    img2 = gc.generate_image("a prompt", "1:1", "1K")

    assert len(calls) == 1  # second call hit the cache, didn't call Gemini again
    assert img1.size == img2.size == (8, 8)


def test_generate_image_cache_key_includes_params(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_CACHE_DIR", tmp_path)
    fake_bytes = _fake_jpeg_bytes()
    calls = []
    monkeypatch.setattr(gc, "_call_generate_image", lambda p, a, r: calls.append(1) or fake_bytes)

    gc.generate_image("a prompt", "1:1", "1K")
    gc.generate_image("a prompt", "16:9", "1K")  # different aspect ratio - must not cache-hit

    assert len(calls) == 2


def test_generate_speech_caches_identical_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_CACHE_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(gc, "_call_generate_speech", lambda t, v: calls.append(1) or b"\x00\x00" * 100)

    gc.generate_speech("hello world")
    gc.generate_speech("hello world")

    assert len(calls) == 1
