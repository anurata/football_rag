import json

log_path = r"C:\Users\anuratajp\.gemini\antigravity-ide\brain\147f8a5c-e351-42c2-8ba6-20572ba40ec8\.system_generated\logs\transcript_full.jsonl"

with open(log_path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx in [68, 70, 72, 80, 90, 100, 110, 120, 130, 140, 150, 152]:
            data = json.loads(line)
            if data.get("type") == "PLANNER_RESPONSE" and data.get("content"):
                out_file = f"scratch/planner_response_{idx}.md"
                with open(out_file, "w", encoding="utf-8") as out:
                    out.write(data["content"])
                print(f"Saved {out_file}, len: {len(data['content'])}")
