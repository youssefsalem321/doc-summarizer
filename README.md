# ملخّص الإيميلات والعقود 📄

مشروع AI Engineering: بياخد إيميل أو عقد (نص / PDF / DOCX) ويرجّع ملخص **منظم** (JSON)
مع المطلوب عمله والمواعيد والبنود الخطرة وأرقام البنود.

## التشغيل
```bash
pip install -r requirements.txt
cp .env.example .env        # حط GROQ_API_KEY (من console.groq.com/keys)
streamlit run app.py        # الواجهة
python cli.py email sample.txt
python -m eval.run_eval     # التقييم
```

## الهيكل
| ملف | وظيفته |
|---|---|
| `summarizer/schemas.py` | شكل المخرجات (Pydantic) |
| `summarizer/core.py` | استدعاء Groq + إعادة المحاولة لو JSON باظ + map-reduce للعقود الطويلة |
| `summarizer/loaders.py` | قراءة txt/pdf/docx |
| `app.py` | واجهة Streamlit |
| `cli.py` | استخدام من الـ terminal |
| `eval/` | عينات + سكريبت تقييم |

## أفكار للتطوير
- OCR للـ PDF الممسوح (pytesseract).
- قراءة الإيميلات مباشرة من Gmail API.
- مقارنة نسختين من عقد.
- Dockerfile + نشر على سيرفر.
- زوّد عينات التقييم لـ 20+ وقيس الدقة مع كل تعديل في الـ prompt.

> ⚠️ الملخص للفهم السريع وليس استشارة قانونية.
