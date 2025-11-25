import json
from pathlib import Path
from datetime import datetime
import sys


def log_node_execution(
    node_name: str,
    inputs: dict,
    outputs: dict,
    prompt: str = None,
    model_config: dict = None,
    human_decision: dict = None
):
    """
    Log node execution with full orchestration details.
    Captures: Timestamp, Inputs, Prompt, Output, Model Settings, Human Decisions.
    """
    timestamp = datetime.now().isoformat()
    
    # 1. Construct the structured log entry (for file storage)
    log_entry = {
        "node": node_name,
        "timestamp": timestamp,
        "inputs": inputs,
        "prompt": prompt, # Store full prompt in JSON, truncate in console
        "outputs": outputs,
        "model_settings": model_config or {"type": "deterministic", "details": "N/A"},
        "human_decision": human_decision or "N/A"
    }
    
    # 2. Write to JSONL file (Persistent Log)
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"run_{datetime.now().strftime('%Y%m%d')}.jsonl"
    
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry) + '\n')
    
    # 3. Console Output (Visual Orchestration Style)
    # Matches your requested format: NODE -> OUTPUT -> HITL
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] NODE: {node_name.upper()}", flush=True)
    
    # Print Inputs (Brief)
    input_str = str(inputs)[:100] + "..." if len(str(inputs)) > 100 else str(inputs)
    print(f"   INPUTS: {input_str}", flush=True)
    
    # Print Prompt (Brief)
    if prompt:
        print(f"   PROMPT: {prompt[:50].replace(chr(10), ' ')}...", flush=True)
        
    # Print Model Settings
    if model_config:
        print(f"   MODEL: {model_config.get('model', 'unknown')} (temp={model_config.get('temperature', 0)})", flush=True)

    # Print Output (Brief)
    output_str = str(outputs)[:150] + "..." if len(str(outputs)) > 150 else str(outputs)
    print(f"   OUTPUT: {output_str}", flush=True)
    
    # Print Human Decision (High Visibility)
    if human_decision:
        print(f"   👑 HITL DECISION: {human_decision}", flush=True)

    print("-" * 40, flush=True)
    
    return log_entry