"""Patch aliases: list into the frontmatter of existing articles.

Inserts immediately above `disclaimer: true`. Idempotent: skips files that
already contain an `aliases:` key.

Run:
    python knowledge/scripts/add_aliases.py
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "articles"

ALIASES: dict[str, list[str]] = {
    "dog_vomiting.md": ["呕吐","吐","干呕","吐黄水","狗呕吐","吐白沫","胃反流"],
    "diarrhea_in_dogs.md": ["拉肚子","软便","稀便","腹泻","狗拉稀","狗拉肚子","血便","水便"],
    "dog_vaccinations.md": ["疫苗","打针","免疫","加强针","狗狗疫苗","狂犬疫苗","小狗疫苗","疫苗时间表"],
    "giving_medications.md": ["喂药","吃药","给药","喂药方法","药怎么喂"],
    "foreign_body_in_dogs.md": ["异食","误食","吞了","吃到","卡住","肠梗阻","吞异物","狗吞东西","线状异物"],
    "deworming_dogs.md": ["驱虫","打虫","体内驱虫","体外驱虫","跳蚤","蜱虫","心丝虫","蛔虫","绦虫"],
    "spay_neuter_dogs.md": ["绝育","结扎","去势","公狗绝育","母狗绝育"],
    "skin_disorders_dogs.md": ["皮肤病","皮肤","过敏","瘙痒","掉毛","红疹","脱毛","脓疱","狗过敏"],
    "ear_mites_dogs.md": ["耳螨","耳朵黑","耳朵痒","抓耳朵","摇头","耳道发炎","耳屎多"],
    "dental_care_dogs.md": ["牙结石","口臭","牙龈炎","牙周病","洗牙","刷牙","烂牙","牙齿"],

    "cat_vomiting.md": ["猫呕吐","吐","干呕","毛球","吐毛球","猫吐","猫吐白沫"],
    "cat_diarrhea.md": ["猫拉肚子","猫拉稀","软便","稀便","腹泻","血便"],
    "cat_vaccinations.md": ["猫疫苗","免疫","三联","五联","猫三联","狂犬疫苗","小猫疫苗"],
    "cat_foreign_body.md": ["猫吞","误食","线","绳子","毛线","缝衣线","卡住","异物"],
    "cat_deworming.md": ["猫驱虫","打虫","体内驱虫","体外驱虫","跳蚤","猫蛔虫","绦虫"],
    "cat_skin_disorders.md": ["猫皮肤病","皮肤","过敏","瘙痒","掉毛","舔毛","脱毛","猫过敏","过度舔毛"],
    "cat_ear_mites.md": ["猫耳螨","耳朵黑","耳朵痒","抓耳朵","摇头","耳屎多"],
    "cat_dental_care.md": ["猫牙结石","口臭","猫牙","牙龈炎","吃饭掉东西","牙齿"],
    "cat_flutd.md": ["尿路感染","尿闭","公猫尿不出","猫拉尿","尿血","尿频","膀胱炎","特发性膀胱炎","猫尿不出来"],
    "cat_hyperthyroidism.md": ["甲亢","甲状腺","变瘦","爱吃","老猫瘦","叫得多","喝水多","尿多"],

    "toxic_plants.md": ["有毒植物","百合","百合花","花粉","有毒花","吃了植物","吃了花","沙漠玫瑰","杜鹃"],
    "food_toxins.md": ["巧克力","葡萄","洋葱","大蒜","木糖醇","夏威夷果","提子","狗吃了","猫吃了","中毒","误食食物","吃了人的食物"],
    "human_medications_toxic.md": ["布洛芬","对乙酰氨基酚","泰诺","阿司匹林","人药","感冒药","止痛药","安眠药","抗抑郁药","误服","药物中毒","芬必得","氨酚待因"],

    "dog_eye_problems.md": ["狗眼睛","眼睛红","眼屎","结膜炎","红眼","眼睛闭着","眼睛睁不开","眼睛分泌物"],
    "cat_eye_problems.md": ["猫眼睛","眼睛红","眼屎","结膜炎","眼睛闭着","猫眼屎","睁不开"],
    "dog_behavior_problems.md": ["吠叫","乱叫","咬人","攻击","焦虑","分离焦虑","怕打雷","怕烟花","强迫行为","随地大小便","行为问题","狗乱叫"],
    "cat_behavior_problems.md": ["乱尿","乱拉","抓沙发","打架","猫攻击","焦虑","叫","乱喷尿","行为问题","过度舔毛","猫乱尿"],
    "puppy_first_weeks.md": ["幼犬","小狗","新狗","刚到家","一周","小狗疫苗","社会化","小狗照顾"],
    "kitten_first_weeks.md": ["幼猫","小猫","新猫","刚接回家","一周","小猫疫苗","社会化","小猫照顾"],
}


def patch(filepath: Path, aliases: list[str]) -> str:
    text = filepath.read_text(encoding="utf-8")

    if "\naliases:" in text or text.startswith("aliases:"):
        return "skip (already has aliases)"

    # Locate frontmatter end
    if not text.startswith("---\n"):
        return "skip (no frontmatter)"
    fm_end = text.find("\n---\n", 4)
    if fm_end == -1:
        return "skip (unclosed frontmatter)"

    # Insert before `disclaimer:` if present, else append at end of frontmatter
    alias_block = "aliases:\n" + "\n".join(f"  - {a}" for a in aliases) + "\n"

    fm = text[4:fm_end + 1]  # trailing newline included
    rest = text[fm_end + 1:]  # starts with "---\n..."

    disc_idx = fm.rfind("disclaimer:")
    if disc_idx != -1:
        # Insert before disclaimer line
        new_fm = fm[:disc_idx] + alias_block + fm[disc_idx:]
    else:
        # Append at end
        new_fm = fm + alias_block

    filepath.write_text("---\n" + new_fm + rest, encoding="utf-8")
    return f"added {len(aliases)} aliases"


def main():
    for name, aliases in ALIASES.items():
        fp = ROOT / name
        if not fp.exists():
            print(f"  ✗ {name}  MISSING")
            continue
        status = patch(fp, aliases)
        print(f"  ✓ {name}  {status}")


if __name__ == "__main__":
    main()
