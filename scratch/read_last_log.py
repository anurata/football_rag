import json, sys
sys.stdout.reconfigure(encoding='utf-8')
path = r'C:\Users\anuratajp\.gemini\antigravity-ide\brain\636b944e-cbea-42c6-944e-46a5ef27d7f5\.system_generated\logs\transcript.jsonl'
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()
for line in lines[-30:]:
    data = json.loads(line)
    t = data.get('type')
    if t in ('USER_INPUT', 'PLANNER_RESPONSE'):
        c = data.get('content') or ''
        print(f"[{t}]:\n{c[:500]}\n")
