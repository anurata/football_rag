import json, sys
sys.stdout.reconfigure(encoding='utf-8')

cid = '17b4c000-24de-44d3-9a51-2e56749160e2'
path = f"C:\\Users\\anuratajp\\.gemini\\antigravity-ide\\brain\\{cid}\\.system_generated\\logs\\transcript.jsonl"
print(f"\n==================== CONVERSATION: {cid} ====================")
try:
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            d = json.loads(line)
            t = d.get('type')
            c = d.get('content') or ''
            if t == 'USER_INPUT':
                print(f"[USER]: {c.strip()}\n---")
            elif t == 'PLANNER_RESPONSE' and any(k in c for k in ['ツール', 'バッチ', 'fetch', '取得', '構造化']):
                lines = [l.strip() for l in c.split('\n') if l.strip().startswith('#') or l.strip().startswith('*') or l.strip().startswith('-')]
                if lines:
                    print(f"[ASSISTANT]: " + " / ".join(lines[:4])[:200])
except Exception as e:
    print(f"Error {cid}: {e}")
