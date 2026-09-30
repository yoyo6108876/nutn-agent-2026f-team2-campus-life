"""Lecture-compatible entry point. auto and fixture never use a network/API key."""

import argparse
from pathlib import Path
import sys

from .run_week3_evidence import run_lab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', choices=['auto', 'fixture', 'openai-live'], default='auto',
                        help='auto/fixture: authored gemini_fixture; openai-live: three paid calls on synthetic Q1/QP/B1')
    parser.add_argument('--output', type=Path, default=Path('artifacts/week03-generator-comparison.json'))
    args = parser.parse_args()
    live_queries = ['Q1', 'QP', 'B1'] if args.path == 'openai-live' else []
    return run_lab(args.output.parent, live_queries, comparison_name=args.output.name,
                   command='python -m scripts.run_studio_generator_lab ' + ' '.join(sys.argv[1:]))


if __name__ == '__main__':
    raise SystemExit(main())
