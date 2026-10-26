import json

log_path = r"C:\Users\anuratajp\.gemini\antigravity-ide\brain\147f8a5c-e351-42c2-8ba6-20572ba40ec8\.system_generated\logs\transcript_full.jsonl"

with open(log_path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        data = json.loads(line)
        content = data.get("content", "")
        if "15" in content and ("観点" in content or "分析" in content or "客観" in content):
            print(f"Line {idx}, Type: {data.get('type')}, Step: {data.get('step_index')}")
            # print first 200 chars
            print(content[:300].replace("\n", " "))
            print("-" * 50)
