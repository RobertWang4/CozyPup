"""Validate + summarize seeds.yaml and gen/*.yaml. Usage: python -m nano.check_data"""
import re, glob, collections, sys
import yaml

DATA = "nano/data"
TAGS = set("seizure breathing toxin trauma bleeding gdv urinary shock heat neuro panic mild record reminder task profile "
           "question knowledge places email language correction delete confirm chitchat past hypothetical other_owner "
           "managed multi gray typo voice en keyword_trap edge emergency e2e scenario db".split())
KEYWORDS = re.compile(r"抽搐|中毒|呼吸困难|seizure|poison|breath", re.I)
norm = lambda s: re.sub(r"[\s，。！？,.!?~～]+", "", str(s).strip().lower())

def load(path):
    rows = yaml.safe_load(open(path)) or []
    errs = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict) or "msg" not in r or "label" not in r:
            errs.append(f"{i}: bad row {r!r}"[:120]); continue
        if not isinstance(r["label"], bool): errs.append(f"{i}: label not bool: {r['label']!r}")
        if not str(r["msg"]).strip(): errs.append(f"{i}: empty msg")
    return rows, errs

def main():
    files = [f"{DATA}/seeds.yaml"] + sorted(glob.glob(f"{DATA}/gen/*.yaml"))
    seen, total_dups = {}, 0
    print(f"{'file':28} {'n':>5} {'true':>5} {'en':>5} {'gray':>5} {'dup':>5}  true_no_kw  errs")
    for f in files:
        rows, errs = load(f)
        name = f.split("/")[-1]
        dups = 0
        for r in rows:
            k = norm(r["msg"])
            if k in seen: dups += 1; r["_dup"] = seen[k]
            else: seen[k] = name
        t = [r for r in rows if r["label"] is True]
        no_kw = sum(1 for r in t if not KEYWORDS.search(r["msg"]))
        print(f"{name:28} {len(rows):5} {len(t):5} {sum('en' in r.get('tags',[]) for r in rows):5} "
              f"{sum('gray' in r.get('tags',[]) for r in rows):5} {dups:5}  "
              f"{(no_kw/len(t)*100 if t else 0):6.0f}%     {len(errs)}")
        for e in errs[:5]: print("    ERR", e)
        total_dups += dups
    n = len(seen)
    print(f"\nunique total {n}, cross-file dups {total_dups}")
    shape_audit([r for f in files[1:] for r in load(f)[0]])


NAMES = re.compile(r"豆豆|咪咪|维尼|小维|团子|花花|球球|旺财|Max|Luna|Whiskers|Mochi|Weiwei|Doudou|Huahua", re.I)

def shape_audit(rows):
    """Label rate by SURFACE features of the training rows (gen/*.yaml only).

    The model will learn whatever shape separates true from false most cheaply.
    r1 learned "short = false" (0/303 short rows were true); r2 learned
    "short + pet name + 吐了/吃了 = true". Each bucket's true% should stay near
    the overall true%; a bucket far above or below it is a shortcut waiting to be learned.
    """
    def length(r):
        m = r["msg"]
        if "en" in (r.get("tags") or []):
            n = len(m.split()); return "en <=4 words" if n <= 4 else "en 5-8 words" if n <= 8 else "en >8 words"
        n = len(m); return "zh <=8" if n <= 8 else "zh 9-15" if n <= 15 else "zh 16-30" if n <= 30 else "zh >30"
    feats = {
        "length": length,
        "has pet name": lambda r: bool(NAMES.search(r["msg"])),
        "has 了": lambda r: "了" in r["msg"],
        "ends with ?/吗/怎么办": lambda r: bool(re.search(r"[吗呀啊办?？]$", r["msg"])),
        "panic word (救命/完了/help)": lambda r: bool(re.search(r"救命|完了|怎么办|help|omg", r["msg"], re.I)),
    }
    overall = sum(r["label"] for r in rows) / len(rows) * 100
    print(f"\n== shape audit (gen/ only, overall true {overall:.0f}%) — flag buckets far from overall ==")
    for name, f in feats.items():
        c = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            b = c[f(r)]; b[0] += 1; b[1] += r["label"]
        print(name)
        for v, (a, t) in sorted(c.items(), key=lambda x: str(x[0])):
            pct = t / a * 100
            flag = "  <-- skew" if abs(pct - overall) > 15 else ""
            print(f"   {v!s:14} n={a:5d}  true {pct:5.1f}%{flag}")

if __name__ == "__main__":
    main()
