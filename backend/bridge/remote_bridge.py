"""Remote bridge for TenderClaw — enables remote connections."""

from dataclasses import dataclass, field
from enum import Enum
import uuid
import jwt
from datetime import datetime, timedelta


class BridgeState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"


@dataclass
class RemoteSession:
    id: str
    bridge_id: str
    client_id: str
    state: BridgeState = BridgeState.DISCONNECTED
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class BridgeConfig:
    host: str = "0.0.0.0"
    port: int = 7001
    jwt_secret: str = "change-me-in-production"
    jwt_expiry_hours: int = 24
    max_sessions: int = 10
    heartbeat_interval: int = 30


class RemoteBridge:
    """Manages remote connections to TenderClaw."""

    def __init__(self, config: BridgeConfig | None = None):
        self.config = config or BridgeConfig()
        self.sessions: dict[str, RemoteSession] = {}
        self._active = False

    def generate_token(self, session_id: str, client_id: str) -> str:
        """Generate JWT token for a session."""
        payload = {
            "session_id": session_id,
            "client_id": client_id,
            "exp": datetime.utcnow() + timedelta(hours=self.config.jwt_expiry_hours),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, self.config.jwt_secret, algorithm="HS256")

    def verify_token(self, token: str) -> dict | None:
        """Verify and decode JWT token."""
        try:
            return jwt.decode(token, self.config.jwt_secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    async def connect(self, client_id: str) -> tuple[str, str]:
        """Create a new remote session and return (session_id, token)."""
        if len(self.sessions) >= self.config.max_sessions:
            raise RuntimeError("Maximum sessions reached")

        session_id = str(uuid.uuid4())
        token = self.generate_token(session_id, client_id)

        session = RemoteSession(
            id=session_id,
            bridge_id=str(uuid.uuid4()),
            client_id=client_id,
            state=BridgeState.CONNECTING,
        )
        self.sessions[session_id] = session
        return session_id, token

    async def authenticate(self, session_id: str, token: str) -> bool:
        """Authenticate a session with token."""
        if session_id not in self.sessions:
            return False

        payload = self.verify_token(token)
        if not payload:
            return False

        if payload.get("session_id") != session_id:
            return False

        session = self.sessions[session_id]
        session.state = BridgeState.AUTHENTICATED
        session.last_activity = datetime.utcnow()
        return True

    def disconnect(self, session_id: str) -> bool:
        """Disconnect a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def get_session(self, session_id: str) -> RemoteSession | None:
        """Get session by ID."""
        return self.sessions.get(session_id)

    def list_sessions(self) -> list[RemoteSession]:
        """List all active sessions."""
        return list(self.sessions.values())

    def cleanup_stale_sessions(self, timeout_seconds: int = 300):
        """Remove sessions with no activity."""
        now = datetime.utcnow()
        stale = [
            sid for sid, s in self.sessions.items()
            if (now - s.last_activity).total_seconds() > timeout_seconds
        ]
        for sid in stale:
            self.disconnect(sid)


remote_bridge = RemoteBridge()
