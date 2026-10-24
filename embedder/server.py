"""Authenticated CPU audio/text embedding service; no paid inference APIs."""
import base64
import binascii
import hmac
import io
import json
import os
import resource
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_ID = "google/embeddinggemma-2"
MAX_BODY = 3_000_000
LOCK = threading.Lock()
MODEL = None
KEY = os.environ.get("EMBEDDING_API_KEY", "")


def prepare_input(data):
    if data.get("model", MODEL_ID) != MODEL_ID:
        raise ValueError("Unsupported model")
    if "audio_base64" in data:
        raw = base64.b64decode(data["audio_base64"], validate=True)
        import numpy as np
        import soundfile as sf
        from scipy.signal import resample_poly
        from math import gcd
        with sf.SoundFile(io.BytesIO(raw)) as f:
            if not 8000 <= f.samplerate <= 96000 or f.channels > 2:
                raise ValueError("Unsupported audio sample rate or channels")
            if not 0 < f.frames <= 20 * f.samplerate:
                raise ValueError("Audio must be between 0 and 20 seconds")
            rate = f.samplerate
            audio = f.read(dtype="float32", always_2d=True).mean(axis=1)
        if not np.isfinite(audio).all():
            raise ValueError("Audio contains non-finite samples")
        if rate != 16000:
            divisor = gcd(rate, 16000)
            audio = resample_poly(audio, 16000 // divisor, rate // divisor).astype("float32")
        return [{"audio": audio}]
    texts = data.get("input")
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list) or not 1 <= len(texts) <= 8:
        raise ValueError("input must contain 1 to 8 strings")
    if any(not isinstance(t, str) or not t.strip() or len(t) > 8000 for t in texts):
        raise ValueError("Each input must be a nonempty string of at most 8000 characters")
    return texts


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, fmt, *args):
        # Do not log request bodies, credentials, or user content.
        pass

    def reply(self, status, body):
        payload = json.dumps(body, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self):
        return bool(KEY) and hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + KEY)

    def do_GET(self):
        if self.path in ("/", "/health"):
            return self.reply(200, {"ready": MODEL is not None, "model": MODEL_ID, "dimensions": 768,
                                    "modalities": ["text", "audio"], "device": "cpu"})
        if self.path == "/v1/models" and self.authorized():
            return self.reply(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "google"}]})
        self.reply(404, {"error": "Not found"})

    def do_POST(self):
        if not self.authorized():
            return self.reply(401, {"error": "Unauthorized"})
        if self.path not in ("/v1/embeddings", "/v1/audio/embeddings"):
            return self.reply(404, {"error": "Not found"})
        if not LOCK.acquire(blocking=False):
            return self.reply(429, {"error": "Embedder busy; retry later"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                return self.reply(413, {"error": "Request body must be between 1 and 3000000 bytes"})
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            if data.get("encoding_format", "float") != "float":
                raise ValueError("Only float encoding is supported")
            if data.get("dimensions", 768) != 768:
                raise ValueError("This endpoint returns 768 dimensions")
            inputs = prepare_input(data)
            started = time.monotonic()
            vectors = MODEL.encode(inputs, batch_size=1, normalize_embeddings=True, show_progress_bar=False)
            result = {"object": "list", "model": MODEL_ID,
                      "data": [{"object": "embedding", "index": i, "embedding": v.tolist()} for i, v in enumerate(vectors)],
                      "elapsed_ms": round((time.monotonic() - started) * 1000),
                      "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}
            self.reply(200, result)
        except (ValueError, TypeError, binascii.Error, RuntimeError) as exc:
            self.reply(400, {"error": "Invalid input or unsupported audio"})
        except Exception as exc:
            print("Embedding failed:", type(exc).__name__, flush=True)
            self.reply(500, {"error": "Embedding failed"})
        finally:
            LOCK.release()


if __name__ == "__main__":
    if len(KEY) < 32:
        raise RuntimeError("Set a strong EMBEDDING_API_KEY before starting")
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    MODEL = SentenceTransformer(os.environ.get("MODEL_PATH", MODEL_ID), device="cpu",
                                config_kwargs={"vision_config": None},
                                model_kwargs={"torch_dtype": torch.bfloat16})
    MODEL.max_seq_length = 2048
    vector = MODEL.encode(["Readiness check"], normalize_embeddings=True, show_progress_bar=False)
    assert vector.shape == (1, 768)
    print("Embedder ready; peak RSS MB:", round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024), flush=True)
    # Startup smoke test of the actual audio encoder on this Render CPU plan.
    # Uses synthetic speech, not private user data or external inference APIs.
    import subprocess
    import soundfile as sf
    import numpy as np
    test_wav = "/tmp/embedding-audio-smoke.wav"
    subprocess.run(["espeak-ng", "-s", "155", "-w", test_wav,
                    "What was the garden project password?"],
                   check=True, capture_output=True)
    with sf.SoundFile(test_wav) as audio_f:
        test_audio = audio_f.read(dtype="float32", always_2d=True).mean(axis=1)
        test_rate = audio_f.samplerate
    if test_rate != 16000:
        from scipy.signal import resample_poly
        from math import gcd
        divisor = gcd(test_rate, 16000)
        test_audio = resample_poly(test_audio, 16000 // divisor, test_rate // divisor).astype("float32")
    started_audio = time.monotonic()
    audio_vector = MODEL.encode([{"audio": test_audio}], normalize_embeddings=True,
                                show_progress_bar=False)
    audio_ms = round((time.monotonic() - started_audio) * 1000)
    assert audio_vector.shape == (1, 768) and np.isfinite(audio_vector).all()
    print("AUDIO_SMOKE_OK", json.dumps({
        "duration_s": round(len(test_audio) / 16000, 2),
        "inference_ms": audio_ms,
        "vector_dim": int(audio_vector.shape[1]),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    }), flush=True)
    # Repeated warmed-up audio benchmark. This runs once per deploy using only
    # synthesized speech; it does not access user data or any paid external API.
    # Don't hard-fail the service if cross-modal ranking quality is poor; record
    # the outcome so we can decide whether to use the model in Maya.
    audio_trials_ms = []
    for trial in range(3):
        t0 = time.monotonic()
        audio_embedding = MODEL.encode([{"audio": test_audio}],
                                       normalize_embeddings=True, show_progress_bar=False)
        audio_trials_ms.append(round((time.monotonic() - t0) * 1000))
    print("AUDIO_WARM_BENCH", json.dumps({
        "duration_s": round(len(test_audio)/16000, 2),
        "warm_trials_ms": audio_trials_ms,
        "warm_median_ms": sorted(audio_trials_ms)[len(audio_trials_ms)//2],
        "warm_best_ms": min(audio_trials_ms),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    }), flush=True)
    # Synthetic memory retrieval, comparing *audio* embeddings with text
    # documents in the same vector space, no transcription involved.
    import torch.nn.functional as F
    sample_docs = [
        "title: Garden project | text: The garden project password is cobalt seven.",
        "title: Garden watering | text: The garden plants need more water.",
        "title: Falcon project | text: The Falcon team meeting is on Thursday.",
        "title: Cafe | text: The cafe is closed on Sundays.",
    ]
    ts = time.monotonic()
    document_vectors = MODEL.encode(sample_docs, prompt_name="Document",
                                    normalize_embeddings=True, show_progress_bar=False)
    text_index_ms = round((time.monotonic()-ts)*1000)
    similarities = np.asarray(document_vectors) @ np.asarray(audio_embedding[0])
    order = np.argsort(-similarities).tolist()
    print("AUDIO_TEXT_RETRIEVAL_SMOKE", json.dumps({
        "text_index_ms": text_index_ms,
        "top_document_index": int(order[0]),
        "relevant_document_rank": int(order.index(0)+1),
        "recall_at_1": bool(order[0] == 0),
        "recall_at_3": bool(0 in order[:3]),
        "scores": [round(float(n), 4) for n in similarities.tolist()],
        "note": "One synthetic example; not a reliable retrieval accuracy benchmark",
    }), flush=True)
    # Extended CPU diagnostic: latency versus shorter speech and
    # cross-modal retrieval across more than one synthetic question.
    # Exceptions here should not prevent the API from starting.
    try:
        shorter_audio = test_audio[:16000]
        t0 = time.monotonic()
        short_vector = MODEL.encode([{"audio": shorter_audio}],
                                    normalize_embeddings=True, show_progress_bar=False)
        print("AUDIO_ONE_SECOND_BENCH", json.dumps({
            "audio_seconds": 1.0,
            "inference_ms": round((time.monotonic()-t0)*1000),
            "vector_dim": int(short_vector.shape[1]),
        }), flush=True)
        extra_checks = [
            ("When is the Falcon team meeting?", 2),
            ("On which day is the cafe closed?", 3),
            ("What do the garden plants need?", 1),
        ]
        ranks = [int(order.index(0)+1)]
        latencies_ms = [audio_trials_ms[-1]]
        for question, expected_index in extra_checks:
            subprocess.run(["espeak-ng", "-s", "155", "-w", test_wav, question],
                           check=True, capture_output=True)
            with sf.SoundFile(test_wav) as af:
                a = af.read(dtype="float32", always_2d=True).mean(axis=1)
                sr = af.samplerate
            if sr != 16000:
                g = gcd(sr, 16000)
                a = resample_poly(a, 16000//g, sr//g).astype("float32")
            t0 = time.monotonic()
            v = MODEL.encode([{"audio": a}], normalize_embeddings=True,
                             show_progress_bar=False)[0]
            latencies_ms.append(round((time.monotonic()-t0)*1000))
            ranks.append(int(np.argsort(-(np.asarray(document_vectors) @ v)).tolist().index(expected_index)+1))
        print("AUDIO_RETRIEVAL_EXTENDED", json.dumps({
            "samples": len(ranks),
            "relevant_document_ranks": ranks,
            "recall_at_1": sum(r == 1 for r in ranks)/len(ranks),
            "recall_at_3": sum(r <= 3 for r in ranks)/len(ranks),
            "query_inference_ms": latencies_ms,
            "note": "Four synthetic prompts against four synthetic documents only",
        }), flush=True)
    except Exception as exc:
        print("AUDIO_DIAGNOSTIC_ERROR", type(exc).__name__, str(exc)[:300], flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler).serve_forever()
