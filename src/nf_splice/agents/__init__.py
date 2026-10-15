"""Agentic integration: three ways to work, one deterministic engine.

- **Manual**: the person drives the CLI or wizard; *Ask AI* answers
  contextual questions with read-only tools and never takes control
  (:func:`ask_for_help`).
- **AI-assisted**: a persistent session in which the agent proposes each
  stage, the person approves, questions or objects, and approved changes are
  applied and validated (:class:`SessionEngine`).
- **Autonomous**: within a scope and policy the person approves, the agent
  works through every stage unattended and reports, truthfully, what is
  complete and what is blocked.

Importing this package never imports a provider SDK. nf-splice's
deterministic services remain the only writers and validators of SPLICE
files in every mode.
"""

from nf_splice.agents.engine import SessionEngine, StaleProposal
from nf_splice.agents.help import HelpAnswer, ask_for_help
from nf_splice.agents.permissions import (
    Budgets,
    ExecutionPolicy,
    Permission,
    PolicyViolation,
    validate_grants,
)
from nf_splice.agents.protocol import (
    AgentEvent,
    AgentProvider,
    CapabilityError,
    ConsentRequired,
    EventKind,
    ProviderCapabilities,
    ProviderUnavailable,
    TurnRequest,
)
from nf_splice.agents.stages import Stage, StageStatus
from nf_splice.agents.state import (
    InteractionMode,
    SessionError,
    SessionState,
    SessionStatus,
    SessionStore,
)

__all__ = [
    "AgentEvent",
    "AgentProvider",
    "Budgets",
    "CapabilityError",
    "ConsentRequired",
    "EventKind",
    "ExecutionPolicy",
    "HelpAnswer",
    "InteractionMode",
    "Permission",
    "PolicyViolation",
    "ProviderCapabilities",
    "ProviderUnavailable",
    "SessionEngine",
    "SessionError",
    "SessionState",
    "SessionStatus",
    "SessionStore",
    "Stage",
    "StageStatus",
    "StaleProposal",
    "TurnRequest",
    "ask_for_help",
    "validate_grants",
]
