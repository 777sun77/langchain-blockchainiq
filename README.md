# Langchain Blockchain IQ

Framework-native `BlockchainIQBriefTool` and `BlockchainIQEventRiskTool` by Sihu Park.
Each invocation purchases JSON from the [Blockchain IQ API](https://www.blockchainiq.co/agents)
using the official [x402 Python SDK](https://pypi.org/project/x402/2.25.0/):
x402 v2, scheme `exact`, EIP-3009, USDC on Base (`eip155:8453`).

## Install

Python 3.11–3.13. From this directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
```

This repository is a standalone package. No sibling
package, API key, RPC URL, or LLM credentials are required for the example.

## Verify for free

```sh
python examples/paid_call.py --dry-run
pytest -q
```

Dry-run requests only `/brief` (expecting HTTP 402) and the free `/sample`. It prints
the decoded payment requirements and sample JSON. It does not read a private key,
sign an authorization, send a payment header, or retry the paid resource.
The tests use mock HTTP transports exclusively and do not spend funds.

## One paid brief call

Fund a wallet with at least $0.01 USDC on **Base mainnet**, then set
`BIQ_X402_PRIVATE_KEY` in your environment using your shell's secret input or secret
manager. This is the only supported secret; never commit it to a file or pass it as
an agent/tool argument. The integration never prints it.

```sh
python examples/paid_call.py
```

This makes one unpaid GET, signs the returned requirements with the official SDK,
and retries once with `PAYMENT-SIGNATURE`. It decodes `PAYMENT-RESPONSE`, requires
successful Base settlement, and prints `Settlement transaction hash: 0x...` along
with data and the decoded proof. A missing or failed proof raises an error rather
than claiming a successful purchase. Keep the actual hash for a bounty claim.

## Framework usage

```python
from langchain_blockchainiq import BlockchainIQBriefTool, BlockchainIQEventRiskTool

tool = BlockchainIQBriefTool(dry_run=True)
result = tool.invoke({})
print(result)

# Set dry_run=False to authorize a purchase on every invocation.
# risk = BlockchainIQEventRiskTool(dry_run=False)  # $0.05, next 7 days
from langchain.agents import create_agent
# agent = create_agent(model=your_model, tools=[tool])
```

Both tools take an empty argument object. `dry_run` is a developer-controlled
constructor setting, not an agent argument. The optional `event-risk` tool uses
the API defaults; query customization is intentionally omitted.
The direct client is also available as `langchain_blockchainiq.client.fetch`.

## Payment and error behavior

- `brief`: at most 10,000 USDC atomic units ($0.01); `event-risk`: at most 50,000 ($0.05).
- Only v2 exact Base USDC EIP-3009 offers are accepted. Origins and paths are fixed;
  redirects are disabled and HTTP requests have a 30-second timeout.
- Each invocation makes at most one signed retry. HTTP errors include status and
  endpoint in `BlockchainIQError`; transport and malformed protocol errors also
  raise `BlockchainIQError`. Configure agent loops carefully: each new invocation
  can purchase again. There is no persistent or cross-invocation spending budget.
- After a signed request, a network error or missing proof can mean settlement is
  uncertain. Check the wallet/API purchase record before manually retrying.

## Proof of a paid call

A live paid `/brief` call ($0.01 USDC on Base) made by this integration's
`python examples/paid_call.py` on 2026-10-28 settled in transaction
[`0xb17f5f27bce8b6b4291a57182463286ad0b18ad3a5d1beadd305dadb7ee51acb`](https://basescan.org/tx/0xb17f5f27bce8b6b4291a57182463286ad0b18ad3a5d1beadd305dadb7ee51acb)
(payer `0x7Dfe0d168B76267D6331859ACa5B1745759e2E01`, x402 v2 exact, `eip155:8453`).

Mock tests verify SDK signing and receipt extraction without spending funds.

MIT licensed. Author: Sihu Park.
