"""
Message Bus for Agent-to-Agent Communication

This module provides the communication infrastructure that allows agents
to send messages to each other, enabling autonomous negotiation and collaboration.
"""
from collections import defaultdict
from datetime import datetime
from typing import Callable, Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from models.schemas import AgentMessage, MessageType

console = Console()


class MessageBus:
    """
    Central message bus for agent communication.
    
    Features:
    - Point-to-point messaging between agents
    - Broadcast messaging to all agents
    - Message history tracking
    - Subscription-based message handling
    - Verbose mode for debugging agent conversations
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._message_history: list[AgentMessage] = []
        self._pending_messages: dict[str, list[AgentMessage]] = defaultdict(list)
        
    def subscribe(self, agent_name: str, handler: Callable[[AgentMessage], None]):
        """
        Subscribe an agent to receive messages.
        
        Args:
            agent_name: Name of the agent subscribing
            handler: Callback function to handle incoming messages
        """
        self._subscribers[agent_name].append(handler)
        
    def unsubscribe(self, agent_name: str):
        """Remove all subscriptions for an agent."""
        if agent_name in self._subscribers:
            del self._subscribers[agent_name]
    
    def send(self, message: AgentMessage) -> Optional[AgentMessage]:
        """
        Send a message from one agent to another.
        
        Args:
            message: The message to send
            
        Returns:
            Response message if one is generated synchronously
        """
        self._message_history.append(message)
        
        if self.verbose:
            self._display_message(message)
        
        # Handle broadcast messages
        if message.recipient == "ALL":
            for agent_name, handlers in self._subscribers.items():
                if agent_name != message.sender:
                    for handler in handlers:
                        handler(message)
            return None
        
        # Handle point-to-point messages
        if message.recipient in self._subscribers:
            for handler in self._subscribers[message.recipient]:
                response = handler(message)
                if response:
                    self._message_history.append(response)
                    if self.verbose:
                        self._display_message(response)
                    return response
        else:
            # Queue message for later if recipient not yet subscribed
            self._pending_messages[message.recipient].append(message)
            
        return None
    
    def get_pending_messages(self, agent_name: str) -> list[AgentMessage]:
        """Get and clear pending messages for an agent."""
        messages = self._pending_messages.pop(agent_name, [])
        return messages
    
    def get_history(self, 
                    sender: Optional[str] = None,
                    recipient: Optional[str] = None,
                    conversation_id: Optional[str] = None) -> list[AgentMessage]:
        """
        Get message history with optional filters.
        
        Args:
            sender: Filter by sender agent
            recipient: Filter by recipient agent
            conversation_id: Filter by conversation thread
            
        Returns:
            List of matching messages
        """
        messages = self._message_history
        
        if sender:
            messages = [m for m in messages if m.sender == sender]
        if recipient:
            messages = [m for m in messages if m.recipient == recipient]
        if conversation_id:
            messages = [m for m in messages if m.conversation_id == conversation_id]
            
        return messages
    
    def get_conversation_summary(self) -> str:
        """Generate a summary of all agent conversations."""
        if not self._message_history:
            return "No messages exchanged yet."
        
        lines = []
        for msg in self._message_history:
            timestamp = msg.timestamp.strftime("%H:%M:%S")
            lines.append(f"[{timestamp}] {msg.sender} -> {msg.recipient}: {msg.action}")
        
        return "\n".join(lines)
    
    def _display_message(self, message: AgentMessage):
        """Display a message in the console with rich formatting."""
        # Color coding by message type
        colors = {
            MessageType.REQUEST: "cyan",
            MessageType.RESPONSE: "green",
            MessageType.DISPUTE: "yellow",
            MessageType.CONFIRM: "blue",
            MessageType.ERROR: "red",
            MessageType.STATUS: "magenta",
        }
        
        color = colors.get(message.message_type, "white")
        
        # Format the message
        header = Text()
        header.append(f"[{message.sender}", style=f"bold {color}")
        header.append(" → ", style="white")
        header.append(f"{message.recipient}]", style=f"bold {color}")
        header.append(f" {message.message_type.value}", style=f"dim {color}")
        
        content = Text()
        content.append(f"Action: ", style="dim")
        content.append(f"{message.action}\n", style="bold")
        
        if message.payload:
            # Show a summary of payload, not the whole thing
            payload_preview = str(message.payload)[:200]
            if len(str(message.payload)) > 200:
                payload_preview += "..."
            content.append(f"Payload: {payload_preview}", style="dim")
        
        panel = Panel(
            content,
            title=header,
            border_style=color,
            padding=(0, 1),
        )
        console.print(panel)


class ConversationThread:
    """
    Represents a conversation thread between agents.
    Used for tracking multi-turn exchanges.
    """
    
    def __init__(self, conversation_id: str, initiator: str, topic: str):
        self.conversation_id = conversation_id
        self.initiator = initiator
        self.topic = topic
        self.messages: list[AgentMessage] = []
        self.status: str = "open"  # open, resolved, disputed
        self.created_at: datetime = datetime.now()
        self.resolved_at: Optional[datetime] = None
        
    def add_message(self, message: AgentMessage):
        """Add a message to this conversation thread."""
        self.messages.append(message)
        
    def resolve(self, resolution: str = "completed"):
        """Mark the conversation as resolved."""
        self.status = resolution
        self.resolved_at = datetime.now()
        
    def get_summary(self) -> dict:
        """Get a summary of this conversation."""
        return {
            "id": self.conversation_id,
            "initiator": self.initiator,
            "topic": self.topic,
            "message_count": len(self.messages),
            "status": self.status,
            "participants": list(set(m.sender for m in self.messages)),
        }
