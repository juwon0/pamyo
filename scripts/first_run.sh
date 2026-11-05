#!/usr/bin/env bash
# First run in one command (macOS/Linux): Ollama -> Gemma 4 -> the haunted repository -> three questions.
#   bash scripts/first_run.sh
#   PAMYO_MODEL=gemma4:e4b bash scripts/first_run.sh   # pick the model yourself
set -euo pipefail
cd "$(dirname "$0")/.."

OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
MODEL="${PAMYO_MODEL:-}"

step() { printf '\n▶ %s\n' "$*"; }
ollama_up() { curl -fsS "$OLLAMA_URL/api/version" >/dev/null 2>&1; }

# 1. Ollama
if ! command -v ollama >/dev/null 2>&1; then
  if [[ "$(uname)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    step "Installing Ollama (brew)"
    brew install ollama
  else
    echo "Ollama is missing. Install it from https://ollama.com/download and run this again."
    exit 1
  fi
fi
if ! ollama_up; then
  step "Starting Ollama"
  if [[ "$(uname)" == "Darwin" && -d /Applications/Ollama.app ]]; then
    open -a Ollama
  else
    nohup ollama serve >first-run-ollama.log 2>&1 &
  fi
  for _ in $(seq 1 30); do ollama_up && break; sleep 1; done
  ollama_up || { echo "Ollama does not answer. See first-run-ollama.log."; exit 1; }
fi

# 2. Model: the 12B follows the quoting rules more closely if there's room for it.
if [[ -z "$MODEL" ]]; then
  if [[ "$(uname)" == "Darwin" ]]; then
    mem_gb=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
  else
    mem_gb=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 ))
  fi
  if (( mem_gb >= 16 )); then MODEL="gemma4:12b"; else MODEL="gemma4:e4b"; fi
  step "${mem_gb} GB of memory, so using $MODEL"
fi
step "Pulling $MODEL (first time only; it is several GB)"
ollama pull "$MODEL"

# 3. uv
if ! command -v uv >/dev/null 2>&1; then
  step "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# 4. The haunted repository: five years of a made-up shop's order service, everyone who wrote it gone.
haunted="$(mktemp -d "${TMPDIR:-/tmp}/pamyo-XXXXXX")/dalbit-orders"
step "Building the haunted repository in $haunted"
uv run python scripts/make_haunted_repo.py "$haunted" >/dev/null

# 5. Three questions: a reason in Korean, a promise to a customer, and a line nobody explained.
ask() { PAMYO_MODEL="$MODEL" OLLAMA_URL="$OLLAMA_URL" uv run pamyo why "$haunted/$1" "$2"; }
step "pamyo why orders/export.py:10 \"Why cp949 and not UTF-8? Can I switch it?\""
ask orders/export.py:10 "Why cp949 and not UTF-8? Can I switch it?"
step "pamyo why orders/users.py:7 \"Why is user 1043 never blocked?\""
ask orders/users.py:7 "Why is user 1043 never blocked?"
step "pamyo why orders/coupons.py:5 \"WELCOME2020은 왜 반값이야?\""
ask orders/coupons.py:5 "WELCOME2020은 왜 반값이야?"

step "Now ask about your own code:"
echo "  PAMYO_MODEL=$MODEL uv run pamyo why path/to/your/repo/file.py:42 \"why is this here?\""
echo "  (or 'uv tool install .' once, then just: pamyo why file.py:42)"
