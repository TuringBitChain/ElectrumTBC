# ElectrumSV - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@gitorious
# Copyright (C) 2019-2020 The ElectrumSV Developers
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

from decimal import Decimal
from typing import Callable, Optional

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPalette, QPainter, QPaintEvent
from PyQt6.QtWidgets import (QLineEdit, QStyle, QStyleOptionFrame, QWidget)

from electrumsv.app_state import app_state
from electrumsv.util import format_satoshis_plain


class MyLineEdit(QLineEdit):
    frozen = pyqtSignal()

    def setFrozen(self, flag: bool) -> None:
        self.setReadOnly(flag)
        self.setFrame(not flag)
        self.frozen.emit()


class AmountEdit(MyLineEdit):
    shortcut = pyqtSignal()
    in_event: bool = False
    is_last_edited: bool = False

    def __init__(self, base_unit_func: Callable[[], str], parent: Optional[QWidget]=None) -> None:
        super().__init__(parent)
        # This seems sufficient for hundred-BTC amounts with 8 decimals
        self.setFixedWidth(140)
        self.base_unit_func = base_unit_func
        self.textChanged.connect(self.numbify)
        self.is_shortcut = False
        self.help_palette = QPalette()

    def decimal_point(self) -> int:
        return 8

    def numbify(self) -> None:
        text = self.text().strip()
        if text == '!':
            self.shortcut.emit()
            return
        pos = self.cursorPosition()
        chars = '0123456789.'
        s = ''.join([i for i in text if i in chars])
        if '.' in s:
            p = s.find('.')
            s = s.replace('.','')
            s = s[:p] + '.' + s[p: p + self.decimal_point()]
        self.setText(s)
        # setText sets Modified to False.  Instead we want to remember
        # if updates were because of user modification.
        self.setModified(self.hasFocus())
        self.setCursorPosition(pos)

    def paintEvent(self, event: QPaintEvent) -> None:
        QLineEdit.paintEvent(self, event)

        panel = QStyleOptionFrame()
        self.initStyleOption(panel)
        textRect = self.style().subElementRect(QStyle.SubElement.SE_LineEditContents, panel,
            self)
        textRect.adjust(2, 0, -10, 0)
        painter = QPainter(self)
        painter.setPen(self.help_palette.brush(QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Text).color())
        painter.drawText(textRect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self.base_unit_func())

    def get_amount(self) -> Optional[Decimal]:
        try:
            return Decimal(str(self.text()))
        except Exception:
            return None


class BTCAmountEdit(AmountEdit):
    def __init__(self, parent: Optional[QWidget]=None) -> None:
        super().__init__(app_state.base_unit, parent)

    def decimal_point(self) -> int:
        return app_state.decimal_point

    # NOTE(typing) Arbitrary requirement that subclasses can't do different things.
    def get_amount(self) -> Optional[int]: # type: ignore[override]
        try:
            x = Decimal(str(self.text()))
        except Exception:
            return None

        p = pow(10, self.decimal_point())
        return int( p * x )

    def setAmount(self, amount: Optional[int]) -> None:
        if amount is None:
            self.setText(" ") # Space forces repaint in case units changed
        else:
            self.setText(format_satoshis_plain(amount, self.decimal_point()))


class BTCSatsByteEdit(AmountEdit):

    def __init__(self, parent: Optional[QWidget]=None) -> None:
        super().__init__(self.base_unit, parent=parent)

    def decimal_point(self) -> int:
        return 2

    def base_unit(self) -> str:
        return 'sats/B'

    def get_satoshis_per_byte(self) -> Optional[float]:
        try:
            x = float(Decimal(str(self.text())))
        except Exception:
            return None
        return x if x > 0.0 else None

    def setAmount(self, amount: Optional[float]) -> None:
        if amount is None:
            self.setText(" ") # Space forces repaint in case units changed
        else:
            self.setText(str(round(amount*100.0)/100.0))
