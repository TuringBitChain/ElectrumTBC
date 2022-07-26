"""
NOTE(AustEcon) Many of the following types are copied or slightly modified from the
ESVReferenceServer. It might be that at a later date we include a dedicated pypi package
for an ESVReferenceClient and/or use a github submodule in ElectrumSV
(or something along those lines).
"""
from __future__ import annotations
import asyncio
import concurrent.futures
import dataclasses
import enum
import logging
from enum import IntFlag
from typing import Any, Callable, NamedTuple, Optional, Sequence, TYPE_CHECKING, TypedDict

import aiohttp
from aiohttp import ClientWebSocketResponse

from ..constants import NetworkServerFlag, ServerConnectionFlag
from ..types import IndefiniteCredentialId, Outpoint, OutputSpend
from ..wallet_database.types import ServerPeerChannelMessageRow, DPPMessageRow, \
    PaymentRequestReadRow

from .constants import ServerProblemKind

if TYPE_CHECKING:
    from ..wallet import Wallet, WalletDataAccess
    from ..wallet_database.types import ServerPeerChannelRow

    from .api_server import NewServer


# ----- HeaderSV types ----- #
class HeaderResponse(TypedDict):
    hash: str
    version: int
    prevBlockHash: str
    merkleRoot: str
    creationTimestamp: int
    difficultyTarget: int
    nonce: int
    transactionCount: int
    work: int


class TipResponse(NamedTuple):
    header_bytes: bytes
    height: int


# ----- Peer Channel Types ----- #
class TokenPermissions(IntFlag):
    NONE            = 0
    READ_ACCESS     = 1 << 1
    WRITE_ACCESS    = 1 << 2


class PeerChannelToken(NamedTuple):
    remote_token_id: int
    permissions: TokenPermissions
    api_key: str


# Todo - we may need to persist a mapping of channel_id -> PeerChannelType
#  Otherwise we cannot know how to parse the received messages.
#  E.g. We need to know that a MAPICallbackResponse type json structure will be received
#  in advance to know how to parse and process it.
class PeerChannelType(IntFlag):
    NONE            = 0
    MERCHANT_API    = 1 << 1
    BACKUP          = 1 << 2


ChannelId = str
GenericJSON = dict[Any, Any]


# ViewModel refers to json response structures
class RetentionViewModel(TypedDict):
    min_age_days: int
    max_age_days: int
    auto_prune: bool


class PeerChannelAPITokenViewModelGet(TypedDict):
    id: int
    token: str
    description: str
    can_read: bool
    can_write: bool


class PeerChannelViewModelGet(TypedDict):
    id: str
    href: str
    public_read: bool
    public_write: bool
    sequenced: bool
    locked: bool
    head_sequence: int
    retention: RetentionViewModel
    access_tokens: list[PeerChannelAPITokenViewModelGet]


class GenericPeerChannelMessage(TypedDict):
    sequence: int
    received: str
    content_type: str
    payload: Any


class TipFilterPushDataMatchesData(TypedDict):
    blockId: Optional[str]
    matches: list[TipFilterPushDataMatch]


class TipFilterPushDataMatch(TypedDict):
    pushDataHashHex: str
    transactionId: str
    transactionIndex: int
    flags: int


class MessageViewModelGetBinary(TypedDict):
    sequence: int
    received: str
    content_type: str
    payload: str  # hex


# ----- General Websocket Types ----- #
class ChannelNotification(TypedDict):
    id: str
    notification: str


class ServerWebsocketNotification(TypedDict):
    message_type: str
    result: ChannelNotification  # Later this will be a Union of multiple message types


class AccountMessageKind(enum.IntEnum):
    PEER_CHANNEL_MESSAGE = 1
    SPENT_OUTPUT_EVENT = 2


class TipFilterRegistrationJobEntry(NamedTuple):
    pushdata_hash: bytes
    duration_seconds: int
    keyinstance_id: int


@dataclasses.dataclass
class TipFilterRegistrationJob:
    entries: list[TipFilterRegistrationJobEntry]

    # Input: If there is a contextual logger associated with this job it should be set here.
    logger: Optional[logging.Logger] = None
    # Input: If there is a payment request associated with this job this will be the id.
    paymentrequest_id: Optional[int] = None
    # Input: If there is a refresh callback associated with this job. This is not called the
    #    registration process, but if necessary by user logic that has a reference to the job.
    refresh_callback: Optional[Callable[[], None]] = None
    # Input: If there is a completion callback associated with this job. This is not called the
    #    registration process, but if necessary by user logic that has a reference to the job.
    completion_callback: Optional[Callable[[], None]] = None

    # Output: This will be set when the processing of this job starts.
    start_event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    # Output: This will be set when the processing of this job ends successfully or by error.
    completed_event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    # Output: If the registration succeeds this will be the UTC date the request expires.
    date_registered: Optional[int] = None
    # Output: If the registration errors this will be a description to explain why to the user.
    failure_reason: Optional[str] = None


class TipFilterRegistrationResponse(TypedDict):
    dateCreated: str


class IndexerServerSettings(TypedDict):
    tipFilterCallbackUrl: Optional[str]
    tipFilterCallbackToken: Optional[str]


ServerConnectionProblem = tuple[ServerProblemKind, str]
ServerConnectionProblems = dict[ServerProblemKind, list[str]]


@dataclasses.dataclass
class ServerConnectionState:
    petty_cash_account_id: int
    usage_flags: NetworkServerFlag
    wallet_proxy: Optional[Wallet]
    wallet_data: Optional[WalletDataAccess]
    session: aiohttp.ClientSession
    server: NewServer

    credential_id: Optional[IndefiniteCredentialId] = None
    cached_peer_channel_rows: Optional[dict[str, ServerPeerChannelRow]] = None

    # This should only be used to send problems that occur that should result in the connection
    # being closed and the user informed.
    disconnection_event_queue: asyncio.Queue[tuple[ServerProblemKind, str]] = dataclasses.field(
        default_factory=asyncio.Queue[tuple[ServerProblemKind, str]])

    # Incoming peer channel message notifications from the server.
    indexer_settings: Optional[IndexerServerSettings] = None
    # Server consuming: Post outpoints here to get them registered with the server.
    output_spend_registration_queue: asyncio.Queue[Sequence[Outpoint]] = dataclasses.field(
        default_factory=asyncio.Queue[Sequence[Outpoint]])
    # Server consuming: Incoming peer channel message notifications from the server.
    peer_channel_message_queue: asyncio.Queue[str] = dataclasses.field(
        default_factory=asyncio.Queue[str])
    # Server consuming: Set this if there are new pushdata hashes that need to be monitored.
    tip_filter_new_registration_queue: asyncio.Queue[TipFilterRegistrationJob] = \
        dataclasses.field(default_factory=asyncio.Queue[TipFilterRegistrationJob])

    # Wallet consuming: Post MAPI callback responses here to get them registered with the server.
    mapi_callback_response_queue: \
        asyncio.Queue[list[tuple[ServerPeerChannelMessageRow, GenericPeerChannelMessage]]] = \
            dataclasses.field(default_factory=asyncio.Queue[list[tuple[ServerPeerChannelMessageRow,
                GenericPeerChannelMessage]]])
    mapi_callback_response_event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    # Wallet consuming: Incoming spend notifications from the server.
    output_spend_result_queue: asyncio.Queue[Sequence[OutputSpend]] = dataclasses.field(
        default_factory=asyncio.Queue[Sequence[OutputSpend]])
    # Wallet consuming: Post tip filter matches here to get them registered with the server.
    tip_filter_matches_queue: \
        asyncio.Queue[list[tuple[ServerPeerChannelMessageRow, GenericPeerChannelMessage]]] = \
            dataclasses.field(default_factory=asyncio.Queue[list[tuple[ServerPeerChannelMessageRow,
                GenericPeerChannelMessage]]])
    # Wallet consuming: Direct payment protocol-related messages from the DPP server
    dpp_messages_queue: asyncio.Queue[DPPMessageRow] = dataclasses.field(
        default_factory=asyncio.Queue[DPPMessageRow])
    # dpp_invoice ID -> open websocket. If websocket is None, it means the ws:// is closed
    dpp_websockets: dict[str, Optional[ClientWebSocketResponse]] = dataclasses.field(
        default_factory=dict[str, Optional[ClientWebSocketResponse]])
    # Adding a payment_request_id to this queue results in opening a dpp websocket
    active_invoices_queue: asyncio.Queue[PaymentRequestReadRow] = dataclasses.field(
        default_factory=asyncio.Queue[PaymentRequestReadRow])

    # The stage of the connection process it has last reached.
    connection_flags: ServerConnectionFlag = ServerConnectionFlag.INITIALISED
    stage_change_event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    upgrade_lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)

    # Wallet individual futures (all servers).
    stage_change_pipeline_future: Optional[concurrent.futures.Future[None]] = None
    connection_future: Optional[concurrent.futures.Future[ServerConnectionProblems]] = None

    # Wallet individual futures (servers used for blockchain services only).
    mapi_callback_consumer_future: Optional[concurrent.futures.Future[None]] = None
    output_spends_consumer_future: Optional[concurrent.futures.Future[None]] = None
    tip_filter_consumer_future: Optional[concurrent.futures.Future[None]] = None
    # For each DPP Proxy server there is a manager task to create ws:// connections and
    # a corresponding consumer task associated with the `Wallet` instance (which uses a shared
    # queue)
    manage_dpp_connections_future: Optional[concurrent.futures.Future[None]] = None
    dpp_consumer_future: Optional[concurrent.futures.Future[None]] = None

    # Server websocket-related futures.
    websocket_futures: list[concurrent.futures.Future[None]] = dataclasses.field(
        default_factory=list[concurrent.futures.Future[None]])

    @property
    def used_with_reference_server_api(self) -> bool:
        return self.usage_flags & NetworkServerFlag.MASK_UTILISATION != 0

    def clear_for_reconnection(self, clear_flags: ServerConnectionFlag=ServerConnectionFlag.NONE) \
            -> None:
        self.connection_flags = clear_flags | ServerConnectionFlag.INITIALISED
        self.stage_change_event.set()
        self.stage_change_event.clear()

        self.cached_peer_channel_rows = None
        self.indexer_settings = None

        # When we establish a new websocket we will register all the outstanding output spend
        # registrations that we need, so whatever is left in the queue at this point is redundant.
        while not self.output_spend_registration_queue.empty():
            self.output_spend_registration_queue.get_nowait()
        while not self.peer_channel_message_queue.empty():
            self.peer_channel_message_queue.get_nowait()
        while not self.disconnection_event_queue.empty():
            self.disconnection_event_queue.get_nowait()


class VerifiableKeyData(TypedDict):
    public_key_hex: str
    signature_hex: str
    message_hex: str
