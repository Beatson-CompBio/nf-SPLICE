"""One focused view per wizard step."""

from __future__ import annotations

from nf_splice.interfaces.tui.screens.build import BuildView
from nf_splice.interfaces.tui.screens.components import ComponentsView
from nf_splice.interfaces.tui.screens.done import DoneView
from nf_splice.interfaces.tui.screens.drafts import DraftsView
from nf_splice.interfaces.tui.screens.identity import IdentityView
from nf_splice.interfaces.tui.screens.inputs import InputsView
from nf_splice.interfaces.tui.screens.migration import MigrationView
from nf_splice.interfaces.tui.screens.outputs import OutputsView
from nf_splice.interfaces.tui.screens.profiles import ProfilesView
from nf_splice.interfaces.tui.screens.provenance import ProvenanceView
from nf_splice.interfaces.tui.screens.repository import RepositoryView
from nf_splice.interfaces.tui.screens.review import ReviewView
from nf_splice.interfaces.tui.screens.welcome import WelcomeView
from nf_splice.interfaces.tui.widgets import StepView

VIEWS: dict[str, type[StepView]] = {
    view.step_id: view
    for view in (
        WelcomeView,
        RepositoryView,
        MigrationView,
        IdentityView,
        InputsView,
        OutputsView,
        ComponentsView,
        ProfilesView,
        ProvenanceView,
        DraftsView,
        ReviewView,
        BuildView,
        DoneView,
    )
}

__all__ = ["VIEWS"]
