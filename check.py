import json
data = json.loads(open('data/Denim_Tears.json', encoding='utf-8').read())
for i, p in enumerate(data['products']):
    print(i+1, p.get('image','なし')[:60], '|', p['title'][:25])