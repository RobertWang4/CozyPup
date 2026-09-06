# Emergency classifier sidecar: llama-server + the quantized fine-tuned model.
#
# Build context is backend/ (see cloudbuild.yaml, which first copies the GGUF from
# gs://cozypup-models/emergency-clf/ into nano/serve/model.gguf). The model is baked
# into the image so cold starts need no network fetch; 610 MB Q8 keeps the image small.
#
# Local test:
#   docker build -f nano/serve/Dockerfile -t clf . && docker run -p 8081:8081 clf
#   curl localhost:8081/health
FROM ghcr.io/ggml-org/llama.cpp:server

COPY nano/serve/model.gguf /models/clf.gguf
COPY nano/serve/grammar.gbnf /models/grammar.gbnf

ENV LLAMA_ARG_MODEL=/models/clf.gguf \
    LLAMA_ARG_CTX_SIZE=512 \
    LLAMA_ARG_THREADS=2 \
    LLAMA_ARG_N_PARALLEL=2 \
    LLAMA_ARG_HOST=0.0.0.0 \
    LLAMA_ARG_PORT=8081

# --grammar-file: the model can only ever emit "true" or "false".
# --no-webui / --metrics off: nothing but /completion and /health.
CMD ["--grammar-file", "/models/grammar.gbnf", "--no-webui"]
