import json
try:
    with open('video_meta.json', encoding='utf-8') as f:
        d = json.load(f)
        print("TITLE:", d.get("title"))
        print("DESC:", d.get("description")[:200])
except Exception as e:
    print(e)
