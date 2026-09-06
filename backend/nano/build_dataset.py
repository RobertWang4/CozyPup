"""Merge gen/*.yaml into train/val JSONL, deduped against each other and against
the held-out test file. Usage: python -m nano.build_dataset [--test nano/data/seeds.yaml]"""
import glob, json, random, re
import click, yaml

norm = lambda s: re.sub(r"[\s，。！？,.!?~～]+", "", str(s).strip().lower())


@click.command()
@click.option("--gen-dir", default="nano/data/gen")
@click.option("--test", default="nano/data/seeds.yaml", help="held-out file; anything matching it is dropped from train")
@click.option("--val-frac", default=0.1, type=float)
@click.option("--seed", default=42, type=int)
@click.option("--out-dir", default="nano/data")
def main(gen_dir, test, val_frac, seed, out_dir):
    test_keys = {norm(r["msg"]) for r in (yaml.safe_load(open(test)) or [])}
    rows, seen, dropped_test, dropped_dup = [], set(), 0, 0
    for f in sorted(glob.glob(f"{gen_dir}/*.yaml")):
        for r in yaml.safe_load(open(f)) or []:
            k = norm(r["msg"])
            if not k: continue
            if k in test_keys: dropped_test += 1; continue
            if k in seen: dropped_dup += 1; continue
            seen.add(k)
            rows.append({"msg": str(r["msg"]).strip(), "label": bool(r["label"]),
                         "tags": [str(t) for t in r.get("tags", [])], "source": f.split("/")[-1]})
    random.Random(seed).shuffle(rows)
    # stratified split so val has the same true ratio
    pos = [r for r in rows if r["label"]]; neg = [r for r in rows if not r["label"]]
    nvp, nvn = int(len(pos) * val_frac), int(len(neg) * val_frac)
    val = pos[:nvp] + neg[:nvn]; train = pos[nvp:] + neg[nvn:]
    random.Random(seed).shuffle(train); random.Random(seed).shuffle(val)
    for name, data in (("train", train), ("val", val)):
        with open(f"{out_dir}/{name}.jsonl", "w") as fh:
            for r in data: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"train {len(train)} (true {sum(r['label'] for r in train)})  val {len(val)} (true {sum(r['label'] for r in val)})")
    print(f"dropped: {dropped_test} overlap with test, {dropped_dup} duplicates")


if __name__ == "__main__":
    main()
