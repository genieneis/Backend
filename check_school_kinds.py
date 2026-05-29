import json
from collections import Counter, defaultdict

with open("temp_db.txt", encoding="utf-8") as f:
    data = json.load(f)

schools = data["schools"]
counter = Counter(s.get("school_kind") for s in schools)

print(f"전체 학교 수: {len(schools):,}")
print(f"school_kind 종류: {len(counter)}가지\n")

for kind, count in sorted(counter.items(), key=lambda x: (x[0] is None, x[0])):
    print(f"  {kind or '(없음)':<30} {count:>5}개")


def classify(kind) -> str:
    if not kind:
        return "etc"
    if "초등" in kind or "(초)" in kind:
        return "elementary"
    if "중학교" in kind or "(중)" in kind or "중학" in kind:
        return "middle"
    if "고등학교" in kind or "(고)" in kind or "고등기술" in kind:
        return "high"
    if "특수" in kind:
        return "special"
    return "etc"


category_counter: Counter = Counter()
category_kinds: defaultdict[str, set] = defaultdict(set)

for s in schools:
    kind = s.get("school_kind")
    cat = classify(kind)
    category_counter[cat] += 1
    category_kinds[cat].add(kind or "(없음)")

print("\n── 5종류 분류 결과 ──────────────────────────")
for cat in ("elementary", "middle", "high", "special", "etc"):
    kinds = sorted(category_kinds[cat])
    print(f"\n  {cat} ({category_counter[cat]}개)")
    for k in kinds:
        print(f"    - {k}")
