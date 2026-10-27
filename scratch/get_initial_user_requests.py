import json, sys
sys.stdout.reconfigure(encoding='utf-8')

for cid in ['76905be6-14e1-420a-8f75-579e2190bc4b', '7651a061-4b53-4d5d-a1c3-5158ff29c101', 'ebf0a0fb-6fea-4698-a83d-c1879d412e63']:
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
    except Exception as e:
        print(f"Error {cid}: {e}")
