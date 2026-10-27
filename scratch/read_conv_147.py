import json, sys
sys.stdout.reconfigure(encoding='utf-8')

path = r"C:\Users\anuratajp\.gemini\antigravity-ide\brain\147f8a5c-e351-42c2-8ba6-20572ba40ec8\.system_generated\logs\transcript.jsonl"
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        d = json.loads(line)
        t = d.get('type')
        c = d.get('content') or ''
        if t == 'USER_INPUT':
            print(f"USER:\n{c}\n===")
        elif t == 'PLANNER_RESPONSE' and ('15' in c or '多角' in c or '客観' in c):
            # print heading or summary
            lines = [l for l in c.split('\n') if l.strip().startswith('#') or '15' in l or '客観' in l or '多角' in l]
            if lines:
                print(f"ASSISTANT:\n" + "\n".join(lines[:5]) + "\n---")
