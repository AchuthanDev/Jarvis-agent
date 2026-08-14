"""Permission policy for tool execution.

The LLM never decides whether an action is allowed — tools declare a risk
level, and this policy gates execution independently:

- explicit ``deny`` rows in the ``permissions`` table always win;
- otherwise the tool's risk must be at or below the configured
  ``TOOL_MAX_AUTONOMOUS_RISK`` (default 1).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.tools.base import ToolContext
from database.models import Permission

EFFECT_DENY = "deny"
EFFECT_ALLOW = "allow"


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    allowed: bool
    reason: str


class PermissionPolicy:
    def __init__(self, max_autonomous_risk: int = 1) -> None:
        self.max_autonomous_risk = max_autonomous_risk

    async def decide(
        self,
        session: AsyncSession | None,
        context: ToolContext,
        tool_name: str,
        risk: int,
    ) -> PermissionDecision:
        override = await self._explicit_rule(session, context, tool_name)
        if override is not None:
            allowed = override == EFFECT_ALLOW
            return PermissionDecision(
                allowed=allowed,
                reason=(
                    "denied by explicit permission rule"
                    if not allowed
                    else "allowed by explicit permission rule"
                ),
            )
        if risk <= self.max_autonomous_risk:
            return PermissionDecision(
                allowed=True,
                reason=f"risk {risk} within autonomous threshold {self.max_autonomous_risk}",
            )
        return PermissionDecision(
            allowed=False,
            reason=(
                f"tool risk {risk} exceeds the autonomous threshold "
                f"{self.max_autonomous_risk} (approval required)"
            ),
        )

    async def _explicit_rule(
        self,
        session: AsyncSession | None,
        context: ToolContext,
        tool_name: str,
    ) -> str | None:
        """Return 'allow'/'deny' from a matching permissions row, or ``None``."""
        if session is None:
            return None
        stmt = select(Permission).where(Permission.tool == tool_name)
        if context.user_id is not None:
            stmt = stmt.where(Permission.user_id.is_(None) | (Permission.user_id == context.user_id))
        else:
            stmt = stmt.where(Permission.user_id.is_(None))
        if context.device_id is not None:
            stmt = stmt.where(
                Permission.device_id.is_(None) | (Permission.device_id == context.device_id)
            )
        else:
            stmt = stmt.where(Permission.device_id.is_(None))
        rows = list((await session.scalars(stmt)).all())
        # Deny wins over allow.
        if any(row.effect == EFFECT_DENY for row in rows):
            return EFFECT_DENY
        if any(row.effect == EFFECT_ALLOW for row in rows):
            return EFFECT_ALLOW
        return None
