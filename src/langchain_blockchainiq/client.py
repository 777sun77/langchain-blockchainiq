"""Small, bounded x402 v2 client for the public Blockchain IQ API."""
import os
import re
from typing import Any

import httpx
from eth_account import Account
from x402 import x402ClientSync
from x402.http.utils import (
    decode_payment_required_header,
    decode_payment_response_header,
    encode_payment_signature_header,
)
from x402.mechanisms.evm.exact import ExactEvmScheme

BASE_URL = "https://www.blockchainiq.co/api/x402/v1"
NETWORK = "eip155:8453"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PRICES = {"brief": 10000, "event-risk": 50000}


class BlockchainIQError(RuntimeError):
    """HTTP, payment negotiation or settlement failure."""


def _check(response: httpx.Response) -> None:
    if not response.is_success:
        raise BlockchainIQError(
            f"Blockchain IQ GET {response.request.url.path}: HTTP {response.status_code}"
        )


def _requirements(response: httpx.Response, endpoint: str):
    try:
        required = decode_payment_required_header(response.headers["PAYMENT-REQUIRED"])
        if required.x402_version != 2:
            raise ValueError("Expected x402 v2")
        offers = [r for r in required.accepts if (
            r.scheme == "exact" and r.network == NETWORK
            and r.asset.lower() == USDC.lower()
            and 0 < int(r.amount) <= PRICES[endpoint]
            and (r.extra or {}).get("assetTransferMethod", "eip3009") == "eip3009"
        )]
        if not offers:
            raise ValueError("No exact Base USDC offer within endpoint price limit")
        return required.model_copy(update={"accepts": [offers[0]]})
    except Exception:
        raise BlockchainIQError("Invalid or unsupported PAYMENT-REQUIRED requirements") from None


def _signature(required) -> str:
    # Never accept a key as a tool argument, constructor field or file.
    key = os.environ.get("BIQ_X402_PRIVATE_KEY")
    if not key:
        raise BlockchainIQError("Set BIQ_X402_PRIVATE_KEY for a paid call")
    try:
        account = Account.from_key(key)
    except Exception:
        raise BlockchainIQError("BIQ_X402_PRIVATE_KEY is invalid") from None
    client = x402ClientSync()
    client.register(NETWORK, ExactEvmScheme(account))
    try:
        return encode_payment_signature_header(client.create_payment_payload(required))
    except Exception:
        raise BlockchainIQError("Could not sign the x402 payment authorization") from None


def fetch(endpoint: str = "brief", *, dry_run: bool = False,
          transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """Fetch once, pay only on 402, retry once, and require settlement proof.

    Dry-run uses a plain HTTP client and never reads a key or creates a signature.
    The transport argument supports offline testing; the origin is always fixed.
    """
    if endpoint not in PRICES:
        raise ValueError("endpoint must be brief or event-risk")
    try:
        with httpx.Client(timeout=30, follow_redirects=False, transport=transport) as http:
            response = http.get(f"{BASE_URL}/{endpoint}")
            if response.status_code != 402:
                _check(response)
                raise BlockchainIQError("Expected HTTP 402 payment requirements")
            required = _requirements(response, endpoint)
            if dry_run:
                sample = http.get(f"{BASE_URL}/sample")
                _check(sample)
                return {"dry_run": True,
                        "requirements": required.model_dump(by_alias=True, exclude_none=True),
                        "sample": sample.json()}
            signature = _signature(required)
            response = http.get(f"{BASE_URL}/{endpoint}",
                                headers={"PAYMENT-SIGNATURE": signature})
            _check(response)
            try:
                proof = decode_payment_response_header(response.headers["PAYMENT-RESPONSE"])
                if (not proof.success or proof.network != NETWORK
                        or not re.fullmatch(r"0x[0-9a-fA-F]{64}", proof.transaction)):
                    raise ValueError("Invalid settlement")
            except Exception:
                raise BlockchainIQError(
                    "Missing, failed or invalid PAYMENT-RESPONSE settlement proof; "
                    "payment may have settled, do not automatically retry"
                ) from None
            return {"data": response.json(), "transaction_hash": proof.transaction,
                    "settlement": proof.model_dump(by_alias=True, exclude_none=True)}
    except httpx.RequestError:
        raise BlockchainIQError(
            "Blockchain IQ network request failed; after signing, settlement may be uncertain"
        ) from None
    except ValueError as error:
        raise BlockchainIQError("Blockchain IQ returned invalid JSON") from error
