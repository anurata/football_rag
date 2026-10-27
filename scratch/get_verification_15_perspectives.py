import json, sys
sys.stdout.reconfigure(encoding='utf-8')

path = r"C:\Users\anuratajp\.gemini\antigravity-ide\brain\147f8a5c-e351-42c2-8ba6-20572ba40ec8\.system_generated\logs\transcript.jsonl"
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        d = json.loads(line)
        c = d.get('content') or ''
        if '15' in c and ('客観データ' in c or '多角分析' in c or 'ゲームフロー' in c):
            if d.get('type') == 'PLANNER_RESPONSE':
                print(f"=== STEP {d.get('step_index')} ===")
                # Print first 2000 chars of this planner response
                print(c[:2000])
                print("\n" + "="*50 + "\n")
