"""Run arms A and B of the filter-coverage scenario sequentially and print reports.

  set -a; . evals/nxd_eval/.env; set +a            # OPENAI_API_KEY
  export NXD_PAT=...                               # 1-day personal access token
  export SSL_CERT_FILE=<bundle-with-nxdCA.crt-and-certifi>
  cd evals/nxd_eval && uv run --extra openai python scenarios/run_filter_coverage.py \
      openai/gpt-6-luna [--epochs 5] [--isolate] [--arms A,B] [--chat-completions]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scenarios.filter_coverage import run_arm  # noqa: E402

from nxd_eval import Report  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--arms", default="A,B")
    ap.add_argument("--isolate", action="store_true")
    ap.add_argument("--log-dir", default="logs/filter_coverage")
    ap.add_argument(
        "--chat-completions",
        action="store_true",
        help="use OpenAI Chat Completions instead of the Responses API",
    )
    a = ap.parse_args()
    model_args = (
        {"responses_api": True}
        if a.model.startswith("openai/") and not a.chat_completions
        else None
    )
    for arm in a.arms.split(","):
        log = run_arm(
            arm, agent_model=a.model, epochs=a.epochs,
            agent_model_args=model_args,
            log_dir=a.log_dir, isolate_sessions=a.isolate,
        )
        print(f"\n=== arm {arm} · {a.model} · {log}\n")
        print(Report.from_path(log).to_markdown())


if __name__ == "__main__":
    main()
