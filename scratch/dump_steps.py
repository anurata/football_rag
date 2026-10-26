import json

log_path = r"C:\Users\anuratajp\.gemini\antigravity-ide\brain\147f8a5c-e351-42c2-8ba6-20572ba40ec8\.system_generated\logs\transcript_full.jsonl"

with open(log_path, "r", encoding="utf-8") as f, open("scratch/steps_81_89.txt", "w", encoding="utf-8") as out:
    for idx, line in enumerate(f):
        data = json.loads(line)
        step = data.get("step_index")
        if step in range(80, 95):
            out.write(f"=== STEP {step} ({data.get('type')}) ===\n")
            out.write(data.get("content", "") + "\n\n")
