"""Optional, provider-neutral agent integration (off by default).

Importing this package never imports a provider SDK. The deterministic
services remain the only source of validation and truth.
"""

from nf_splice.agents.orchestration import (
    AgentRunResult,
    ConsentRequired,
    approve,
    reject,
    run_agent,
)
from nf_splice.agents.policy import AgentPolicy, PolicyViolation
from nf_splice.agents.protocol import (
    AgentEvent,
    AgentMode,
    AgentProvider,
    EventKind,
    ProviderCapabilities,
    SessionLimits,
)
from nf_splice.agents.tools import AgentToolbox, Proposal, ProposalBook, ProposalStatus

__all__ = [
    "AgentEvent",
    "AgentMode",
    "AgentPolicy",
    "AgentProvider",
    "AgentRunResult",
    "AgentToolbox",
    "ConsentRequired",
    "EventKind",
    "PolicyViolation",
    "Proposal",
    "ProposalBook",
    "ProposalStatus",
    "ProviderCapabilities",
    "SessionLimits",
    "approve",
    "reject",
    "run_agent",
]
