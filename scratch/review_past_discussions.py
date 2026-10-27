import json, sys
sys.stdout.reconfigure(encoding='utf-8')

convs = [
    '76905be6-14e1-420a-8f75-579e2190bc4b',
    '7651a061-4b53-4d5d-a1c3-5158ff29c101',
    'ebf0a0fb-6fea-4698-a83d-c1879d412e63',
    '69c79270-c9df-4a5a-b76b-f2bf2045246b',
    '147f8a5c-e351-42c2-8ba6-20572ba40ec8',
]

for cid in convs:
    path = f"C:\\Users\\anuratajp\\.gemini\\antigravity-ide\\brain\\{cid}\\.system_generated\\logs\\transcript.jsonl"
    print(f"\n==================== CONVERSATION: {cid} ====================")
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                d = json.loads(line)
                t = d.get('type')
                c = d.get('content') or ''
                if t == 'USER_INPUT':
                    print(f"[USER]: {c.strip()[:300]}\n")
                elif t == 'PLANNER_RESPONSE' and any(k in c for k in ['ルール', '要件', '客観', '多角', '15', '設計', 'データ分析', '因果']):
                    # Look for headings or bullet points
                    lines = [l.strip() for l in c.split('\n') if l.strip().startswith('#') or l.strip().startswith('*') or l.strip().startswith('-')]
                    if lines:
                        print(f"[ASSISTANT SUMMARY]: " + " / ".join(lines[:6])[:300])
    except Exception as e:
        print(f"Error {cid}: {e}")
