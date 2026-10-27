import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def search_conv(cid, query):
    path = f"C:\\Users\\anuratajp\\.gemini\\antigravity-ide\\brain\\{cid}\\.system_generated\\logs\\transcript.jsonl"
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if query in line:
                    d = json.loads(line)
                    c = d.get('content') or ''
                    print(f"[{cid}] [{d.get('type')}]:\n{c[:300]}\n---")
    except Exception as e:
        print(f"Error {cid}: {e}")

search_conv('147f8a5c-e351-42c2-8ba6-20572ba40ec8', '15')
search_conv('9ce771fc-14ae-401d-b389-d47abafc0cf3', '15')
search_conv('69c79270-c9df-4a5a-b76b-f2bf2045246b', '15')
