import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.getenv("PAMYO_MODEL", "gemma4:e4b")

MODEL_DOWN = "The local model did not answer. Is Ollama running with the model pulled?"
