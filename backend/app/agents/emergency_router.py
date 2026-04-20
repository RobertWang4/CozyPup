"""Emergency short-circuit router.

Purpose: for HIGH-CONFIDENCE life-threatening pet emergencies, return a
structured response *before* the LLM runs. This bypasses both RAG and the
chat model, saving ~2-8 seconds of latency and removing the risk of the
model producing unsafe text on critical queries.

Scope vs. `emergency.py`:
- `emergency.py::detect_emergency` is a broad keyword net used to route
  ambiguous emergencies to the more accurate/expensive Kimi model and to
  nudge the LLM to invoke `trigger_emergency`.
- `emergency_router.py::classify_emergency` is a tighter classifier that
  ONLY fires on unambiguous emergencies and emits a ready-to-ship payload
  (hotline, category, short guidance, relevant article slug). The chat
  endpoint should call this first; if it returns a match, short-circuit.

Legal note: the payload here must NOT contain dosages or diagnoses. It
points the owner at a veterinarian and at an authoritative hotline. All
specific-article references are slugs in the knowledge base — the app
may surface them as links but never quote their dosage-adjacent passages.
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Public 24/7 North American hotlines; both charge a consult fee.
ASPCA_POISON_CONTROL = "(888) 426-4435"  # ASPCA Animal Poison Control Center
PET_POISON_HELPLINE = "(855) 764-7661"   # Pet Poison Helpline


@dataclass
class EmergencyMatch:
    """A high-confidence emergency classification.

    `category` is a stable key (use for analytics / A/B). `article_slug` is a
    matching knowledge-base article (the iOS app can deep-link to it).
    """
    category: str
    keywords: list[str]
    hotline: str  # preferred hotline for THIS category
    message_en: str
    message_zh: str
    article_slug: str | None = None
    metadata: dict = field(default_factory=dict)


# --- Category rules ------------------------------------------------------
#
# Each rule is a (category, compiled-regex, payload) triple. The first
# match wins. Keep the patterns tight — false positives waste user trust,
# but misses are worse, so we err toward firing.
#
# Pattern-design notes:
# - No word boundaries: Chinese has none and English keywords are distinctive.
# - Case-insensitive for English.
# - Multi-keyword patterns use `|` alternation to match any trigger phrase.


def _rx(*phrases: str) -> re.Pattern[str]:
    return re.compile("|".join(re.escape(p) for p in phrases), re.IGNORECASE)


_RULES: list[tuple[str, re.Pattern[str], dict]] = [
    # --- Poisoning / toxin ingestion ---------------------------------------
    (
        "toxin_ingestion",
        _rx(
            # English triggers: EITHER "ate/ingested/swallowed <toxic>" OR a specific toxin name.
            "ate chocolate", "ate a chocolate", "ate some chocolate",
            "ate grape", "ate a grape", "ate grapes", "ate raisin", "ate raisins",
            "ate onion", "ate garlic", "ate xylitol", "ate lily", "licked lily",
            "xylitol", "antifreeze",
            "ate rat poison", "rodenticide", "ate marijuana", "ate edible",
            "swallowed pill", "swallowed medication", "ate my medication",
            "swallowed ibuprofen", "swallowed tylenol", "swallowed acetaminophen",
            "swallowed advil", "swallowed aleve", "swallowed aspirin",
            "ate ibuprofen", "ate tylenol", "ate acetaminophen", "ate advil",
            "ate aleve", "ate aspirin", "poisoned", "poisoning",
            # Chinese — compound phrases
            "吃了巧克力", "吃了葡萄", "吃了提子", "吃了洋葱", "吃了大蒜",
            "吃了木糖醇", "吃了百合", "舔了百合", "百合花粉",
            "吃了老鼠药", "灭鼠药", "防冻液", "吃了大麻",
            "吃了药", "误食药", "误食布洛芬", "误食泰诺", "误服药",
            "吃了布洛芬", "吃了泰诺", "吃了阿司匹林", "吃了对乙酰氨基酚",
            "中毒",
            # Chinese — bare keywords when the word appears in a pet-chat query
            # it is almost always the user reporting ingestion. Accepting some
            # false positives on these is safer than missing the emergency.
            "巧克力", "木糖醇", "鼠药", "老鼠药", "大麻",
            "布洛芬", "泰诺", "对乙酰氨基酚",
        ),
        {
            "hotline": ASPCA_POISON_CONTROL,
            "message_en": (
                "This may be a poisoning. Call the ASPCA Animal Poison Control Center "
                f"at {ASPCA_POISON_CONTROL} right now — there is a consult fee but "
                "they will guide you. Do not induce vomiting unless they tell you to. "
                "Bring the product packaging to the vet."
            ),
            "message_zh": (
                "这可能是中毒。请立即拨打 ASPCA 动物中毒控制中心 "
                f"{ASPCA_POISON_CONTROL}（收取咨询费），他们会给出即时指导。"
                "未经专业人员指导不要自行催吐。把误食物品的包装带到医院。"
            ),
            "article_slug": "food_toxins",  # will also surface human_medications_toxic / toxic_plants
        },
    ),
    # --- Seizures / convulsions --------------------------------------------
    (
        "seizure",
        _rx(
            "seizure", "seizing", "convulsing", "convulsion",
            "having a fit", "tremoring uncontrollably",
            "抽搐", "抽风", "癫痫发作", "痉挛",
            "口吐白沫", "翻白眼倒地", "突然倒地抽动",
        ),
        {
            "hotline": PET_POISON_HELPLINE,
            "message_en": (
                "Seizures are an emergency — move furniture and sharp edges away, "
                "keep hands clear of the mouth, note the time. If the seizure "
                "lasts more than 3 minutes OR there are two in a row, go to "
                "an emergency vet now. Otherwise, call your vet immediately."
            ),
            "message_zh": (
                "抽搐是紧急情况。移开周围家具和尖锐物，不要把手放进嘴里，记录开始时间。"
                "如果单次抽搐超过 3 分钟或 24 小时内发生两次以上，立即去急诊兽医院。"
                "否则马上联系兽医。"
            ),
            "article_slug": "seizures",
        },
    ),
    # --- Urinary obstruction (especially male cat) -------------------------
    (
        "urinary_obstruction",
        _rx(
            "can't pee", "cant pee", "can't urinate", "cant urinate",
            "straining to pee", "straining to urinate", "no urine",
            "blocked cat", "blocked tomcat",
            "尿不出", "尿不出来", "拉不出尿", "不能尿尿", "一直蹲", "一直蹲厕所",
            "公猫尿不出", "尿道阻塞",
        ),
        {
            "hotline": PET_POISON_HELPLINE,  # default; for urinary, go straight to vet
            "message_en": (
                "A cat (especially male) that cannot pass urine is a life-threatening "
                "emergency — go to an emergency vet NOW. Do not wait. Without "
                "treatment, a urethral blockage can be fatal in 24-48 hours."
            ),
            "message_zh": (
                "猫（尤其公猫）尿不出来是致命急症，请立即去急诊兽医院，不要等待。"
                "尿道阻塞如不及时处理 24-48 小时内可能致命。"
            ),
            "article_slug": "cat_flutd",
        },
    ),
    # --- Respiratory distress ---------------------------------------------
    (
        "respiratory_distress",
        _rx(
            "can't breathe", "cant breathe", "not breathing",
            "open mouth breathing", "breathing with mouth open",
            "blue gums", "blue tongue", "purple gums", "gasping",
            "不能呼吸", "不呼吸", "呼吸困难", "张嘴呼吸",
            "牙龈发蓝", "牙龈发紫", "牙龈变紫", "牙龈变蓝",
            "舌头发紫", "舌头发蓝", "舌头变紫",
        ),
        {
            "hotline": PET_POISON_HELPLINE,
            "message_en": (
                "Breathing distress — open-mouth breathing in a cat, blue/purple "
                "gums, or gasping — is a true emergency. Keep the pet calm, "
                "minimize handling, and go to the nearest emergency vet now."
            ),
            "message_zh": (
                "呼吸困难（猫张嘴呼吸、牙龈/舌头发紫、喘息）是真正的紧急情况。"
                "保持安静、减少搬动，立刻去最近的急诊兽医院。"
            ),
            "article_slug": "respiratory_problems",
        },
    ),
    # --- GDV / bloat (large-breed dog) ------------------------------------
    (
        "gdv_bloat",
        _rx(
            "bloated belly", "distended abdomen", "swollen belly",
            "unproductive retching", "trying to vomit nothing comes up",
            "gdv", "gastric dilatation",
            "肚子鼓胀", "腹胀", "胃扭转", "干呕吐不出", "想吐吐不出",
        ),
        {
            "hotline": PET_POISON_HELPLINE,
            "message_en": (
                "A hard bloated belly with unproductive retching is a possible "
                "gastric dilatation-volvulus (GDV). This is a surgical emergency "
                "especially in large/deep-chested dogs — go to an emergency vet "
                "immediately, no time for a regular visit."
            ),
            "message_zh": (
                "腹部胀硬且反复干呕吐不出东西可能是胃扭转（GDV），尤其大型/深胸犬。"
                "这是外科急症，立刻去急诊兽医院，不要等常规门诊。"
            ),
            "article_slug": "bleeding_trauma",  # fallback until gdv.md is added
        },
    ),
    # --- Heatstroke --------------------------------------------------------
    (
        "heatstroke",
        _rx(
            "heat stroke", "heatstroke", "overheated", "left in hot car",
            "left in the car", "too hot panting",
            "中暑", "热射病", "热衰竭", "在车里", "车里太热",
        ),
        {
            "hotline": PET_POISON_HELPLINE,
            "message_en": (
                "Heatstroke is life-threatening. Move to shade, apply cool (not "
                "ice-cold) water to belly and paws, do NOT submerge in ice water, "
                "and go to an emergency vet now — even if the pet seems to be "
                "recovering, delayed organ injury can follow for 24-72 hours."
            ),
            "message_zh": (
                "中暑危及生命。移至阴凉处，用凉水（不要冰水）浇腹部和脚掌，"
                "绝对不要泡冰水。立即送急诊兽医院——即使看起来在恢复，"
                "24-72 小时内仍可能出现延迟性器官损伤。"
            ),
            "article_slug": "heatstroke",
        },
    ),
    # --- Severe trauma / bleeding -----------------------------------------
    (
        "severe_trauma",
        _rx(
            "hit by a car", "hit by car", "attacked by another dog",
            "mauled", "fell from", "bleeding a lot", "won't stop bleeding",
            "deep wound", "broken bone",
            "被车撞", "被撞", "被狗咬", "被咬伤", "大出血", "流血不止",
            "骨折", "摔下来",
        ),
        {
            "hotline": PET_POISON_HELPLINE,
            "message_en": (
                "Serious trauma — control bleeding with firm pressure on a clean "
                "cloth, don't remove impaled objects, keep the pet still, and go "
                "to an emergency vet now. Internal injuries can be hidden."
            ),
            "message_zh": (
                "严重外伤。用干净布料持续按压止血，不要拔出刺入物，保持静卧，"
                "立即前往急诊兽医院。内脏损伤可能看不出来。"
            ),
            "article_slug": "bleeding_trauma",
        },
    ),
    # --- Dystocia (difficult labor) ---------------------------------------
    (
        "dystocia",
        _rx(
            "labor more than", "straining no puppy", "straining no kitten",
            "green discharge no puppy", "green discharge no kitten",
            "dystocia", "stuck puppy", "stuck kitten",
            "难产", "生不出", "绿色分泌物", "小狗卡住", "小猫卡住",
            "宫缩", "强烈宫缩", "宫缩没生", "生不下来",
        ),
        {
            "hotline": PET_POISON_HELPLINE,
            "message_en": (
                "Difficult labor — more than 30 min of strong contractions with "
                "no birth, more than 2 hours of weak contractions, or green/black "
                "discharge without a baby — is an emergency. Go to the vet now."
            ),
            "message_zh": (
                "难产信号：强烈宫缩 30 分钟以上未生出、弱宫缩 2 小时以上未生出，"
                "或出现绿色/黑色分泌物且无胎儿产出。立即去急诊兽医院。"
            ),
            "article_slug": "dog_pregnancy",
        },
    ),
    # --- Collapse / unresponsive ------------------------------------------
    (
        "collapse",
        _rx(
            "collapsed", "unconscious", "unresponsive", "won't wake up",
            "cant wake", "not moving",
            "倒下了", "昏迷", "叫不醒", "没反应", "没有意识", "不动了",
        ),
        {
            "hotline": PET_POISON_HELPLINE,
            "message_en": (
                "A collapsed or unresponsive pet is a critical emergency. Check "
                "breathing and gum color, keep warm, and go to an emergency vet "
                "right now. Call ahead so they can prepare."
            ),
            "message_zh": (
                "宠物倒地或无反应是危重急症。观察呼吸和牙龈颜色，注意保暖，"
                "立刻送急诊兽医院。先打电话告知诊所做好准备。"
            ),
            "article_slug": "pet_emergency_basics",
        },
    ),
]


def classify_emergency(message: str) -> EmergencyMatch | None:
    """Return a structured EmergencyMatch for unambiguous emergencies, else None.

    The caller should short-circuit the chat pipeline when this returns
    non-None: skip RAG, skip the LLM, emit the EmergencyMatch as a direct
    structured response so the owner sees guidance immediately.
    """
    if not message or not message.strip():
        return None

    for category, pattern, payload in _RULES:
        matches = pattern.findall(message)
        if matches:
            keywords = list(dict.fromkeys(matches))
            logger.info(
                "emergency_router_match",
                extra={"category": category, "keywords": keywords},
            )
            return EmergencyMatch(
                category=category,
                keywords=keywords,
                hotline=payload["hotline"],
                message_en=payload["message_en"],
                message_zh=payload["message_zh"],
                article_slug=payload.get("article_slug"),
            )
    return None


def render_for_user(match: EmergencyMatch, lang: str = "zh") -> dict:
    """Shape an EmergencyMatch into the JSON payload the frontend expects.

    Keep the contract stable: the iOS client renders this as an emergency
    card with the message + a call-the-hotline button + a link to the
    related knowledge article.
    """
    msg = match.message_zh if lang == "zh" else match.message_en
    return {
        "type": "emergency",
        "category": match.category,
        "keywords": match.keywords,
        "hotline": match.hotline,
        "message": msg,
        "article_slug": match.article_slug,
    }
