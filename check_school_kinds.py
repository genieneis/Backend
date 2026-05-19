import json
from collections import Counter

with open("temp_db.txt", encoding="utf-8") as f:
    data = json.load(f)

schools = data["schools"]
counter = Counter(s.get("school_kind") for s in schools)

print(f"전체 학교 수: {len(schools):,}")
print(f"school_kind 종류: {len(counter)}가지\n")

for kind, count in sorted(counter.items(), key=lambda x: (x[0] is None, x[0])):
    print(f"  {kind or '(없음)':<30} {count:>5}개")
