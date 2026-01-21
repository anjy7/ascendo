"""
Pydantic models for data structures used across agents.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class MessageType(str, Enum):
    """Types of messages agents can send."""
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    DISPUTE = "DISPUTE"
    CONFIRM = "CONFIRM"
    ERROR = "ERROR"
    STATUS = "STATUS"


class Speaker(BaseModel):
    """A conference speaker."""
    name: str
    title: str = ""
    company: str = ""
    bio: str = ""
    session_title: str = ""
    linkedin_url: str = ""
    
    def __hash__(self):
        return hash((self.name, self.company))


class Attendee(BaseModel):
    """A conference attendee."""
    name: str
    title: str = ""
    company: str = ""
    
    def __hash__(self):
        return hash((self.name, self.company))


class Company(BaseModel):
    """A company extracted from conference data."""
    name: str
    industry: str = ""
    size: Optional[int] = None  # employee count
    size_category: str = ""  # "Small", "Mid-market", "Enterprise"
    headquarters: str = ""
    website: str = ""
    description: str = ""
    source: str = ""  # "logo", "speaker", "attendee"
    speakers: list[str] = Field(default_factory=list)
    attendees: list[str] = Field(default_factory=list)
    
    def __hash__(self):
        return hash(self.name)


class ICPResult(BaseModel):
    """Result of ICP validation for a company."""
    company_name: str
    score: int = Field(ge=0, le=100)
    fit_level: str  # "High", "Medium", "Low"
    reasoning: str
    industry_score: int = 0
    title_score: int = 0
    department_score: int = 0
    size_score: int = 0
    speaker_bonus: int = 0
    validated_by: str = ""
    disputed: bool = False
    dispute_reason: str = ""
    final_score: Optional[int] = None


class ConferenceData(BaseModel):
    """All data extracted from a conference website."""
    url: str
    conference_name: str = ""
    date: str = ""
    location: str = ""
    speakers: list[Speaker] = Field(default_factory=list)
    attendees: list[Attendee] = Field(default_factory=list)
    companies: list[Company] = Field(default_factory=list)
    scraped_at: datetime = Field(default_factory=datetime.now)


class AgentMessage(BaseModel):
    """Message passed between agents."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    sender: str
    recipient: str  # Agent name or "ALL" for broadcast
    message_type: MessageType
    action: str  # e.g., "validate_company", "enrich_data", "confirm_score"
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_response: bool = False
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = Field(default_factory=datetime.now)
    
    def __str__(self):
        return f"[{self.sender} -> {self.recipient}] {self.message_type.value}: {self.action}"


class AgentContext(BaseModel):
    """Shared context passed between agents in the pipeline."""
    url: str
    conference_data: Optional[ConferenceData] = None
    icp_results: list[ICPResult] = Field(default_factory=list)
    messages: list[AgentMessage] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    status: str = "initialized"
    current_agent: str = ""
    verbose: bool = False
    
    def add_message(self, message: AgentMessage):
        """Add a message to the context."""
        self.messages.append(message)
    
    def get_messages_for(self, agent_name: str) -> list[AgentMessage]:
        """Get all messages intended for a specific agent."""
        return [
            m for m in self.messages 
            if m.recipient == agent_name or m.recipient == "ALL"
        ]
    
    def get_conversation(self, conversation_id: str) -> list[AgentMessage]:
        """Get all messages in a conversation thread."""
        return [m for m in self.messages if m.conversation_id == conversation_id]
