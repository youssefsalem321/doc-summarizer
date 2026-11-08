"""استخدام من الـ terminal:
    python cli.py email path/to/email.txt
    python cli.py contract path/to/contract.pdf
"""
import argparse
import sys

from summarizer import load_text, summarize_contract, summarize_email


def main():
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=["email", "contract"])
    p.add_argument("path")
    args = p.parse_args()

    text = load_text(args.path)
    fn = summarize_email if args.kind == "email" else summarize_contract
    result = fn(text)
    sys.stdout.reconfigure(encoding="utf-8")
    print(result.model_dump_json(indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
