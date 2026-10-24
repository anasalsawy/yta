# CPU audio/text embedder

Replacement for the suspended yta-hermes compute workload. Deploy this folder's Dockerfile as a Render web service in Oregon on the existing-budget `1c-2g` plan. The Hermes code and service remain available for rollback.

Uses google/embeddinggemma-2 with the vision encoder disabled and bfloat16 CPU weights. Returns normalized 768-dimensional vectors in the same space for audio and text. No Google inference API or per-token bill. Actual RAM fit and latency must be validated on Render; do not upgrade the plan without owner authorization.

Set a randomly generated EMBEDDING_API_KEY in Render. POST `/v1/embeddings` with a Bearer token and JSON `{"model":"google/embeddinggemma-2","input":["some text"]}`. Audio uses POST `/v1/audio/embeddings` with JSON `{"audio_base64":"<base64-encoded WAV or other libsndfile-supported file>"}`. Audio is capped at 20 seconds and resampled to 16 kHz. URLs and local paths are not accepted from clients. Inference is serialized; concurrent requests receive 429.

GET `/health` reports readiness. The server binds only after the model loads and a text inference succeeds. Do not point the consuming application here until text/audio inference, authorization, RAM usage, and latency have been checked. Existing embeddings from other models must be re-embedded or kept in separate model-tagged indexes.
