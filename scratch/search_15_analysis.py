import json, sys
sys.stdout.reconfigure(encoding='utf-8')

# 他の会話ファイルも探す
import glob, os

brain_dir = r'C:\Users\anuratajp\.gemini\antigravity-ide\brain'
for path in glob.glob(os.path.join(brain_dir, '*', '.system_generated', 'logs', 'transcript.jsonl')):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if '15の' in line or '15項目' in line or '多角分析' in line or '15' in line and '分析' in line:
                try:
                    data = json.loads(line)
                    t = data.get('type')
                    if t == 'USER_INPUT':
                        print(f"USER ({path}):\n{data.get('content')}\n")
                    elif t == 'PLANNER_RESPONSE' and ('15の' in (data.get('content') or '') or '多角' in (data.get('content') or '')):
                        print(f"ASSISTANT ({path}):\n{data.get('content')[:300]}\n")
                except:
                    pass
