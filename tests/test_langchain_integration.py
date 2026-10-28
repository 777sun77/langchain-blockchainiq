import base64
import json

import httpx
import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from x402.http.utils import decode_payment_signature_header
from langchain_blockchainiq import BlockchainIQBriefTool, BlockchainIQEventRiskTool, BlockchainIQError
from langchain_blockchainiq.client import fetch, USDC

TX = "0x" + "ab" * 32
PAYEE = "0x617dA9383fbA67e86137BC4924b8b7E400fB7C9e"


def header(data):
    return base64.b64encode(json.dumps(data).encode()).decode()


def challenge(endpoint="brief", **changes):
    offer = dict(scheme="exact", network="eip155:8453",
                 amount="10000" if endpoint == "brief" else "50000",
                 asset=USDC, payTo=PAYEE, maxTimeoutSeconds=300,
                 extra={"name": "USD Coin", "version": "2"})
    offer.update(changes)
    return {"x402Version": 2, "resource": {"url": "https://www.blockchainiq.co/api/x402/v1/" + endpoint},
            "accepts": [offer]}


def test_paid_flow_real_sdk_signature_and_proof(monkeypatch):
    account = Account.create()  # Ephemeral test-only key; no network or funds.
    monkeypatch.setenv("BIQ_X402_PRIVATE_KEY", account.key.hex())
    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            assert "PAYMENT-SIGNATURE" not in request.headers
            return httpx.Response(402, headers={"payment-required": header(challenge())})
        payload = decode_payment_signature_header(request.headers["PAYMENT-SIGNATURE"])
        assert payload.x402_version == 2
        auth = payload.payload["authorization"]
        assert auth["from"].lower() == account.address.lower()
        assert auth["to"].lower() == PAYEE.lower()
        assert auth["value"] == "10000"
        typed = {
            "types": {"TransferWithAuthorization": [
                {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"}]},
            "primaryType": "TransferWithAuthorization",
            "domain": {"name": "USD Coin", "version": "2", "chainId": 8453, "verifyingContract": USDC},
            "message": auth,
        }
        recovered = Account.recover_message(encode_typed_data(full_message=typed),
                                            signature=payload.payload["signature"])
        assert recovered == account.address
        return httpx.Response(200, json={"coins": []}, headers={"payment-response": header(
            {"success": True, "network": "eip155:8453", "transaction": TX})})

    result = fetch(transport=httpx.MockTransport(handler))
    assert result["transaction_hash"] == TX
    assert len(seen) == 2


@pytest.mark.parametrize("endpoint", ["brief", "event-risk"])
def test_dry_run_never_reads_key_or_signs(monkeypatch, endpoint):
    import langchain_blockchainiq.client as client
    monkeypatch.setattr(client.os.environ, "get", lambda *a: pytest.fail("read environment"))
    monkeypatch.setattr(client, "_signature", lambda *a: pytest.fail("signed"))
    seen = []
    def handler(request):
        seen.append(request.url.path)
        assert "PAYMENT-SIGNATURE" not in request.headers
        if request.url.path.endswith("/sample"):
            return httpx.Response(200, json={"sample": True})
        return httpx.Response(402, headers={"payment-required": header(challenge(endpoint))})
    result = fetch(endpoint, dry_run=True, transport=httpx.MockTransport(handler))
    assert result["sample"] == {"sample": True}
    assert len(seen) == 2


@pytest.mark.parametrize("changes", [{"amount": "10001"}, {"amount": "0"},
    {"network": "eip155:1"}, {"scheme": "other"}, {"asset": "0x" + "00" * 20},
    {"extra": {"assetTransferMethod": "permit2"}}])
def test_reject_bad_offer(changes):
    with pytest.raises(BlockchainIQError, match="requirements"):
        fetch(dry_run=True, transport=httpx.MockTransport(lambda r: httpx.Response(
            402, headers={"payment-required": header(challenge(**changes))})))


@pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 503, 302])
def test_http_errors(status):
    with pytest.raises(BlockchainIQError, match=f"HTTP {status}"):
        fetch(transport=httpx.MockTransport(lambda r: httpx.Response(status)))


@pytest.mark.parametrize("proof", [None, "bad", header({"success": False, "network": "eip155:8453", "transaction": TX}),
    header({"success": True, "network": "eip155:1", "transaction": TX}),
    header({"success": True, "network": "eip155:8453", "transaction": "invalid"})])
def test_invalid_settlement(monkeypatch, proof):
    import langchain_blockchainiq.client as client
    monkeypatch.setattr(client, "_signature", lambda r: "mock-signature")
    def handler(request):
        if "PAYMENT-SIGNATURE" not in request.headers:
            return httpx.Response(402, headers={"payment-required": header(challenge())})
        return httpx.Response(200, json={}, headers={} if proof is None else {"PAYMENT-RESPONSE": proof})
    with pytest.raises(BlockchainIQError, match="settlement proof"):
        fetch(transport=httpx.MockTransport(handler))


def test_retry_402_is_bounded(monkeypatch):
    import langchain_blockchainiq.client as client
    monkeypatch.setattr(client, "_signature", lambda r: "mock-signature")
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(402, headers={"payment-required": header(challenge())})
    with pytest.raises(BlockchainIQError, match="HTTP 402"):
        fetch(transport=httpx.MockTransport(handler))
    assert len(calls) == 2


def test_missing_and_invalid_key(monkeypatch):
    transport = httpx.MockTransport(lambda r: httpx.Response(402, headers={"payment-required": header(challenge())}))
    monkeypatch.delenv("BIQ_X402_PRIVATE_KEY", raising=False)
    with pytest.raises(BlockchainIQError, match="Set BIQ_X402_PRIVATE_KEY"):
        fetch(transport=transport)
    monkeypatch.setenv("BIQ_X402_PRIVATE_KEY", "invalid-secret-do-not-echo")
    with pytest.raises(BlockchainIQError) as error:
        fetch(transport=transport)
    assert "invalid-secret-do-not-echo" not in str(error.value)


def test_framework_tools(monkeypatch):
    import langchain_blockchainiq.tools as tools
    monkeypatch.setattr(tools, "fetch", lambda endpoint, **kw: {"endpoint": endpoint, **kw})
    for cls, endpoint in [(BlockchainIQBriefTool, "brief"), (BlockchainIQEventRiskTool, "event-risk")]:
        tool = cls(dry_run=True)
        assert tool.invoke({}) == {"endpoint": endpoint, "dry_run": True}
        assert tool.args_schema.model_json_schema()["properties"] == {}


def test_malformed_challenge():
    for headers in [{}, {"payment-required": "invalid"}, {"payment-required": header({"x402Version": 1})}]:
        with pytest.raises(BlockchainIQError, match="requirements"):
            fetch(dry_run=True, transport=httpx.MockTransport(lambda r: httpx.Response(402, headers=headers)))


def test_sample_error_and_network_error():
    def handler(request):
        if request.url.path.endswith("/sample"):
            return httpx.Response(503)
        return httpx.Response(402, headers={"payment-required": header(challenge())})
    with pytest.raises(BlockchainIQError, match="HTTP 503"):
        fetch(dry_run=True, transport=httpx.MockTransport(handler))
    def broken(request):
        raise httpx.ConnectError("unavailable", request=request)
    with pytest.raises(BlockchainIQError, match="network request failed"):
        fetch(transport=httpx.MockTransport(broken))
