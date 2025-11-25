import os
from pathlib import Path

# Define the path to the prompts folder
# Assumes structure: backend/utils/prompt_loader.py -> backend/prompts/
PROMPT_DIR = Path(__file__).parent.parent / "prompts"

def load_prompt(filename: str) -> str:
    """Loads a prompt template from the backend/prompts directory."""
    file_path = PROMPT_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read().strip()

# Cache the loaded prompts for efficient access
# Ensure keys match the strings used in nodes.py (e.g., get_prompt("extract"))
PROMPT_TEMPLATES = {
    "extract": load_prompt("extract.txt"),
    "synthesize": load_prompt("synthesize.txt"),
    "content": load_prompt("content.txt"),
    "verify": load_prompt("verify.txt"), # Needed for validator.py (see note below)
}

print(f"[INIT] Loaded {len(PROMPT_TEMPLATES)} prompt templates.", flush=True)

def get_prompt(name: str) -> str:
    """Retrieves a loaded prompt template by its key name."""
    if name not in PROMPT_TEMPLATES:
        raise ValueError(f"Prompt template '{name}' not found.")
    return PROMPT_TEMPLATES[name]