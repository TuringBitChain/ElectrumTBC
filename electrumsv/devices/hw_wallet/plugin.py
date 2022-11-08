#!/usr/bin/env python2
# -*- mode: python -*-
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2016  The Electrum developers
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

import threading
from typing import Any, List, Optional, Tuple, Type, TYPE_CHECKING

from bitcoinx import BIP32PublicKey

from ...i18n import _
from ...logs import logs
from ...types import MasterKeyDataHardware
from ...util import versiontuple

if TYPE_CHECKING:
    from ...device import Device, DeviceInfo
    from ...keystore import Hardware_KeyStore
    from ...wallet_database.types import MasterKeyRow
    from ...gui.qt.account_wizard import AccountWizard
    from ...gui.qt.util import WindowProtocol
    from ..hw_wallet.qt import QtHandlerBase


class HW_PluginBase(object):
    keystore_class: Type["Hardware_KeyStore"]
    libraries_available_message: str
    libraries_available: bool
    DEVICE_IDS: List[Any]

    hid_lock = threading.Lock()

    def __init__(self, device_kind: str) -> None:
        self.device: str = self.keystore_class.device
        self.name = device_kind
        self.logger = logs.get_logger(device_kind)

    def create_keystore(self, data: MasterKeyDataHardware, row: Optional['MasterKeyRow']) \
            -> 'Hardware_KeyStore':
        keystore = self.keystore_class(data, row)
        keystore.plugin = self
        return keystore

    def create_handler(self, window: "WindowProtocol") -> "QtHandlerBase":
        raise NotImplementedError

    def create_client(self, device: "Device", handler: "QtHandlerBase") -> Any:
        raise NotImplementedError
            # -> Optional[DigitalBitbox_Client]:

    def is_enabled(self) -> bool:
        return True

    def get_library_version(self) -> str:
        """Returns the version of the 3rd party python library
        for the hw wallet. For example '0.9.0'

        Returns 'unknown' if library is found but cannot determine version.
        Raises 'ImportError' if library is not found.
        Raises 'LibraryFoundButUnusable' if found but there was a problem (includes version num).
        """
        raise NotImplementedError()

    def check_libraries_available(self) -> bool:
        def version_str(t: Tuple[int]) -> str:
            return ".".join(str(i) for i in t)

        try:
            # this might raise ImportError or LibraryFoundButUnusable
            library_version = self.get_library_version()
            # if no exception so far, we might still raise LibraryFoundButUnusable
            if (library_version == 'unknown' or
                    versiontuple(library_version) < self.minimum_library or  # type: ignore
                    hasattr(self, "maximum_library") and
                    versiontuple(library_version) >= self.maximum_library):
                raise LibraryFoundButUnusable(library_version=library_version)
        except ImportError:
            return False
        except LibraryFoundButUnusable as e:
            library_version = e.library_version
            max_version_str = (version_str(self.maximum_library)
                               if hasattr(self, "maximum_library") else "inf")
            self.libraries_available_message = (
                    _("Library version for '{}' is incompatible.").format(self.name)
                    + '\nInstalled: {}, Needed: {} <= x < {}'
                    .format(library_version,
                            version_str(self.minimum_library),  # type: ignore
                            max_version_str))
            self.logger.warning(self.libraries_available_message)
            return False

        return True

    def get_library_not_available_message(self) -> str:
        if hasattr(self, 'libraries_available_message'):
            message = self.libraries_available_message
        else:
            message = _("Missing libraries for {}.").format(self.name)
        message += '\n' + _("Make sure you install it with python3")
        return message

    def setup_device(self, device_info: "DeviceInfo", wizard: "AccountWizard") -> None:
        raise NotImplementedError

    def enumerate_devices(self) -> List["Device"]:
        raise NotImplementedError

    def get_master_public_key(self, device_id: str, derivation: str, wizard: "AccountWizard") \
            -> BIP32PublicKey:
        raise NotImplementedError


class LibraryFoundButUnusable(Exception):
    def __init__(self, library_version: str='unknown') -> None:
        super().__init__()
        self.library_version = library_version
