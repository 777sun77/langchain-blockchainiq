"""One brief call. Use --dry-run for free requirements and sample only."""
import argparse
import json
import sys
from langchain_blockchainiq import BlockchainIQBriefTool, BlockchainIQError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    tool = BlockchainIQBriefTool(dry_run=args.dry_run)
    try:
        result = tool.invoke({})
    except BlockchainIQError as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps(result, indent=2))
    else:
        print("Settlement transaction hash:", result["transaction_hash"])
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
