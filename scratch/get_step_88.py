import json, sys
sys.stdout.reconfigure(encoding='utf-8')

path = r"C:\Users\anuratajp\.gemini\antigravity-ide\brain\147f8a5c-e351-42c2-8ba6-20572ba40ec8\.system_generated\logs\transcript.jsonl"
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        d = json.loads(line)
        idx = d.get('step_index', 0)
        if 80 <= idx <= 100:
            c = d.get('content') or ''
            if '15' in c or 'ゲームフロー' in c or '客観' in c:
                print(f"=== STEP {idx} ===")
                print(c[:3000])
                print("\n" + "="*50 + "\n")
