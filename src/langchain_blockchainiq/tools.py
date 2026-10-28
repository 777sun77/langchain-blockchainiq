"""Framework-native tools. Each invocation can purchase one response."""
from typing import Type
from pydantic import BaseModel
from langchain_core.tools import BaseTool
from .client import fetch


class NoArguments(BaseModel):
    """This API resource takes no arguments."""


class BlockchainIQBriefTool(BaseTool):
    name: str = "blockchainiq_brief"
    description: str = "Get BTC, ETH, SOL and XRP market brief. Costs $0.01 USDC on Base per invocation."
    args_schema: Type[BaseModel] = NoArguments
    dry_run: bool = False

    def _run(self) -> dict:
        return fetch("brief", dry_run=self.dry_run)


class BlockchainIQEventRiskTool(BaseTool):
    name: str = "blockchainiq_event_risk"
    description: str = "Get scheduled event risk for the next seven days. Costs $0.05 USDC on Base per invocation."
    args_schema: Type[BaseModel] = NoArguments
    dry_run: bool = False

    def _run(self) -> dict:
        return fetch("event-risk", dry_run=self.dry_run)
