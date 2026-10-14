# app/cli.py
# Ask questions from the terminal, without starting the web server.
#   python -m app.cli "how do I get to Teide?"            -> full answer
#   python -m app.cli --search "kids beach Los Cristianos" -> only show what retrieval finds

import sys

from app import rag


def main():
    args = sys.argv[1:]
    if not args:
        print('Usage: python -m app.cli [--search] "your question"')
        return

    if args[0] == "--search":
        for s in rag.retrieve(" ".join(args[1:])):
            print(f"\n[{s['score']:.2f}] {s['type']} – {s['title']}")
            print(s["content"][:300], "...")
        return

    result = rag.ask(" ".join(args))
    print("\nANSWER:\n" + result["answer"])
    print("\nSOURCES:")
    for i, s in enumerate(result["sources"], start=1):
        print(f"  {i}. [{s['score']}] {s['type']} – {s['title']}")


if __name__ == "__main__":
    main()
