"""
Base Agent Class

Abstract base class for all agents in the multi-agent system.
Provides common functionality for messaging, logging, and execution.
"""
from abc import ABC, abstractmethod
from typing import Optional
from rich.console import Console

from models.schemas import AgentMessage, MessageType
from communication.message_bus import MessageBus
from communication.context import SharedContext

console = Console()


class BaseAgent(ABC):
    """
    Abstract base class for all agents.
    
    Each agent must implement:
    - process(): Main processing logic
    - handle_message(): Handle incoming messages from other agents
    
    Provides:
    - send_message(): Send messages to other agents
    - log(): Logging with agent name prefix
    - execute(): Run the agent's main process
    """
    
    def __init__(self, name: str, message_bus: MessageBus):
        self.name = name
        self.message_bus = message_bus
        self._register_with_bus()
        
    def _register_with_bus(self):
        """Register this agent with the message bus."""
        self.message_bus.subscribe(self.name, self._on_message)
        
    def _on_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Internal message handler that routes to handle_message."""
        return self.handle_message(message)
    
    def send_message(self,
                     recipient: str,
                     message_type: MessageType,
                     action: str,
                     payload: dict = None,
                     requires_response: bool = False,
                     conversation_id: str = None) -> Optional[AgentMessage]:
        """
        Send a message to another agent.
        
        Args:
            recipient: Name of the recipient agent or "ALL" for broadcast
            message_type: Type of message (REQUEST, RESPONSE, etc.)
            action: The action being requested or performed
            payload: Data payload for the message
            requires_response: Whether a response is expected
            conversation_id: ID for tracking conversation threads
            
        Returns:
            Response message if one is generated synchronously
        """
        message = AgentMessage(
            sender=self.name,
            recipient=recipient,
            message_type=message_type,
            action=action,
            payload=payload or {},
            requires_response=requires_response,
            conversation_id=conversation_id or "",
        )
        return self.message_bus.send(message)
    
    def log(self, message: str, style: str = ""):
        """Log a message with the agent name prefix."""
        if style:
            console.print(f"[{style}][{self.name}] {message}[/{style}]")
        else:
            console.print(f"[bold cyan][{self.name}][/bold cyan] {message}")
    
    def log_status(self, status: str):
        """Log a status update."""
        console.print(f"[dim][{self.name}] {status}[/dim]")
        
    def log_error(self, error: str):
        """Log an error."""
        console.print(f"[bold red][{self.name}] ERROR: {error}[/bold red]")
        
    def log_success(self, message: str):
        """Log a success message."""
        console.print(f"[bold green][{self.name}] [OK] {message}[/bold green]")
    
    def execute(self, context: SharedContext) -> SharedContext:
        """
        Execute the agent's main process.
        
        Args:
            context: Shared context with pipeline state
            
        Returns:
            Updated context
        """
        context.set_current_agent(self.name)
        self.log_status(f"Starting execution...")
        
        try:
            # Process any pending messages first
            pending = self.message_bus.get_pending_messages(self.name)
            for msg in pending:
                self.handle_message(msg)
            
            # Run main processing
            context = self.process(context)
            self.log_success("Execution completed")
            
        except Exception as e:
            self.log_error(str(e))
            context.add_error(f"{self.name}: {str(e)}")
            
        return context
    
    @abstractmethod
    def process(self, context: SharedContext) -> SharedContext:
        """
        Main processing logic for the agent.
        
        Args:
            context: Shared context with pipeline state
            
        Returns:
            Updated context
        """
        pass
    
    @abstractmethod
    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """
        Handle an incoming message from another agent.
        
        Args:
            message: The incoming message
            
        Returns:
            Optional response message
        """
        pass
