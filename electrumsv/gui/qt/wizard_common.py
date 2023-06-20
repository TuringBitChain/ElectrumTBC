# Open BSV License version 4
#
# Copyright (c) 2021,2022 Bitcoin Association for BSV ("Bitcoin Association")
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# 1 - The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# 2 - The Software, and any software that is derived from the Software or parts thereof,
# can only be used on the Bitcoin SV blockchains. The Bitcoin SV blockchains are defined,
# for purposes of this license, as the Bitcoin blockchain containing block height #556767
# with the hash "000000000000000001d956714215d96ffc00e0afda4cd0a96c96f8d802b1662b" and
# that contains the longest persistent chain of blocks accepted by this Software and which
# are valid under the rules set forth in the Bitcoin white paper (S. Nakamoto, Bitcoin: A
# Peer-to-Peer Electronic Cash System, posted online October 2008) and the latest version
# of this Software available in this repository or another repository designated by Bitcoin
# Association, as well as the test blockchains that contain the longest persistent chains
# of blocks accepted by this Software and which are valid under the rules set forth in the
# Bitcoin whitepaper (S. Nakamoto, Bitcoin: A Peer-to-Peer Electronic Cash System, posted
# online October 2008) and the latest version of this Software available in this repository,
# or another repository designated by Bitcoin Association
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from enum import IntFlag
from typing import Any, cast, NamedTuple, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QWizard

from .help_dialog import HelpDialog
from .types import WizardPageProtocol
from .util import FormSectionWidget


class WizardFlag(IntFlag):
    NONE = 0

    # The wizard should offer all standard account creation options.
    STANDARD_MODE = 1
    # The wizard should only offer options that are valid as co-signers in a multisig account.
    MULTISIG_MODE = 2
    ALL_MODES = STANDARD_MODE | MULTISIG_MODE

    # Wizard completion ensures the metadata is externally accessible to the wizard invoking logic.
    METADATA_RESULT = 4
    # Completion of the wizard should result in the account being created in the invoking wallet.
    ACCOUNT_RESULT = 8
    RESULT_MASK = METADATA_RESULT | ACCOUNT_RESULT


DEFAULT_WIZARD_FLAGS = WizardFlag.STANDARD_MODE | WizardFlag.ACCOUNT_RESULT


class HelpContext(NamedTuple):
    file_name: str


class BaseWizard(QWizard):
    HELP_DIRNAME: str
    _last_page_id: Any

    def __init__(self, parent: Optional[QWidget]=None) -> None:
        super().__init__(parent, Qt.WindowType(Qt.WindowType.WindowSystemMenuHint |
            Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint))

        self.setOption(QWizard.WizardOption.IndependentPages, False)
        self.setOption(QWizard.WizardOption.NoDefaultButton, True)
        # The help button is either made visible or hidden when a page is entered, depending
        # on whether the page declares a `HELP_CONTEXT` value.
        self.setOption(QWizard.WizardOption.HaveHelpButton, True)
        self.setOption(QWizard.WizardOption.HelpButtonOnRight, False)

        self.currentIdChanged.connect(self._event_wizard_page_changed)
        self.helpRequested.connect(self._event_help_requested)

    def run(self) -> int:
        self.ensure_shown()
        return self.exec()

    def ensure_shown(self) -> None:
        self.show()
        self.raise_()

    # Wiring for pages to know when the wizard switches between them. This is important because
    # pages are instantiated on wizard creation, and reused as the user goes back and forwards
    # between them.
    # TODO: Look at using `initializePage` and `cleanupPage`.
    def _event_wizard_page_changed(self, page_id: int) -> None:
        if self._last_page_id:
            page = cast(WizardPageProtocol, self.page(self._last_page_id))
            if hasattr(page, "on_leave"):
                page.on_leave()

        self._last_page_id = page_id
        page = cast(WizardPageProtocol, self.page(page_id))
        # Only show the help button if there is help to show for the given page.
        help_context: Optional[HelpContext] = getattr(page, "HELP_CONTEXT", None)
        self.button(QWizard.WizardButton.HelpButton).setVisible(help_context is not None)

        if hasattr(page, "on_enter"):
            page.on_enter()
        else:
            button = self.button(QWizard.WizardButton.CustomButton1)
            button.setVisible(False)

    def _event_help_requested(self) -> None:
        page = self.currentPage()
        help_context: Optional[HelpContext] = getattr(page, "HELP_CONTEXT", None)
        assert help_context is not None
        h = HelpDialog(page, self.HELP_DIRNAME, help_context.file_name)
        h.run()


class WizardFormSection(FormSectionWidget):
    show_help_label: bool = False
    minimum_label_width: int = 120
