"""临时脚本：测试 twitter_metadata_parser 能否解析 batch1 的 JSON 文件"""
import sys, json, os, glob

sys.path.insert(0, r'c:\Users\21266\Desktop\zoo\galleryManager')
import twitter_metadata_parser

batch_dir = r'c:\Users\21266\Desktop\zoo\galleryManager\tools\batch_twitter\Digger_import\batch1'

test_files = [
    'D3jP9otUcAEQfhg.jpg.json',    # 老文件，简单author，有内容
    'G--C7RBWMAA-L05.jpg.json',    # 富author，有内容
    'G7iu_pKbIAEqTdp.jpg.json',    # content含hashtag
    'G8a9O8eakAQq8ZZ.jpg.json',    # content为空
]

for fname in test_files:
    path = os.path.join(batch_dir, fname)
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    num = data.get('num', 1)
    count = data.get('count', 1)
    result = twitter_metadata_parser.parse_twitter_metadata(
        data,
        image_position=num,
        total_images=count,
        is_multi_image_post=(count > 1)
    )

    print(f'=== {fname} ===')
    for k, v in result.items():
        print(f'  {k:20s}: {str(v)[:100]}')
    print()

# 全量检查
print('--- 全量检查 ---')
all_jsons = glob.glob(os.path.join(batch_dir, '*.json'))
missing_artist = 0
missing_date = 0
missing_url = 0
empty_title = 0
errors = []

for path in all_jsons:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        num = data.get('num', 1)
        count = data.get('count', 1)
        r = twitter_metadata_parser.parse_twitter_metadata(data, num, count, count > 1)
        if not r['artist']:
            missing_artist += 1
        if not r['publication_date']:
            missing_date += 1
        if not r['source_url']:
            missing_url += 1
        if not r['title']:
            empty_title += 1
    except Exception as e:
        errors.append((os.path.basename(path), str(e)))

total = len(all_jsons)
print(f'总计: {total} 个文件')
print(f'  缺 artist:          {missing_artist} ({missing_artist*100//total}%)')
print(f'  缺 publication_date:{missing_date} ({missing_date*100//total}%)')
print(f'  缺 source_url:      {missing_url} ({missing_url*100//total}%)')
print(f'  空 title:           {empty_title} ({empty_title*100//total}%)')
print(f'  解析错误:           {len(errors)}')
for fname, err in errors[:5]:
    print(f'    {fname}: {err}')
