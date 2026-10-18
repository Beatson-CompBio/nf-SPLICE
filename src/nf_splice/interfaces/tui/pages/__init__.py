"""The workspace's task pages, one per step in the rail."""

from __future__ import annotations

from nf_splice.interfaces.tui.pages.assays import AssaysPage
from nf_splice.interfaces.tui.pages.base import PageView
from nf_splice.interfaces.tui.pages.execution import ExecutionPage
from nf_splice.interfaces.tui.pages.finish import PublishPage, ReviewPage
from nf_splice.interfaces.tui.pages.identity import IdentityPage
from nf_splice.interfaces.tui.pages.outputs import OutputsPage
from nf_splice.interfaces.tui.pages.parameters import ParametersPage
from nf_splice.interfaces.tui.pages.provenance import ProvenancePage
from nf_splice.interfaces.tui.pages.software import SoftwarePage
from nf_splice.interfaces.tui.pages.start import OverviewPage, WelcomePage

PAGE_CLASSES: dict[str, type[PageView]] = {
    page.page_id: page
    for page in (
        WelcomePage,
        OverviewPage,
        IdentityPage,
        AssaysPage,
        ParametersPage,
        OutputsPage,
        SoftwarePage,
        ExecutionPage,
        ProvenancePage,
        ReviewPage,
        PublishPage,
    )
}

__all__ = ["PAGE_CLASSES", "PageView"]
