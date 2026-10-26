import json

log_path = r"C:\Users\anuratajp\.gemini\antigravity-ide\brain\147f8a5c-e351-42c2-8ba6-20572ba40ec8\.system_generated\logs\transcript_full.jsonl"

with open(log_path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        data = json.loads(line)
        if data.get("type") == "USER_INPUT":
            print(f"Step {data.get('step_index')}: {data.get('content')[:150]}")
        elif data.get("type") == "PLANNER_RESPONSE" and data.get("content"):
            content = data.get("content")
            if "15" in content and "観点" in content:
                print(f"  PLANNER step {data.get('step_index')}: {content[:100]}...")
