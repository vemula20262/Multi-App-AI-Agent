#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export HOMEBREW_NO_INSTALL_CLEANUP=1
export HOMEBREW_NO_AUTO_UPDATE=1
if ! command -v ollama >/dev/null || ! command -v whisper-cli >/dev/null; then
  if [[ "$(uname -s)" == Darwin ]] && command -v brew >/dev/null; then
    brew install ollama whisper-cpp
  else
    printf 'Install Ollama (https://ollama.com/download) and whisper.cpp (https://github.com/ggml-org/whisper.cpp), then rerun this script.\n'
    exit 1
  fi
fi
mkdir -p .runtime/models
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then
  printf 'Start ollama serve in another terminal, then rerun this script.\n'
  exit 1
fi
ollama pull "${OLLAMA_MODEL:-llama3.2:3b}"
if [[ ! -f .runtime/models/ggml-base.en.bin ]]; then
  curl -fL --retry 3 -o .runtime/models/ggml-base.en.bin.part https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
  mv .runtime/models/ggml-base.en.bin.part .runtime/models/ggml-base.en.bin
fi
printf '\nLocal models ready. Start the app with .venv/bin/python scripts/dev.py\n'
