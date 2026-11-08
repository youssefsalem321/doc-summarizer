"""تقييم بسيط:  python -m eval.run_eval"""
import json
from pathlib import Path

from summarizer import load_text, summarize_contract, summarize_email

HERE = Path(__file__).parent
samples = json.loads((HERE / "samples.json").read_text(encoding="utf-8"))
passed = 0


def mentions(blob: str, item) -> bool:
    """item ممكن يكون كلمة، أو قائمة صيغ بديلة (أي واحدة منها تكفي)."""
    options = item if isinstance(item, list) else [item]
    return any(o.lower() in blob.lower() for o in options)


for s in samples:
    fn = summarize_email if s["kind"] == "email" else summarize_contract
    text = load_text(HERE / s["file"]) if "file" in s else s["text"]
    try:
        out = fn(text)
    except Exception as e:  # noqa: BLE001
        print(f"❌ {s['id']}: ERROR {e}")
        continue
    blob = out.model_dump_json(ensure_ascii=False)

    checks = {}
    if "expected_priority" in s:
        checks["priority"] = out.priority == s["expected_priority"]
    if s.get("expect_ambiguity"):
        checks["ambiguity found"] = bool(getattr(out, "ambiguities", []))
    for item in s.get("must_mention", []):
        checks[f"mentions {item}"] = mentions(blob, item)
    for field, items in s.get("field_must_mention", {}).items():
        for item in items:
            checks[f"{field} mentions {item}"] = mentions(str(getattr(out, field)), item)
    for word in s.get("must_not_mention", []):
        checks[f"avoids '{word}'"] = word.lower() not in blob.lower()

    ok = all(checks.values())
    passed += ok
    print(f"{'✅' if ok else '❌'} {s['id']}: {checks}")
    if not ok:
        print("   OUTPUT:", blob)

print(f"\nPassed {passed}/{len(samples)}")
