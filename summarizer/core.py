"""المنطق الأساسي: استدعاء Groq + structured output + معالجة النصوص الطويلة."""
import json
import os
import re
import time
from functools import lru_cache

from dotenv import load_dotenv
from groq import BadRequestError, Groq, RateLimitError
from pydantic import BaseModel, ValidationError

from .schemas import ContractSummary, EmailSummary

load_dotenv()

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
CHUNK_CHARS = 6_000  # أصغر شوية عشان حدود الطبقة المجانية في Groq

LANG_RULE = "اكتب كل القيم النصية بنفس لغة المستند الأصلي، إلا لو طُلب غير كده."
GROUNDING_RULE = (
    "استخدم المعلومات الموجودة في النص فقط. لو معلومة مش مذكورة اكتب 'غير مذكور'. "
    "ممنوع التخمين."
)


@lru_cache(maxsize=1)
def _client() -> Groq:
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY مش موجود. حطه في ملف .env")
    return Groq()


def _call(system: str, user: str, max_tokens: int = 2000, json_mode: bool = False) -> str:
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if "gpt-oss" in MODEL:
        # موديلات gpt-oss بتفكّر قبل ما ترد، والتفكير بيتحسب من max_tokens
        kwargs["extra_body"] = {"reasoning_effort": "low"}
    for attempt in range(3):
        try:
            resp = _client().chat.completions.create(
                model=MODEL,
                max_tokens=max_tokens,
                temperature=0,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **kwargs,
            )
            return resp.choices[0].message.content or ""
        except RateLimitError:
            # الطبقة المجانية ليها حد للطلبات في الدقيقة: استنى وحاول تاني
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))
    return ""


def _extract_json(text: str) -> str:
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return text[start : end + 1]


# ---------- حماية: ممنوع تواريخ مش موجودة في النص الأصلي ----------
def _dates(text: str) -> set:
    """بيطلّع كل التواريخ بصيغة (يوم, شهر, سنة) عشان 1/1/2026 = 01/01/2026."""
    found = set()
    for d, m, y in re.findall(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", text):
        found.add((int(d), int(m), int(y)))
    for y, m, d in re.findall(r"(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})", text):
        found.add((int(d), int(m), int(y)))
    return found


def _ungrounded_dates(source: str, output: str) -> list[str]:
    bad = _dates(output) - _dates(source)
    return [f"{d}/{m}/{y}" for d, m, y in sorted(bad)]


def _structured(
    system: str,
    user: str,
    schema: type[BaseModel],
    retries: int = 2,
    source: str | None = None,
    check=None,
):
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    full_system = (
        f"{system}\n\n{LANG_RULE}\n{GROUNDING_RULE}\n\n"
        f"رجّع JSON فقط (بدون markdown أو شرح) مطابق للـ schema:\n{schema_json}"
    )
    prompt = user
    raw = ""
    for attempt in range(retries + 1):
        try:
            raw = _call(full_system, prompt, max_tokens=4096, json_mode=True)
            result = schema.model_validate_json(_extract_json(raw))
            if source is not None:
                bad = _ungrounded_dates(source, result.model_dump_json())
                if bad:
                    raise ValueError(
                        f"التواريخ دي مش مكتوبة في النص الأصلي: {', '.join(bad)}. "
                        "امسحها ولا تحسب أي تاريخ"
                    )
            if check:
                check(result)
            return result
        except (ValidationError, ValueError, BadRequestError) as e:
            if attempt == retries:
                raise RuntimeError(f"فشل الحصول على رد سليم: {e}\n\n{raw}") from e
            prompt = (
                f"{user}\n\n(المحاولة السابقة طلعت غلط: {e}. "
                "صحّحها ورجّع JSON صالح فقط، واختصر: جمل قصيرة وبدون تكرار.)"
            )


def _split(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """قسّم على حدود الفقرات عشان ما نقطعش بند في النص."""
    chunks, current = [], ""
    for para in text.split("\n\n"):
        if current and len(current) + len(para) > size:
            chunks.append(current)
            current = ""
        current += para + "\n\n"
    if current.strip():
        chunks.append(current)
    return chunks


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _urgency_check(source: str):
    """high لازم يكون وراه اقتباس حرفي موجود فعلًا في الإيميل."""

    def check(result: EmailSummary) -> None:
        if result.priority != "high":
            return
        quote = _norm(result.urgency_evidence)
        if not quote or quote == "none" or quote not in _norm(source):
            raise ValueError(
                "priority=high لازم يكون وراه اقتباس حرفي من الإيميل بيثبت استعجال أو عاقبة "
                "مكتوبة. لو مفيش اقتباس زي كده خلّيها medium أو low"
            )

    return check


def summarize_email(text: str) -> EmailSummary:
    system = (
        "انت مساعد بيحلل الإيميلات. لخّص الإيميل بدقة: مين طلب إيه وإيه الحدث الأساسي، "
        "واذكر في الملخص أهم تاريخ أو هدف نهائي. "
        "action_items: اكتب كل مهمة مع اسم المسؤول عنها بين قوسين لو مذكور. "
        "لو الإيميل بيقول عن المهمة إنها مش مستعجلة اكتب جنبها بين قوسين: "
        "(غير مستعجل) لو الإيميل بالعربي، أو (not urgent) لو الإيميل بالإنجليزي. "
        "ما تحطش في action_items حاجة اتأجلت أو مش مطلوب شغل عليها. "
        "deadlines: أي اجتماع أو تسليم له تاريخ ووقت محدد، ولا تذكر كلمات عامة زي 'اليوم'. "
        "الأولوية: الأول املأ urgency_evidence باقتباس حرفي من الإيميل بيثبت استعجال صريح "
        "(زي urgent أو ASAP أو النهاردة) أو عاقبة مكتوبة لو حصل تأخير، ولو مفيش اكتب none. "
        "ممنوع تتوقع أو تفترض عواقب مش مكتوبة، ووجود مواعيد قادمة لوحده مش استعجال. "
        "بعد كده حدد priority: high فقط لو في اقتباس حقيقي، "
        "medium لو في مهام ومواعيد محددة من غير استعجال أو عاقبة مكتوبة، "
        "low لو معلومات فقط أو مفيش مطلوب من حد. "
        "priority_reason لازم يعتمد على اللي مكتوب في الإيميل فقط. "
        "اكتب الرد بنفس لغة الإيميل الأصلي بالظبط (إيميل إنجليزي = رد إنجليزي). "
        "قيمة priority لازم تكون واحدة من: high, medium, low بالإنجليزي."
    )
    return _structured(system, text, EmailSummary, source=text, check=_urgency_check(text))


def _lang_instruction(text: str) -> str:
    """بيحدد لغة المستند من نسبة الحروف ويطلب اللغة صراحة (أضمن من 'بنفس اللغة')."""
    arabic = len(re.findall(r"[\u0600-\u06FF]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if arabic / (arabic + latin + 1) > 0.4:
        return "اكتب كل القيم النصية بالعربي (أسماء الأطراف والمصطلحات الأصلية تفضل زي ما هي). "
    return (
        "Write ALL text values in English only (summary, topics, details, terms), "
        "even though these instructions are written in Arabic. "
    )


CONTRACT_SYSTEM = (
    "انت مساعد بيحلل العقود. اعمل ملخص منظم، واذكر رقم البند/الفقرة "
    "اللي أخدت منها كل التزام أو خطر. "
    "راجع البنود دي واحد واحد وحطها في risks لو موجودة: غرامة تأخير، تجديد تلقائي، "
    "حدود المسؤولية، عدم توازن في الإنهاء أو الإشعار، عدم منافسة أو حصرية، وأي بند غير متوازن. "
    "obligations: التزامات جوهرية فقط (دفع، تسليم، سرية، ملكية فكرية...) "
    "ومن غير بنود شكلية زي الإشعارات والقانون الحاكم وتعديل العقد. "
    "في خانات term وpayment وtermination اكتب المعلومة فقط من غير رقم بند. "
    "risks: بنود فيها ضرر حقيقي أو عدم توازن أو غموض فقط. البنود الروتينية "
    "(سرية، ضمانات عادية، قوة قاهرة، موافقة على التعاقد من الباطن، طلبات تغيير) "
    "مش مخاطر إلا لو فيها شرط غريب. ولا تكرر نفس البند في obligations و risks. "
    "اختصر: كل detail جملة واحدة قصيرة، وأقصى 10 عناصر في obligations و8 في risks. "
    "ممنوع تحسب أو تستنتج تواريخ أو مبالغ أو نسب مش مكتوبة صراحة في النص. "
    "مثال: لو العقد بيقول 'سنة تبدأ 1/1/2026' اكتب المدة 'سنة تبدأ 1/1/2026' "
    "ولا تكتب تاريخ انتهاء. "
    "ambiguities: راجع كل نسبة وغرامة ومبلغ ومدة في النص واحدة واحدة، وسجّل أي صياغة غامضة "
    "بدل ما تفترض معنى. مثال: 'غرامة 2% عن كل أسبوع' من غير تحديد 2% من إيه "
    "(الإيجار الشهري؟ المبلغ المتأخر؟). اكتب [] بس لو مفيش أي غموض. "
    "خانة termination معناها حق إنهاء العقد أثناء مدته فقط. "
    "إشعار عدم التجديد بعد انتهاء المدة مش إنهاء، فلو العقد مفيهوش بند إنهاء اكتب 'غير مذكور'. "
)

CHUNK_NOTE = (
    "ملحوظة: ده جزء واحد بس من عقد أطول. استخرج اللي مكتوب في الجزء ده فقط، "
    "ولو خانة معلوماتها مش في الجزء ده اكتب فيها 'غير مذكور'. "
    "ممنوع تذكر في risks غياب بنود (زي 'مفيش بند إنهاء') لأن البند ممكن يكون في جزء تاني. "
)

_MISSING_RE = re.compile(
    r"غير\s*(?:مذكور|محدد|موجود)"
    r"|\b(?:not|non|no)\b[\s\-]*(?:mentioned|specified|stated|provided|applicable|found|available)"
    r"|\bn/?a\b|\bnone\b|\bunspecified\b",
    re.IGNORECASE,
)


def _is_missing(value: str) -> bool:
    """قيمة قصيرة معناها 'مش موجود'. القيم الطويلة بتتعامل كمعلومة حقيقية."""
    v = value.strip()
    return not v or (len(v) < 40 and bool(_MISSING_RE.search(v)))


def _first_real(values: list[str]) -> str:
    for v in values:
        if not _is_missing(v):
            return v
    return values[0]


def _dedupe(items: list, key) -> list:
    seen, out = set(), []
    for it in items:
        k = key(it)
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


ROLE_WORDS = {
    "client", "the client", "contractor", "the contractor", "party", "parties",
    "العميل", "المستقل", "المتعهد", "المقاول", "الطرف الأول", "الطرف الثاني",
    "المؤجر", "المستأجر",
}


def _clean_parties(parties: list[str]) -> list[str]:
    """شيل التكرار، وكلمات الأدوار لوحدها، وأي اسم موجود جوه اسم تاني."""
    unique = _dedupe(parties, key=lambda x: x.lower().strip())
    cleaned = [
        p for p in unique
        if p.lower().strip(" ()") not in ROLE_WORDS
        and not any(q != p and p.lower().strip() in q.lower() for q in unique)
    ]
    return cleaned or unique  # لو الفلتر هيشيل كل الأسماء نسيب القايمة زي ما هي


def _merge(parts: list[ContractSummary], original: str) -> ContractSummary:
    """دمج نتايج الأجزاء بالكود: المخاطر والالتزامات بتتجمع كلها ومفيش حاجة بتضيع."""
    clause_key = lambda c: (c.reference.lower().strip(), c.topic.lower().strip())  # noqa: E731
    parties = _clean_parties([x for p in parts for x in p.parties])
    term = _first_real([p.term for p in parts])
    payment = _first_real([p.payment for p in parts])
    termination = _first_real([p.termination for p in parts])
    obligations = _dedupe([c for p in parts for c in p.obligations], key=clause_key)
    ambiguities = _dedupe([c for p in parts for c in p.ambiguities], key=clause_key)
    risks = _dedupe([c for p in parts for c in p.risks], key=clause_key)

    # الملخص النهائي بيتكتب من الحقائق المدمجة عشان الأرقام ما تضيعش
    facts = "\n".join(
        [f"Term: {term}", f"Payment: {payment}", f"Termination: {termination}"]
        + [f"Risk ({c.reference}) {c.topic}: {c.detail}" for c in risks]
        + [f"Ambiguity ({c.reference}) {c.topic}: {c.detail}" for c in ambiguities]
    )
    joined = "\n".join(p.summary for p in parts)
    summary = _call(
        "اكتب ملخص من 3 إلى 4 جمل لعقد واحد بناءً على المعلومات دي. "
        "احتفظ بالأرقام والمدد والنسب المحددة زي ما هي (أيام، مبالغ، نسب). "
        "استخدم اللي مكتوب فيها فقط ولا تحسب أي تواريخ. " + _lang_instruction(original),
        facts + "\n\n" + joined,
    ).strip()
    if not summary or _ungrounded_dates(original, summary):
        summary = joined  # لو الملخص الموحّد فيه تاريخ مخترع نرجع للملخصات الأصلية

    return ContractSummary(
        summary=summary,
        parties=parties,
        term=term,
        payment=payment,
        termination=termination,
        obligations=obligations,
        ambiguities=ambiguities,
        risks=risks,
    )


def _prettify(topic: str) -> str:
    """DisputeResolution -> Dispute Resolution"""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", topic).strip()


def _tidy(result: ContractSummary) -> ContractSummary:
    """تنضيف شكلي: أسماء مقروءة، ودمج بنود المخاطر اللي من نفس المادة."""
    for c in result.obligations + result.risks + result.ambiguities:
        c.topic = _prettify(c.topic)

    merged, index = [], {}
    for c in result.risks:
        key = c.reference.strip().lower()
        if re.search(r"\d", key) and key in index:  # ندمج بس لو رقم المادة معروف
            base = merged[index[key]]
            base.topic = f"{base.topic} / {c.topic}"
            if c.detail.strip().lower() not in base.detail.lower():
                base.detail = f"{base.detail}; {c.detail}"
        else:
            index[key] = len(merged)
            merged.append(c)
    result.risks = merged
    return result


def summarize_contract(text: str) -> ContractSummary:
    system = CONTRACT_SYSTEM + _lang_instruction(text)
    if len(text) <= CHUNK_CHARS:
        return _tidy(_structured(system, text, ContractSummary, retries=3, source=text))

    # عقد طويل: استخرج منظم من كل جزء على النص الأصلي، وبعدين ادمج بالكود
    parts = [
        _structured(system + CHUNK_NOTE, chunk, ContractSummary, retries=3, source=chunk)
        for chunk in _split(text)
    ]
    return _tidy(_merge(parts, text))
