"""Live contract, authorization, and speech-to-text retrieval check."""
import base64
import json
import math
import os
import time
import urllib.error
import urllib.request

BASE = os.environ["EMBEDDER_URL"].rstrip("/")
KEY = os.environ["EMBEDDING_API_KEY"]


def request(path, body=None, auth=True):
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = "Bearer " + KEY
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=180) as response:
        data = json.load(response)
    print(path, "wall_ms", round((time.monotonic() - started) * 1000),
          "inference_ms", data.get("elapsed_ms"), "peak_rss_mb", data.get("peak_rss_mb"), flush=True)
    return data


health = request("/health")
assert health["ready"] and health["dimensions"] == 768
try:
    request("/v1/embeddings", {"input": "authentication check"}, auth=False)
    raise AssertionError("Unauthenticated request was accepted")
except urllib.error.HTTPError as exc:
    assert exc.code == 401
texts = ["Roses are red, violets are blue.", "A car engine is being repaired in a garage."]
data = request("/v1/embeddings", {"input": texts})
vectors = [d["embedding"] for d in data["data"]]
assert len(vectors) == 2
for v in vectors:
    assert len(v) == 768 and all(math.isfinite(x) for x in v)
    assert abs(sum(x*x for x in v) - 1) < 0.01
with open(os.environ["TEST_AUDIO_PATH"], "rb") as f:
    audio = base64.b64encode(f.read()).decode()
data = request("/v1/audio/embeddings", {"audio_base64": audio})
av = data["data"][0]["embedding"]
assert len(av) == 768 and all(math.isfinite(x) for x in av)
assert abs(sum(x*x for x in av) - 1) < 0.01
similarities = [sum(a*b for a,b in zip(av,v)) for v in vectors]
print("Speech/text similarities:", similarities, flush=True)
assert similarities[0] > similarities[1], "Speech should match its transcript more closely than an unrelated sentence"
print("PASS: auth, text, audio, cross-modal retrieval", flush=True)
