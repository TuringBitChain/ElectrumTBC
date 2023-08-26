#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@gitorious
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations
import time
from decimal import Decimal, InvalidOperation
from typing import cast, TYPE_CHECKING

from bitcoinx import Address, cashaddr, Script, ScriptError

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent, QFontMetrics, QTextCursor
from PyQt6.QtWidgets import QCompleter, QPlainTextEdit

from electrumsv.bitcoin import string_to_bip276_script
from electrumsv.bip276 import PREFIX_BIP276_SCRIPT
from electrumsv.constants import MAX_VALUE, PREFIX_ASM_SCRIPT
from electrumsv.exceptions import InvalidPayToError
from electrumsv.i18n import _
from electrumsv.logs import logs
from electrumsv.networks import Net
from electrumsv.transaction import XTxOutput
from electrumsv.web import is_URI, URIError

from .qrtextedit import ScanQRTextEdit
from . import util


if TYPE_CHECKING:
    from .send_view import SendView


logger = logs.get_logger("ui.paytoedit")


frozen_style = "QWidget { background-color:none; border:none;}"
normal_style = "QPlainTextEdit { }"

class PayToEdit(ScanQRTextEdit):
    ''' timestamp indicating when the user was last warned about using cash addresses. '''
    last_cashaddr_warning = None

    def __init__(self, send_view: SendView) -> None:
        super().__init__(send_view._main_window.reference())

        self._send_view = send_view
        # NOTE(typing) Bad Qt5 type stubs for `contentsChanged`.
        self.document().contentsChanged.connect(self.update_size)
        self.heightMin = 0
        self.heightMax = 150
        self._completer: QCompleter|None = None
        self.textChanged.connect(self._on_text_changed)
        self._outputs: list[XTxOutput] = []
        self._errors: list[tuple[int, str]] = []
        # Accessed by the send view.
        self.is_invoice = False
        self._ignore_uris = False
        self.update_size()
        self._payto_script: Script | None = None

    def setFrozen(self, flag: bool) -> None:
        self.setReadOnly(flag)
        self.setStyleSheet(frozen_style if flag else normal_style)
        for button in self.buttons:
            button.setHidden(flag)

    def set_validated(self) -> None:
        self.setStyleSheet(util.ColorScheme.GREEN.as_stylesheet(True))

    def set_expired(self) -> None:
        self.setStyleSheet(util.ColorScheme.RED.as_stylesheet(True))

    def _show_cashaddr_warning(self, address_text: str) -> None:
        '''
        cash addresses are not in the future for BSV. Anyone who uses one should be warned that
        they are being phased out, in order to encourage them to pre-emptively move on.
        '''
        # We only care if it is decoded, as this will be a cash address.
        try:
            cashaddr.decode(address_text)
        except Exception:
            return

        last_check_time = PayToEdit.last_cashaddr_warning
        ignore_watermark_time = time.time() - 24 * 60 * 60
        if last_check_time is None or last_check_time < ignore_watermark_time:
            PayToEdit.last_cashaddr_warning = time.time()

            message = ("<p>"+
                _("One or more of the addresses you have provided has been recognized "+
                "as a 'cash address'. For now, this is acceptable but is recommended that you get "+
                "in the habit of requesting that anyone who provides you with payment addresses "+
                "do so in the form of normal Bitcoin SV addresses.")+
                "</p>"+
                "<p>"+
                _("Within the very near future, various services and applications in the Bitcoin "+
                "SV ecosystem will stop accepting 'cash addresses'. It is in your best interest "+
                "to make sure you transition over to normal Bitcoin SV addresses as soon as "+
                "possible, in order to ensure that you can both be paid, and also get paid.")+
                "</p>"
                )
            util.MessageBox.show_warning(message, title=_("Cash address warning"))

    def _parse_tx_output(self, line: str) -> XTxOutput:
        try:
            x, y = line.split(',')
        except ValueError:
            raise InvalidPayToError(_("Invalid payment destination: {}").format(line))

        script = self._parse_output(x)
        try:
            amount = self._parse_amount(y)
        except InvalidOperation:
            raise InvalidPayToError(_("Invalid payment destination: {}").format(line))

        # NOTE(typing) attrs has typing issues.
        return XTxOutput(amount, script) # type: ignore[arg-type]

    def _parse_output(self, text: str) -> Script:
        # raises InvalidPayToError
        try:
            address = Address.from_string(text, Net.COIN)
            self._show_cashaddr_warning(text)
            return address.to_script()
        except ValueError:
            pass

        if text.startswith(PREFIX_BIP276_SCRIPT +":"):
            try:
                return string_to_bip276_script(text)
            except ValueError as e:
                raise InvalidPayToError(e.args[0])

        if text.startswith(PREFIX_ASM_SCRIPT):
            try:
                return Script.from_asm(text[len(PREFIX_ASM_SCRIPT):])
            except ScriptError as e:
                raise InvalidPayToError(e.args[0])

        raise InvalidPayToError(_("Unrecognized payment destination: {}").format(text))

    def _parse_amount(self, x: str) -> int:
        if x.strip() == '!':
            return MAX_VALUE
        p = pow(10, self._send_view.amount_e.decimal_point())
        return int(p * Decimal(x.strip()))

    def setPlainText(self, text: str, ignore_uris: bool=False) -> None:
        # We override this so that there's no infinite loop where pay_to_URI calls this then
        # the BIP276 URI is detected as a URI and we feed it back to pay_to_URI.
        self._ignore_uris = ignore_uris
        try:
            super().setPlainText(text)
        finally:
            self._ignore_uris = False

    def _on_text_changed(self) -> None:
        self._errors = []
        if self.is_invoice:
            return

        self._payto_script = None

        # filter out empty lines
        lines = [i for i in self._lines() if i]
        if len(lines) == 1:
            data = lines[0]
            if not self._ignore_uris and is_URI(data):
                self._send_view._main_window.pay_to_URI(data)
                return

            try:
                self._payto_script = self._parse_output(data)
            except InvalidPayToError:
                # We don't need to capture this error as it will be caught in the multiple-line
                # case for display.
                pass
            if self._payto_script is not None:
                self._send_view.lock_amount(False)
                return

        total = 0
        outputs = []
        is_max = False
        for i, line in enumerate(lines):
            try:
                tx_output = self._parse_tx_output(line)
            except InvalidPayToError as e:
                self._errors.append((i, e.args[0]))
                continue

            outputs.append(tx_output)
            if tx_output.value == MAX_VALUE:
                is_max = True
            else:
                total += tx_output.value

        self._send_view.set_spend_maximum(is_max)
        self._outputs = outputs
        self._payto_script = None

        if self._send_view.is_spending_maximum():
            self._send_view.do_update_fee()
        else:
            self._send_view.amount_e.setAmount(total if outputs else None)
            self._send_view.lock_amount(total > 0 or len(lines) > 1)

    def get_errors(self) -> list[tuple[int, str]]:
        return self._errors

    def get_payee_script(self) -> Script | None:
        return self._payto_script

    def get_outputs(self, is_max: bool) -> list[XTxOutput]:
        if self._payto_script is not None:
            if is_max:
                amount = MAX_VALUE
            else:
                amount = cast(int, self._send_view.amount_e.get_amount())
            # NOTE(typing) attrs has typing issues.
            self._outputs = [
                XTxOutput(amount, self._payto_script)] # type: ignore[arg-type]
        return self._outputs[:]

    def _lines(self) -> list[str]:
        return self.toPlainText().split('\n')

    def _is_multiline(self) -> bool:
        return len(self._lines()) > 1

    def paytomany(self) -> None:
        self.setText("\n\n\n")
        self.update_size()

    def update_size(self) -> None:
        lineHeight = QFontMetrics(self.document().defaultFont()).height()
        docHeight = self.document().size().height()
        h = int(docHeight * lineHeight + 11)
        if self.heightMin <= h <= self.heightMax:
            self.setMinimumHeight(h)
            self.setMaximumHeight(h)
        self.verticalScrollBar().hide()

    def set_completer(self, completer: QCompleter) -> None:
        self._completer = completer
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.activated.connect(self._insert_completion)

    def _insert_completion(self, completion: str) -> None:
        assert self._completer is not None
        if self._completer.widget() != self:
            return
        tc = self.textCursor()
        extra = len(completion) - len(self._completer.completionPrefix())
        tc.movePosition(QTextCursor.MoveOperation.Left)
        tc.movePosition(QTextCursor.MoveOperation.EndOfWord)
        tc.insertText(completion[-extra:])
        self.setTextCursor(tc)

    def _get_text_under_cursor(self) -> str:
        tc = self.textCursor()
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        return tc.selectedText()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if self.isReadOnly():
            return

        assert self._completer is not None
        if self._completer.popup().isVisible():
            if e.key() in [Qt.Key.Key_Enter, Qt.Key.Key_Return]:
                e.ignore()
                return

        if e.key() in [Qt.Key.Key_Tab]:
            e.ignore()
            return

        if e.key() in [Qt.Key.Key_Down, Qt.Key.Key_Up] and not self._is_multiline():
            e.ignore()
            return

        QPlainTextEdit.keyPressEvent(self, e)

        ctrlOrShift = e.modifiers() and \
            (Qt.KeyboardModifier.ControlModifier or Qt.KeyboardModifier.ShiftModifier)
        if self._completer is None or (ctrlOrShift and not e.text()):
            return

        eow = "~!@#$%^&*()_+{}|:\"<>?,./;'[]\\-="
        hasModifier = (e.modifiers() != Qt.KeyboardModifier.NoModifier) and \
            not ctrlOrShift
        completionPrefix = self._get_text_under_cursor()

        if hasModifier or not e.text() or len(completionPrefix) < 1 or eow.find(e.text()[-1]) >= 0:
            self._completer.popup().hide()
            return

        if completionPrefix != self._completer.completionPrefix():
            self._completer.setCompletionPrefix(completionPrefix)
            self._completer.popup().setCurrentIndex(self._completer.completionModel().index(0, 0))

        cr = self.cursorRect()
        cr.setWidth(self._completer.popup().sizeHintForColumn(0)
                    + self._completer.popup().verticalScrollBar().sizeHint().width())
        self._completer.complete(cr)

    # NOTE(typing) Signature of "qr_input" incompatible with supertype "ScanQRTextEdit"  [override]
    def qr_input(self) -> None: # type: ignore[override]
        def callback(text: str) -> None:
            # TODO Old comment. Revisit. "update fee"
            if text:
                try:
                    self._send_view._main_window.pay_to_URI(text)
                except URIError as e:
                    self._send_view._main_window.show_error(str(e))
        super(PayToEdit,self).qr_input(callback, ignore_uris=True)
