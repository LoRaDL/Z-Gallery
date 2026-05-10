"""
临时脚本：将 downloads 下 MMDD-MMDD 格式的文件夹重命名为 YYMMDD-YYMMDD
规则：月份 <= 6 → 26年，月份 > 6 → 25年
"""
import os
import re
import shutil

DOWNLOADS = os.path.join(os.path.dirname(__file__), "downloads")

def get_year(mm: str) -> str:
    return "26" if int(mm) <= 6 else "25"

pattern = re.compile(r"^(\d{2})(\d{2})-(\d{2})(\d{2})$")

for name in os.listdir(DOWNLOADS):
    m = pattern.match(name)
    if not m:
        continue
    mm1, dd1, mm2, dd2 = m.groups()
    yy1 = get_year(mm1)
    yy2 = get_year(mm2)
    new_name = f"{yy1}{mm1}{dd1}-{yy2}{mm2}{dd2}"
    src = os.path.join(DOWNLOADS, name)
    dst = os.path.join(DOWNLOADS, new_name)
    print(f"{name} -> {new_name}")
    shutil.move(src, dst)

print("Done.")
