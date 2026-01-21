"""
Shared Context Manager for Agent Pipeline

Manages the shared state that flows through the agent pipeline,
enabling agents to access and modify common data.
"""
from datetime import datetime
from typing import Any, Optional
from models.schemas import AgentContext, ConferenceData, ICPResult, AgentMessage


class SharedContext:
    """
    Manages shared context for the agent pipeline.
    
    This class wraps AgentContext and provides additional
    functionality for tracking pipeline state and agent interactions.
    """
    
    def __init__(self, url: str, verbose: bool = False):
        self.context = AgentContext(url=url, verbose=verbose)
        self._checkpoints: dict[str, AgentContext] = {}
        self._start_time: datetime = datetime.now()
        
    @property
    def url(self) -> str:
        return self.context.url
    
    @property
    def verbose(self) -> bool:
        return self.context.verbose
    
    @property
    def conference_data(self) -> Optional[ConferenceData]:
        return self.context.conference_data
    
    @conference_data.setter
    def conference_data(self, data: ConferenceData):
        self.context.conference_data = data
        
    @property
    def icp_results(self) -> list[ICPResult]:
        return self.context.icp_results
    
    @property
    def messages(self) -> list[AgentMessage]:
        return self.context.messages
    
    @property
    def errors(self) -> list[str]:
        return self.context.errors
        
    def set_current_agent(self, agent_name: str):
        """Set the currently active agent."""
        self.context.current_agent = agent_name
        
    def set_status(self, status: str):
        """Update pipeline status."""
        self.context.status = status
        
    def add_icp_result(self, result: ICPResult):
        """Add an ICP validation result."""
        # Check if we already have a result for this company
        existing = next(
            (r for r in self.context.icp_results if r.company_name == result.company_name),
            None
        )
        if existing:
            # Update existing result
            idx = self.context.icp_results.index(existing)
            self.context.icp_results[idx] = result
        else:
            self.context.icp_results.append(result)
            
    def add_message(self, message: AgentMessage):
        """Add a message to the conversation history."""
        self.context.add_message(message)
        
    def add_error(self, error: str):
        """Record an error."""
        self.context.errors.append(error)
        
    def create_checkpoint(self, name: str):
        """
        Create a checkpoint of current state.
        Useful for rollback if an agent fails.
        """
        self._checkpoints[name] = self.context.model_copy(deep=True)
        
    def restore_checkpoint(self, name: str) -> bool:
        """Restore state from a checkpoint."""
        if name in self._checkpoints:
            self.context = self._checkpoints[name].model_copy(deep=True)
            return True
        return False
        
    def get_companies(self) -> list[str]:
        """Get list of unique company names from conference data."""
        if not self.context.conference_data:
            return []
            
        companies = set()
        
        # From explicit company list
        for company in self.context.conference_data.companies:
            companies.add(company.name)
            
        # From speakers
        for speaker in self.context.conference_data.speakers:
            if speaker.company:
                companies.add(speaker.company)
                
        # From attendees
        for attendee in self.context.conference_data.attendees:
            if attendee.company:
                companies.add(attendee.company)
                
        return list(companies)
    
    def get_company_details(self, company_name: str) -> dict[str, Any]:
        """Get all known details about a company."""
        if not self.context.conference_data:
            return {"name": company_name}
            
        details = {"name": company_name, "speakers": [], "attendees": []}
        
        # Find company record and copy relevant fields (not speakers/attendees lists)
        for company in self.context.conference_data.companies:
            if company.name.lower() == company_name.lower():
                details["industry"] = company.industry
                details["size"] = company.size
                details["size_category"] = company.size_category
                details["headquarters"] = company.headquarters
                details["website"] = company.website
                details["description"] = company.description
                details["source"] = company.source
                break
                
        # Find speakers from this company (build proper dict structure)
        for speaker in self.context.conference_data.speakers:
            if speaker.company.lower() == company_name.lower():
                details["speakers"].append({
                    "name": speaker.name,
                    "title": speaker.title,
                })
                
        # Find attendees from this company
        for attendee in self.context.conference_data.attendees:
            if attendee.company.lower() == company_name.lower():
                details["attendees"].append({
                    "name": attendee.name,
                    "title": attendee.title,
                })
                
        return details
    
    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the current pipeline state."""
        stats = {
            "url": self.context.url,
            "status": self.context.status,
            "current_agent": self.context.current_agent,
            "message_count": len(self.context.messages),
            "error_count": len(self.context.errors),
            "elapsed_time": (datetime.now() - self._start_time).total_seconds(),
        }
        
        if self.context.conference_data:
            stats["speakers"] = len(self.context.conference_data.speakers)
            stats["attendees"] = len(self.context.conference_data.attendees)
            stats["companies"] = len(self.context.conference_data.companies)
            
        if self.context.icp_results:
            high_fit = sum(1 for r in self.context.icp_results if r.fit_level == "High")
            medium_fit = sum(1 for r in self.context.icp_results if r.fit_level == "Medium")
            low_fit = sum(1 for r in self.context.icp_results if r.fit_level == "Low")
            stats["icp_results"] = {
                "total": len(self.context.icp_results),
                "high_fit": high_fit,
                "medium_fit": medium_fit,
                "low_fit": low_fit,
            }
            
        return stats
