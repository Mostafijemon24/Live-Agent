import sys

from app.workers.runtime import main

if __name__ == "__main__":
    kinds = ("orchestrator", "tools", "deletion", "scheduler")
    if len(sys.argv) != 2 or sys.argv[1] not in kinds:
        raise SystemExit(f"usage: python -m app.workers {{{'|'.join(kinds)}}}")
    main(sys.argv[1])
