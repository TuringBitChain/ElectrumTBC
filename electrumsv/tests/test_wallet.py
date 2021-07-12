import os
import shutil
import sys
import tempfile
from typing import cast, Dict, Optional, List, Set
import unittest
import unittest.mock

from bitcoinx import Header
import pytest

from electrumsv.constants import (BlockHeight, CHANGE_SUBPATH, DATABASE_EXT, DerivationType,
    KeystoreTextType, RECEIVING_SUBPATH, ScriptType, StorageKind, TransactionImportFlag, TxFlags,
    unpack_derivation_path)
from electrumsv.crypto import pw_decode
from electrumsv.exceptions import InvalidPassword, IncompatibleWalletError
from electrumsv.keystore import (BIP32_KeyStore, Hardware_KeyStore,
    Imported_KeyStore, instantiate_keystore_from_text, Old_KeyStore,
    Multisig_KeyStore)
from electrumsv.networks import Net, SVMainnet, SVTestnet
from electrumsv.storage import get_categorised_files, WalletStorage, WalletStorageInfo
from electrumsv.transaction import Transaction
from electrumsv.types import MasterKeyDataBIP32, TxoKeyType
from electrumsv.wallet import (ImportedPrivkeyAccount, ImportedAddressAccount,
    MissingTransactionEntry, MultisigAccount, Wallet, StandardAccount)
from electrumsv.wallet_database import functions as db_functions
from electrumsv.wallet_database.exceptions import TransactionRemovalError
from electrumsv.wallet_database.types import AccountRow, KeyInstanceRow, TransactionLinkState, \
    WalletBalance

from .util import setup_async, MockStorage, tear_down_async, TEST_WALLET_PATH


class _TestableWallet(Wallet):
    def name(self):
        return self.__class__.__name__


def setUpModule():
    setup_async()


def tearDownModule():
    tear_down_async()


def get_categorised_files2(wallet_path: str) -> List[WalletStorageInfo]:
    matches = get_categorised_files(wallet_path)
    # In order to ensure ordering consistency, we sort the files.
    return sorted(matches, key=lambda v: v.filename)

@pytest.fixture()
def tmp_storage(tmpdir):
    return MockStorage()

@pytest.fixture(params=[SVMainnet, SVTestnet])
def network(request):
    network = request.param
    Net.set_to(network)
    yield network
    Net.set_to(SVMainnet)


class FakeSynchronizer(object):

    def __init__(self):
        self.store = []

    def add(self, address):
        self.store.append(address)


class WalletTestCase(unittest.TestCase):
    def setUp(self):
        self.user_dir = tempfile.mkdtemp()
        self.wallet_path = os.path.join(self.user_dir,
            f"somewallet-{os.urandom(4).hex()}")

    def tearDown(self):
        shutil.rmtree(self.user_dir)


# A funding transaction.
tx_hex_funding = \
    "01000000014e1653d27b6a00c174cb0e79b327cb2ac2268201533de8f5666e63101a6be46601000000" \
    "6a473044022072c3ca2a6ab271142a70e109474108b11800818acecb192325465e970ad0cccb022011" \
    "6c8c05fad2d5ab2be33ae3fc5362b7137db26d0b7ddd009ee8692daacd57914121037f37bb0d14dc72" \
    "d67f0cfb49f6472163924ba86382fd2490d5c04261386b70b0ffffffff0291ee0f00000000001976a9" \
    "14ea7804a2c266063572cc009a63dc25dcc0e9d9b588ac5883e516000000001976a914ad27edee3653" \
    "50b63b5024a8f8168e7297bdd70b88ac216e1500"

# A spending/depletion transaction for the funding transaction.
tx_hex_spend = \
    "01000000019960eee94aa89f4db93a4bc720dc9b7004127df7c115f121fee5ec7eea1e4ce200000000" \
    "6b483045022100870754d5caf0483501f9ef6b886d42add34a693808310a1199c998e827dca7520220" \
    "31d8a58435ac51fbdc94222d2781c08b2af779925f80ac5e05ed5953ae7d07a24121030b482838721a" \
    "38d94847699fed8818b5c5f56500ef72f13489e365b65e5749cfffffffff01d1ed0f00000000001976" \
    "a914ddec06c1086c07c4b1ddc4299730dacb3b25b24088ac536e1500"



def check_legacy_parent_of_standard_wallet(wallet: Wallet,
        seed_words: Optional[str]=None, is_bip39: bool=False,
        password: Optional[str]=None) -> None:
    assert len(wallet.get_accounts()) == 1
    account = cast(StandardAccount, wallet.get_accounts()[0])

    wallet_keystores = cast(List[BIP32_KeyStore], wallet.get_keystores())
    assert len(wallet_keystores) == 1
    account_keystores = cast(List[BIP32_KeyStore], account.get_keystores())
    assert len(account_keystores) == 1
    assert wallet_keystores[0] is account_keystores[0]

    assert password is not None
    assert not account_keystores[0].has_seed() or account_keystores[0].get_seed(password)
    assert type(account_keystores[0].get_passphrase(password)) is str
    assert account_keystores[0].get_master_private_key(password)

    keystore_data = wallet_keystores[0].to_derivation_data()
    assert len(keystore_data) == 5
    assert 'xpub' in keystore_data
    assert 'xprv' in keystore_data
    assert 'label' in keystore_data
    assert 'seed' in keystore_data
    assert 'passphrase' in keystore_data
    keystore_encrypted = False
    try:
        wallet_keystores[0].check_password(None)
    except InvalidPassword:
        keystore_encrypted = True
    assert "encrypted" not in wallet.name() or keystore_encrypted
    if seed_words is not None:
        assert keystore_data['seed'] == seed_words

def check_legacy_parent_of_imported_privkey_wallet(wallet: Wallet, password: str,
        keypairs: Optional[Dict[str, str]]=None) -> None:
    assert len(wallet.get_accounts()) == 1
    account = cast(ImportedPrivkeyAccount, wallet.get_accounts()[0])

    parent_keystores = wallet.get_keystores()
    assert len(parent_keystores) == 0
    child_keystores = cast(List[Imported_KeyStore], account.get_keystores())
    assert len(child_keystores) == 1
    assert child_keystores[0] is not None

    assert not child_keystores[0].has_masterkey()
    with pytest.raises(IncompatibleWalletError):
        child_keystores[0].to_masterkey_row()
    with pytest.raises(IncompatibleWalletError):
        child_keystores[0].to_derivation_data()
    child_keystore = child_keystores[0]
    assert len(child_keystore._keypairs) == 1
    if keypairs:
        for public_key in child_keystore._public_keys.values():
            encrypted_prv =  child_keystore._keypairs[public_key]
            assert pw_decode(encrypted_prv, password) == keypairs[public_key.to_hex()]


def check_legacy_parent_of_imported_address_wallet(wallet: Wallet) -> None:
    assert len(wallet.get_accounts()) == 1
    account = cast(ImportedAddressAccount, wallet.get_accounts()[0])

    assert len(wallet.get_keystores()) == 0
    assert len(account.get_keystores()) == 0


def check_legacy_parent_of_multisig_wallet(wallet: Wallet, password: str,
        seed_phrase: Optional[str]=None) -> None:
    assert len(wallet.get_accounts()) == 1
    account = cast(MultisigAccount, wallet.get_accounts()[0])

    n = account.n

    parent_keystores = wallet.get_keystores()
    assert len(parent_keystores) == 1
    keystore = cast(Multisig_KeyStore, parent_keystores[0])
    child_keystores = keystore.get_cosigner_keystores()
    assert len(child_keystores) == n
    parent_data = keystore.to_derivation_data()

    for i in range(n):
        masterkey_row = child_keystores[i].to_masterkey_row()
        assert masterkey_row.derivation_type == DerivationType.BIP32
        keystore_data = cast(MasterKeyDataBIP32, parent_data["cosigner-keys"][i][1])
        encrypted_seed = keystore_data['seed']
        if encrypted_seed is not None:
            if seed_phrase is not None:
                assert pw_decode(encrypted_seed, password) == seed_phrase
            assert keystore_data['xpub'] is not None
            assert keystore_data['xprv'] is not None
        else:
            assert keystore_data['xpub'] is not None
            assert keystore_data['xprv'] is None

def check_parent_of_blank_wallet(wallet: Wallet) -> None:
    assert len(wallet.get_accounts()) == 0
    parent_keystores = wallet.get_keystores()
    assert len(parent_keystores) == 0


def check_legacy_parent_of_hardware_wallet(wallet: Wallet) -> None:
    assert len(wallet.get_accounts()) == 1
    child_account = cast(StandardAccount, wallet.get_accounts()[0])

    parent_keystores = cast(List[Hardware_KeyStore], wallet.get_keystores())
    assert len(parent_keystores) == 1
    child_keystores = cast(List[Hardware_KeyStore], child_account.get_keystores())
    assert len(child_keystores) == 1
    assert parent_keystores[0] is child_keystores[0]

    masterkey_row = parent_keystores[0].to_masterkey_row()
    assert masterkey_row.derivation_type == DerivationType.HARDWARE
    keystore_data = parent_keystores[0].to_derivation_data()
    # General hardware wallet.
    if keystore_data['hw_type'] == "ledger":
        # Ledger wallets extend the keystore.
        assert "cfg" in keystore_data
    assert 'hw_type' in keystore_data
    assert 'label' in keystore_data
    assert "derivation" in keystore_data


def check_create_keys(wallet: Wallet, account_script_type: ScriptType) -> None:
    def check_rows(rows: List[KeyInstanceRow], script_type: ScriptType) -> None:
        for row in rows:
            assert isinstance(row.keyinstance_id, int)
            assert account.get_id() == row.account_id
            assert 1 == row.masterkey_id
            assert DerivationType.BIP32_SUBPATH == row.derivation_type
            assert None is row.description

    accounts = cast(List[StandardAccount], wallet.get_accounts())
    assert len(accounts) == 1
    account = accounts[0]
    assert [] == account.get_existing_fresh_keys(RECEIVING_SUBPATH, 1000)
    assert [] == account.get_existing_fresh_keys(CHANGE_SUBPATH, 1000)
    assert account_script_type == account.get_default_script_type()

    keyinstances: List[KeyInstanceRow] = []
    keyinstance_ids: Set[int] = set()

    for count in (0, 1, 5):
        future1, future2, new_keyinstances, new_scripthashes = \
            account.allocate_and_create_keys(count, RECEIVING_SUBPATH)
        assert count == len(new_keyinstances)
        check_rows(new_keyinstances, account_script_type)
        keyinstance_ids |= set(keyinstance.keyinstance_id for keyinstance in new_keyinstances)
        keyinstances.extend(new_keyinstances)
        assert len(keyinstance_ids) == len(keyinstances)
        # Wait for the creation to complete before we look.
        if count > 0:
            assert future2 is not None
            future2.result()
        else:
            assert future2 is None
        # Both the local list and the database result should be in the order they were created.
        assert keyinstances == \
            account.get_existing_fresh_keys(RECEIVING_SUBPATH, 1000), f"failed for {count}"

    for count in (0, 1, 5):
        local_last_row = keyinstances[-1]
        assert local_last_row.derivation_data2 is not None
        local_last_index = unpack_derivation_path(local_last_row.derivation_data2)[-1]
        next_index = account.get_next_derivation_index(RECEIVING_SUBPATH)
        assert next_index == local_last_index  + 1

        last_allocation_index = next_index + count - 1
        if count == 0:
            future4, new_keyinstances = account.derive_new_keys_until(
                RECEIVING_SUBPATH + (last_allocation_index,))
            assert future4 is None
            assert len(new_keyinstances) == 0
            continue

        future3, new_keyinstances = account.derive_new_keys_until(
            RECEIVING_SUBPATH + (last_allocation_index,))
        assert future3 is not None
        future3.result()
        assert count == len(new_keyinstances)
        check_rows(new_keyinstances, account_script_type)

        keyinstance_ids |= set(keyinstance.keyinstance_id for keyinstance in new_keyinstances)
        keyinstances.extend(new_keyinstances)
        assert len(keyinstance_ids) == len(keyinstances)
        assert keyinstances == account.get_existing_fresh_keys(RECEIVING_SUBPATH, 1000)

    keyinstance_batches: List[List[KeyInstanceRow]] = []
    for count in (0, 1, 5):
        new_keyinstances = account.get_fresh_keys(RECEIVING_SUBPATH, count)
        assert count == len(new_keyinstances)
        assert new_keyinstances == account.get_existing_fresh_keys(RECEIVING_SUBPATH, count)
        check_rows(new_keyinstances, ScriptType.NONE)
        # Verify each batch includes the last batch and the extra created keys.
        if len(keyinstance_batches) > 0:
            last_keyinstances = keyinstance_batches[-1]
            assert last_keyinstances == new_keyinstances[:len(last_keyinstances)]
        keyinstance_batches.append(new_keyinstances)



# Verify that different legacy wallets are created with correct keystores in both parent
# wallet, and account. And that the underlying data for keystore and wallet persistence
# is also exported correctly.
class TestLegacyWalletCreation:
    @unittest.mock.patch('electrumsv.wallet.app_state')
    def test_standard_electrum(self, mock_app_state, tmp_storage) -> None:
        mock_app_state.credentials.get_wallet_password = lambda wallet_path: "password"

        password = 'password'
        seed_words = 'cycle rocket west magnet parrot shuffle foot correct salt library feed song'
        child_keystore = cast(BIP32_KeyStore, instantiate_keystore_from_text(
            KeystoreTextType.ELECTRUM_SEED_WORDS, seed_words, password))

        wallet = Wallet(tmp_storage)
        masterkey_row = wallet.create_masterkey_from_keystore(child_keystore)

        raw_account_row = AccountRow(-1, masterkey_row.masterkey_id, ScriptType.P2PKH, '...')
        account_row = wallet.add_accounts([ raw_account_row ])[0]
        account = StandardAccount(wallet, account_row)
        wallet.register_account(account.get_id(), account)

        check_legacy_parent_of_standard_wallet(wallet, password=password)
        check_create_keys(wallet, account_row.default_script_type)

    @unittest.mock.patch('electrumsv.wallet.app_state')
    def test_old(self, mock_app_state, tmp_storage) -> None:
        mock_app_state.credentials.get_wallet_password = lambda wallet_path: password

        password = "password"
        seed_words = ('powerful random nobody notice nothing important '+
            'anyway look away hidden message over')
        child_keystore = cast(Old_KeyStore, instantiate_keystore_from_text(
            KeystoreTextType.ELECTRUM_OLD_SEED_WORDS, seed_words, password))
        assert isinstance(child_keystore, Old_KeyStore)

        wallet = Wallet(tmp_storage)
        masterkey_row = wallet.create_masterkey_from_keystore(child_keystore)
        account_row = AccountRow(-1, masterkey_row.masterkey_id, ScriptType.P2PKH, '...')
        account_row = wallet.add_accounts([ account_row ])[0]
        account = StandardAccount(wallet, account_row)
        wallet.register_account(account.get_id(), account)

        parent_keystores = wallet.get_keystores()
        assert len(parent_keystores) == 1
        child_keystores = account.get_keystores()
        assert len(child_keystores) == 1
        assert parent_keystores[0] is child_keystores[0]

        masterkey_row = parent_keystores[0].to_masterkey_row()
        assert masterkey_row.derivation_type == DerivationType.ELECTRUM_OLD
        keystore_data = parent_keystores[0].to_derivation_data()
        assert len(keystore_data) == 2
        assert 'mpk' in keystore_data
        assert 'seed' in keystore_data

        check_create_keys(wallet, account_row.default_script_type)

    @unittest.mock.patch('electrumsv.wallet.app_state')
    def test_imported_privkey(self, mock_app_state, tmp_storage) -> None:
        mock_app_state.app = unittest.mock.Mock()
        mock_app_state.credentials.get_wallet_password = lambda wallet_path: "password"

        wallet = Wallet(tmp_storage)
        account = wallet.create_account_from_text_entries(KeystoreTextType.PRIVATE_KEYS,
            { "KzMFjMC2MPadjvX5Cd7b8AKKjjpBSoRKUTpoAtN6B3J9ezWYyXS6" },
            "password")

        keypairs = {'02c6467b7e621144105ed3e4835b0b4ab7e35266a2ae1c4f8baa19e9ca93452997':
            'KzMFjMC2MPadjvX5Cd7b8AKKjjpBSoRKUTpoAtN6B3J9ezWYyXS6'}
        check_legacy_parent_of_imported_privkey_wallet(wallet, keypairs=keypairs,
            password='password')

    @unittest.mock.patch('electrumsv.wallet.app_state')
    def test_imported_pubkey(self, mock_app_state, tmp_storage) -> None:
        mock_app_state.credentials.get_wallet_password = lambda wallet_path: "password"
        text = """
        15hETetDmcXm1mM4sEf7U2KXC9hDHFMSzz
        1GPHVTY8UD9my6jyP4tb2TYJwUbDetyNC6
        """
        wallet = Wallet(tmp_storage)
        account = wallet.create_account_from_text_entries(KeystoreTextType.ADDRESSES,
            { "15hETetDmcXm1mM4sEf7U2KXC9hDHFMSzz", "1GPHVTY8UD9my6jyP4tb2TYJwUbDetyNC6" },
            "password")
        check_legacy_parent_of_imported_address_wallet(wallet)

    @unittest.mock.patch('electrumsv.wallet.app_state')
    def test_multisig(self, mock_app_state, tmp_storage) -> None:
        password = "my_pasword!"
        mock_app_state.credentials.get_wallet_password = lambda wallet_path: password
        wallet = Wallet(tmp_storage)

        seed_words = ('blast uniform dragon fiscal ensure vast young utility dinosaur abandon '+
            'rookie sure')
        ks1 = cast(BIP32_KeyStore, instantiate_keystore_from_text(
            KeystoreTextType.ELECTRUM_SEED_WORDS, seed_words, password))
        assert not ks1.is_watching_only()
        ks2 = cast(BIP32_KeyStore, instantiate_keystore_from_text(
            KeystoreTextType.EXTENDED_PUBLIC_KEY,
            'xpub661MyMwAqRbcGfCPEkkyo5WmcrhTq8mi3xuBS7VEZ3LYvsgY1cCFDben'
                'T33bdD12axvrmXhuX3xkAbKci3yZY9ZEk8vhLic7KNhLjqdh5ec',
            watch_only=True))

        keystore = Multisig_KeyStore({ 'm': 2, 'n': 2, "cosigner-keys": [] })
        keystore.add_cosigner_keystore(ks1)
        keystore.add_cosigner_keystore(ks2)

        assert not keystore.is_watching_only()
        assert 2 == len(keystore.get_cosigner_keystores())

        masterkey_row = wallet.create_masterkey_from_keystore(keystore)

        account_row = AccountRow(-1, masterkey_row.masterkey_id, ScriptType.MULTISIG_BARE, 'text')
        account_row = wallet.add_accounts([ account_row ])[0]
        account = MultisigAccount(wallet, account_row)
        wallet.register_account(account.get_id(), account)

        check_legacy_parent_of_multisig_wallet(wallet, password, seed_words)
        check_create_keys(wallet, account_row.default_script_type)


@pytest.mark.parametrize("storage_info", get_categorised_files2(TEST_WALLET_PATH))
@unittest.mock.patch('electrumsv.wallet.app_state')
def test_legacy_wallet_loading(mock_app_state, storage_info: WalletStorageInfo) -> None:
    password = initial_password = "123456"
    mock_app_state.credentials.get_wallet_password = lambda wallet_path: password

    # When a wallet is composed of multiple files, we need to know which to load.
    wallet_filenames = []
    if storage_info.kind != StorageKind.DATABASE:
        wallet_filenames.append(storage_info.filename)
    if storage_info.kind in (StorageKind.DATABASE, StorageKind.HYBRID):
        wallet_filenames.append(storage_info.filename + DATABASE_EXT)

    temp_dir = tempfile.mkdtemp()
    for _wallet_filename in wallet_filenames:
        source_wallet_path = os.path.join(TEST_WALLET_PATH, _wallet_filename)
        wallet_path = os.path.join(temp_dir, _wallet_filename)
        shutil.copyfile(source_wallet_path, wallet_path)

    wallet_filename = storage_info.filename
    wallet_path = os.path.join(temp_dir, wallet_filename)
    # "<expected version>_<network>_<type>[_<subtype>]"
    (expected_version_text, expected_network, expected_type, *expected_subtypes) \
        = wallet_filename.split("_")
    expected_version = int(expected_version_text)

    if "testnet" == expected_network:
        Net.set_to(SVTestnet)

    if storage_info.kind == StorageKind.HYBRID:
        pytest.xfail("old development database wallets not supported yet")

    has_password = True
    storage = WalletStorage(wallet_path)
    if "passworded" in expected_subtypes:
        text_store = storage.get_text_store()
        text_store.load_data(text_store.decrypt(initial_password))
    elif "encrypted" in expected_subtypes:
        pass
    elif expected_version >= 22:
        storage.check_password(initial_password)
    else:
        has_password = False

    storage.upgrade(has_password, initial_password)

    try:
        wallet = Wallet(storage)
    except FileNotFoundError as e:
        if sys.version_info[:3] >= (3, 8, 0):
            msg = "Could not find module 'libusb-1.0.dll' (or one of its dependencies)."
            if msg in e.args[0]:
                pytest.xfail("libusb DLL could not be found")
                return
        raise e
    except OSError as e:
        if sys.version_info[:3] < (3, 8, 0):
            if "The specified module could not be found" in e.args[1]:
                pytest.xfail("libusb DLL could not be found")
                return
        raise e

    # Store any pre-password update related data to compare against post-password update data.
    prv_keypairs: Dict[str, str] = {}
    if "imported" == expected_type and "privkey" in wallet_filename:
        assert len(wallet.get_accounts()) == 1
        private_key_account = cast(ImportedPrivkeyAccount, wallet.get_account(1))
        private_key_keystore = cast(Imported_KeyStore, private_key_account.get_keystore())
        # Pre-decrypt the prv for later comparison so the initial password is not needed there.
        for public_key, encrypted_prv in private_key_keystore._keypairs.items():
            prv_keypairs[public_key.to_hex()] = pw_decode(encrypted_prv, initial_password)

    password = "654321"
    future = wallet.update_password(initial_password, password)
    future.result(5)

    if "standard" == expected_type:
        is_bip39 = "bip39" in expected_subtypes
        check_legacy_parent_of_standard_wallet(wallet, is_bip39=is_bip39,
            password=password)
    elif "imported" == expected_type:
        if "privkey" in wallet_filename:
            check_legacy_parent_of_imported_privkey_wallet(wallet, password, prv_keypairs)
        elif "address" in expected_subtypes:
            check_legacy_parent_of_imported_address_wallet(wallet)
        else:
            raise Exception(f"unrecognised wallet file {wallet_filename}")
    elif "multisig" == expected_type:
        check_legacy_parent_of_multisig_wallet(wallet, password)
    elif "hardware" == expected_type:
        check_legacy_parent_of_hardware_wallet(wallet)
    elif "blank" == expected_type:
        check_parent_of_blank_wallet(wallet)
    else:
        raise Exception(f"unrecognised wallet file {wallet_filename}")

    if "testnet" == expected_network:
        Net.set_to(SVMainnet)


# class TestImportedPrivkeyAccount:
#     # TODO(rt12) REQUIRED add some unit tests for this account type. The following is obsolete.
#     def test_pubkeys_to_a_ddress(self, tmp_storage, network):
#         coin = network.COIN
#         privkey = PrivateKey.from_random()
#         WIF = privkey.to_WIF(coin=coin)
#         wallet = _TestableWallet(tmp_storage)
#         account = ImportedPrivkeyAccount.from_text(wallet, WIF)
#         public_key = privkey.public_key
#         address = public_key.to_address(coin=coin).to_string()
#         assert account.pubkeys_to_a_ddress(public_key) == address_from_string(address)


@pytest.mark.asyncio
@unittest.mock.patch('electrumsv.wallet.app_state')
async def test_transaction_import_removal(mock_app_state, tmp_storage) -> None:
    mock_app_state.credentials.get_wallet_password = lambda wallet_path: "password"

    # Boilerplate setting up of a deterministic account. This is copied from above.
    password = 'password'
    seed_words = 'cycle rocket west magnet parrot shuffle foot correct salt library feed song'
    child_keystore = cast(BIP32_KeyStore, instantiate_keystore_from_text(
        KeystoreTextType.ELECTRUM_SEED_WORDS, seed_words, password))

    wallet = Wallet(tmp_storage)
    masterkey_row = wallet.create_masterkey_from_keystore(child_keystore)

    raw_account_row = AccountRow(-1, masterkey_row.masterkey_id, ScriptType.P2PKH, '...')
    account_row = wallet.add_accounts([ raw_account_row ])[0]
    assert account_row.default_masterkey_id is not None
    account = StandardAccount(wallet, account_row)
    wallet.register_account(account.get_id(), account)

    # Ensure that the keys used by the transaction are present to be linked to.
    account.derive_new_keys_until(RECEIVING_SUBPATH + (2,))

    db_context = tmp_storage.get_db_context()
    db = db_context.acquire_connection()
    try:
        tx_1 = Transaction.from_hex(tx_hex_funding)
        tx_hash_1 = tx_1.hash()
        # Add the funding transaction to the database and link it to key usage.
        link_state = TransactionLinkState()
        await wallet.import_transaction_async(tx_hash_1, tx_1, TxFlags.STATE_SIGNED,
            link_state=link_state)

        # Verify the received funds are present.
        tv_rows1 = db_functions.read_transaction_values(db_context, tx_hash_1)
        assert len(tv_rows1) == 1
        assert tv_rows1[0].account_id == account.get_id()
        assert tv_rows1[0].total == 1044113

        balance = db_functions.read_account_balance(db_context, account.get_id(), 100)
        assert balance == WalletBalance(0, 0, 0, 1044113)

        balance = db_functions.read_wallet_balance(db_context, 100)
        assert balance == WalletBalance(0, 0, 0, 1044113)

        tx_2 = Transaction.from_hex(tx_hex_spend)
        tx_hash_2 = tx_2.hash()
        # Add the spending transaction to the database and link it to key usage.
        link_state = TransactionLinkState()
        await wallet.import_transaction_async(tx_hash_2, tx_2, TxFlags.STATE_SIGNED,
            link_state=link_state)

        # Verify both the received funds are present.
        tv_rows2 = db_functions.read_transaction_values(db_context, tx_hash_2)
        assert len(tv_rows2) == 1
        assert tv_rows2[0].account_id == account.get_id()
        assert tv_rows2[0].total == -1044113

        # Check the transaction balance.
        balance = db_functions.read_account_balance(db_context, account.get_id(), 100)
        assert balance == WalletBalance(0, 0, 0, 0)

        balance = db_functions.read_wallet_balance(db_context, 100)
        assert balance == WalletBalance(0, 0, 0, 0)

        # Verify all the transaction outputs are present and are linked to spending inputs.
        txof_rows = db_functions.read_transaction_outputs_full(db_context)
        assert len(txof_rows) == 3
        # tx_1.output0 is linked to the first key.
        assert txof_rows[0].tx_hash == tx_hash_1 and txof_rows[0].txo_index == 0 and \
            txof_rows[0].keyinstance_id == 1 and txof_rows[0].spending_tx_hash == tx_hash_2 and \
            txof_rows[0].spending_txi_index == 0
        # tx_1.output1 is to the payer's change and not linked.
        assert txof_rows[1].tx_hash == tx_hash_1 and txof_rows[1].txo_index == 1 and \
            txof_rows[1].keyinstance_id is None
        # tx_2.output2 is to some other payee.
        assert txof_rows[2].tx_hash == tx_hash_2 and txof_rows[2].txo_index == 0 and \
            txof_rows[2].keyinstance_id is None

        # Verify all the transactions are linked to the account.
        rows = db_functions.read_transaction_hashes(db_context, account.get_id())
        assert len(rows) == 2
        assert set(rows) == { tx_hash_1, tx_hash_2 }

        # Trying to remove the parent transaction when there is a child transaction should fail.
        with pytest.raises(TransactionRemovalError):
            wallet.remove_transaction(tx_hash_1)

        # Remove both transactions (does not delete).
        future_2 = wallet.remove_transaction(tx_hash_2)
        # We need to wait for this to succeed to delete the second. If we really wanted faster
        # removal, we would have a bulk removal function.
        future_2.result()
        future_1 = wallet.remove_transaction(tx_hash_1)
        future_1.result()

        # Verify that the transaction outputs are still linked to key usage (harmless).
        txo_rows = db_functions.read_transaction_outputs_explicit(db_context,
            [ TxoKeyType(tx_hash_1, 0) ])
        assert len(txo_rows) == 1
        # This value is not cleared. It's not a link to anything that can clash.
        assert txo_rows[0].keyinstance_id == 1

        # Verify that the account transaction link entries have been deleted.
        rows = db_functions.read_transaction_hashes(db_context, account.get_id())
        # Any rows have been deleted.
        assert len(rows) == 0

        # Verify that both transactions have been flagged as removed.
        row1 = db_functions.read_transaction_flags(db_context, tx_hash_1)
        assert row1 is not None
        assert TxFlags(row1) == TxFlags.STATE_SIGNED | TxFlags.REMOVED

        row2 = db_functions.read_transaction_flags(db_context, tx_hash_2)
        assert row2 is not None
        assert TxFlags(row2) == TxFlags.STATE_SIGNED | TxFlags.REMOVED
    finally:
        db_context.release_connection(db)


@pytest.mark.asyncio
@unittest.mock.patch('electrumsv.wallet.app_state')
async def test_reorg(mock_app_state, tmp_storage) -> None:
    """
    This test is intended to show that the current subscription mechanism combined with the
    undoing of verifications, should leave the transactions affected in state where their
    remining gets detected and adequately processed.
    """
    mock_app_state.credentials.get_wallet_password = lambda wallet_path: "password"

    # Boilerplate setting up of a deterministic account. This is copied from above.
    password = 'password'
    seed_words = 'cycle rocket west magnet parrot shuffle foot correct salt library feed song'
    child_keystore = cast(BIP32_KeyStore, instantiate_keystore_from_text(
        KeystoreTextType.ELECTRUM_SEED_WORDS, seed_words, password))

    wallet = Wallet(tmp_storage)
    masterkey_row = wallet.create_masterkey_from_keystore(child_keystore)

    raw_account_row = AccountRow(-1, masterkey_row.masterkey_id, ScriptType.P2PKH, '...')
    account_row = wallet.add_accounts([ raw_account_row ])[0]
    assert account_row.default_masterkey_id is not None
    account = StandardAccount(wallet, account_row)
    wallet.register_account(account.get_id(), account)

    # Ensure that the keys used by the transaction are present to be linked to.
    account.derive_new_keys_until(RECEIVING_SUBPATH + (2,))

    db_context = tmp_storage.get_db_context()
    db = db_context.acquire_connection()
    try:
        BLOCK_HASH = b'CAFECAFE'
        BLOCK_HEIGHT = 1000
        BLOCK_POSITION = 3
        FEE_VALUE = 12121

        ## Add a transaction that is settled.
        tx_1 = Transaction.from_hex(tx_hex_funding)
        tx_hash_1 = tx_1.hash()
        # Add the funding transaction to the database and link it to key usage.
        wallet._missing_transactions[tx_hash_1] = MissingTransactionEntry(BLOCK_HASH,
            BLOCK_HEIGHT, FEE_VALUE, TransactionImportFlag.UNSET)
        link_state = TransactionLinkState()
        await wallet.import_transaction_async(tx_hash_1, tx_1, TxFlags.STATE_SETTLED,
            link_state=link_state)

        class FakeHeader:
            timestamp: int

        fake_header = cast(Header, FakeHeader())
        fake_header.timestamp = 1

        await wallet.add_transaction_proof(tx_hash_1, BLOCK_HEIGHT, fake_header, BLOCK_POSITION,
            BLOCK_POSITION, [ b'FAFFFAFF' ] * 10)

        tx_metadata_1 = wallet.get_transaction_metadata(tx_hash_1)
        assert tx_metadata_1 is not None
        assert tx_metadata_1.block_height == BLOCK_HEIGHT
        assert tx_metadata_1.block_position == BLOCK_POSITION
        assert tx_metadata_1.fee_value == FEE_VALUE

        ## Verify that the transaction does not qualify for subscriptions.
        sub_rows = wallet.read_keys_for_transaction_subscriptions(account_row.account_id, tx_hash_1)
        assert not len(sub_rows)

        ## NOP reorg.
        # This is the height at which the blockchain was re-orged above. It should not affect the
        # transaction.
        wallet.undo_verifications(BLOCK_HEIGHT)

        # Check the flags are the same as we set.
        tx_flags1 = db_functions.read_transaction_flags(db_context, tx_hash_1)
        assert tx_flags1 is not None
        assert tx_flags1 == TxFlags.STATE_SETTLED

        # Check the mined metadata is the same as we set.
        tx_metadata_1 = wallet.get_transaction_metadata(tx_hash_1)
        assert tx_metadata_1 is not None
        assert tx_metadata_1.block_height == BLOCK_HEIGHT
        assert tx_metadata_1.block_position == BLOCK_POSITION
        assert tx_metadata_1.fee_value == FEE_VALUE

        ## Real reorg.
        wallet.undo_verifications(BLOCK_HEIGHT-1)

        # Check that the expectation is that the nodes have for now moved it back into the mempool.
        tx_flags1 = db_functions.read_transaction_flags(db_context, tx_hash_1)
        assert tx_flags1 is not None
        assert tx_flags1 == TxFlags.STATE_CLEARED

        # Check that all the mined metadata is reset to mempool state.
        tx_metadata_1 = wallet.get_transaction_metadata(tx_hash_1)
        assert tx_metadata_1 is not None
        assert tx_metadata_1.block_height == BlockHeight.MEMPOOL
        assert tx_metadata_1.block_position is None
        assert tx_metadata_1.fee_value is None

        ## Verify that the transaction now qualify for subscriptions, which would mean that
        ## we would listen for re-mining events.
        sub_rows = wallet.read_keys_for_transaction_subscriptions(account_row.account_id, tx_hash_1)
        assert len(sub_rows) == 1
        assert sub_rows[0].tx_hash == tx_hash_1
        assert sub_rows[0].put_type == 1 # Output
    finally:
        db_context.release_connection(db)


@pytest.mark.asyncio
@unittest.mock.patch('electrumsv.wallet.Wallet.get_local_height')
@unittest.mock.patch('electrumsv.wallet.app_state')
async def test_unverified_transactions(mock_app_state, get_local_height, tmp_storage) -> None:
    mock_app_state.credentials.get_wallet_password = lambda wallet_path: "password"

    # Boilerplate setting up of a deterministic account. This is copied from above.
    password = 'password'
    seed_words = 'cycle rocket west magnet parrot shuffle foot correct salt library feed song'
    child_keystore = cast(BIP32_KeyStore, instantiate_keystore_from_text(
        KeystoreTextType.ELECTRUM_SEED_WORDS, seed_words, password))

    wallet = Wallet(tmp_storage)
    masterkey_row = wallet.create_masterkey_from_keystore(child_keystore)

    raw_account_row = AccountRow(-1, masterkey_row.masterkey_id, ScriptType.P2PKH, '...')
    account_row = wallet.add_accounts([ raw_account_row ])[0]
    assert account_row.default_masterkey_id is not None
    account = StandardAccount(wallet, account_row)
    wallet.register_account(account.get_id(), account)

    # Ensure that the keys used by the transaction are present to be linked to.
    account.derive_new_keys_until(RECEIVING_SUBPATH + (2,))

    db_context = tmp_storage.get_db_context()
    db = db_context.acquire_connection()
    try:
        BLOCK_HASH = b'CAFECAFE'
        BLOCK_HEIGHT = 1000
        BLOCK_POSITION = 3
        FEE_VALUE = 12121

        ## Add a transaction that is settled.
        tx_1 = Transaction.from_hex(tx_hex_funding)
        tx_hash_1 = tx_1.hash()
        # Add the funding transaction to the database and link it to key usage.
        wallet._missing_transactions[tx_hash_1] = MissingTransactionEntry(BLOCK_HASH,
            BLOCK_HEIGHT, FEE_VALUE, TransactionImportFlag.UNSET)
        link_state = TransactionLinkState()
        await wallet.import_transaction_async(tx_hash_1, tx_1, TxFlags.STATE_CLEARED,
            link_state=link_state)

        test_block_height = BLOCK_HEIGHT
        def height_func() -> int:
            return test_block_height
        get_local_height.side_effect = height_func

        ret = await wallet.get_unverified_transactions_async()
        assert ret == { tx_hash_1: BLOCK_HEIGHT }

        # Edge case, the unverified transaction is for a later block.
        # TODO There's a question whether this is something we should flag because if we have
        #   reorged to a lower block, then the `block_height` on this matched transaction should
        #   be wrong. The reorg test above should prove it does not happen.
        test_block_height = BLOCK_HEIGHT-1
        ret = await wallet.get_unverified_transactions_async()
        assert ret == {}
    finally:
        db_context.release_connection(db)

