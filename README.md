# Email & Contract Summarizer

An LLM-powered tool that turns an email or a contract (text, PDF, DOCX) into a **structured summary** with clause references, and an **automated evaluation suite** that catches the model's mistakes.

The interesting part of this project is not the summarizing. It is the guardrails: the model invents dates, overrates urgency, loses clauses in long documents, and misses ambiguous wording. Each failure was found through evaluation and fixed in code, not just in the prompt. See [What I learned](#what-i-learned-failures-found-and-fixed).

<!-- Add a screenshot of the app: save it as docs/screenshot.png, then uncomment the next line -->
<!-- ![App screenshot](docs/screenshot.png) -->

## What it does

**Emails** → summary, action items (with owner), deadlines, and a priority (`high` / `medium` / `low`) backed by a quote from the email.

**Contracts** → parties, term, payment, termination, obligations, risks, and **ambiguous wording**, each with a clause reference. Long contracts are split, analyzed per chunk, and merged in code.

Input: pasted text, `.txt`, `.pdf`, `.docx`. The output follows the language of the document (Arabic or English).

## Tech stack

Python · [Groq API](https://console.groq.com) (default model `openai/gpt-oss-120b`) · Pydantic · Streamlit · pypdf · python-docx

## Quick start

```bash
git clone https://github.com/youssefsalem321/doc-summarizer.git
cd doc-summarizer
pip install -r requirements.txt

cp .env.example .env        # Windows: copy .env.example .env
# edit .env and add your GROQ_API_KEY (free at console.groq.com/keys)

streamlit run app.py        # web UI
python cli.py email mail.txt
python cli.py contract contract.pdf
python -m eval.run_eval     # run the evaluation suite
```

Groq retires and renames models from time to time. If you get a `model_not_found` error, list the models available to your key and set `GROQ_MODEL` in `.env`:

```bash
python -c "from dotenv import load_dotenv; load_dotenv(); from groq import Groq; [print(m.id) for m in Groq().models.list().data]"
```

## How it works

```
file / text ──► loaders.py ──► core.py ──► structured JSON (Pydantic schema)
                                 │
                                 ├─ retry if the JSON is invalid or a guard fails
                                 ├─ long contract? split → extract per chunk → merge in code
                                 └─ guards: dates, urgency evidence, language, missing values
```

| File | Role |
|---|---|
| `summarizer/schemas.py` | Output shape (Pydantic models) |
| `summarizer/core.py` | LLM calls, retries, guards, chunking and merging |
| `summarizer/loaders.py` | Reads txt / pdf / docx |
| `app.py` | Streamlit UI |
| `cli.py` | Command line interface |
| `eval/` | Test samples and the evaluation runner |

## Evaluation

`python -m eval.run_eval` runs every sample in `eval/samples.json` and checks:

- the expected priority,
- required facts (alternative phrasings allowed, e.g. `March 10` / `10 March`),
- forbidden content (for example an invented end date),
- that ambiguous wording was flagged,
- specific output fields (for example, the `termination` field must contain `90`).

The suite is small (5 samples, including a 3-page PDF contract with planted traps). It is meant to catch regressions after every prompt or code change, not to be a benchmark.

## What I learned: failures found and fixed

| Failure | Fix |
|---|---|
| The model **invented an end date** that was not in the contract, even at `temperature=0` and with explicit instructions | Code compares every date in the output to the source text; an unseen date triggers a retry |
| The model rated emails **`high` priority by imagining consequences** the email never stated | The model must first quote evidence from the email; code verifies the quote exists in the source |
| In long contracts the **late fee and auto-renewal clauses silently disappeared** (summary-of-summaries lost them) | Each chunk is extracted into structured data and merged **in code**, so clauses can't be dropped by a second LLM pass |
| Output **mixed Arabic and English** across chunks | The document language is detected in code and requested explicitly |
| The model **missed ambiguous wording** (`2% per week`, but 2% of what?) on some runs | A dedicated `ambiguities` field the model must fill before the risks |
| `termination` showed `non mentioned` although the contract had a termination clause | Missing values are detected with a flexible pattern instead of a fixed list; the eval now checks individual fields |
| A reasoning model **ran out of tokens** before finishing the JSON | Higher token budget, lower reasoning effort, and an automatic retry on that error |

The main lesson: a prompt steers the model, but only code and evaluation can guarantee behavior. Results also vary between runs, so one passing run proves little.

## Limitations

- **Not legal advice.** Summaries help you read faster. They do not replace reading the contract or consulting a lawyer.
- Scanned PDFs (images) are not supported yet; they need OCR.
- Arabic text extracted from some PDFs can come out reversed or garbled, which hurts the summary.
- Output varies between runs, even with the guards.
- Tested on a handful of samples only. Do not rely on it for real decisions without checking the source.
- Groq's free tier has rate limits. Long contracts make several calls and may need a short wait.

## Roadmap

- OCR for scanned PDFs
- Automatic detection of document type (email vs contract)
- The same grounding guard for amounts and percentages
- Larger evaluation set
- Dockerfile and hosted demo

## Privacy

Documents you submit are sent to the Groq API. Do not use confidential documents unless that is acceptable to you. The repo ships only synthetic samples.
