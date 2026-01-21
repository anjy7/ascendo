"""
Enricher Agent

Responsible for fetching additional company information:
- Industry classification
- Company size estimates
- Headquarters location
- Business description
"""
from typing import Optional

from agents.base_agent import BaseAgent
from models.schemas import AgentMessage, MessageType, Company
from communication.message_bus import MessageBus
from communication.context import SharedContext
from llm.gemini_client import GeminiClient


class EnricherAgent(BaseAgent):
    """
    Agent that enriches company data with additional information.
    
    Uses Gemini to infer company details when external APIs are not available.
    Can be extended to use Clearbit, LinkedIn, or other data providers.
    """
    
    def __init__(self, message_bus: MessageBus, gemini_client: Optional[GeminiClient] = None):
        super().__init__("EnricherAgent", message_bus)
        self.gemini = gemini_client
        self._cache: dict[str, dict] = {}  # Cache enrichment results
        
    def process(self, context: SharedContext) -> SharedContext:
        """Enrich all companies in the context."""
        if not context.conference_data:
            self.log_error("No conference data to enrich")
            return context
            
        companies = context.conference_data.companies
        self.log(f"Enriching {len(companies)} companies...")
        
        for i, company in enumerate(companies):
            self.log_status(f"Enriching {i+1}/{len(companies)}: {company.name}")
            
            # Get known info about this company
            known_info = context.get_company_details(company.name)
            
            # Enrich with Gemini
            enriched = self._enrich_company(company.name, known_info)
            
            if enriched:
                company.industry = enriched.get("industry", company.industry)
                company.size_category = enriched.get("size_estimate", "")
                company.description = enriched.get("description", "")
                
                # Parse employee count estimate
                emp_estimate = enriched.get("employee_count_estimate")
                if emp_estimate and isinstance(emp_estimate, int):
                    company.size = emp_estimate
                    
        self.log_success(f"Enriched {len(companies)} companies")
        
        # Notify orchestrator
        self.send_message(
            recipient="OrchestratorAgent",
            message_type=MessageType.RESPONSE,
            action="enrichment_complete",
            payload={"companies_enriched": len(companies)}
        )
        
        return context
    
    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle incoming messages from other agents."""
        if message.action == "enrich_company":
            company_name = message.payload.get("company_name")
            known_info = message.payload.get("known_info", {})
            
            if company_name:
                enriched = self._enrich_company(company_name, known_info)
                return AgentMessage(
                    sender=self.name,
                    recipient=message.sender,
                    message_type=MessageType.RESPONSE,
                    action="company_enriched",
                    payload={"company_name": company_name, "data": enriched},
                    conversation_id=message.conversation_id,
                )
                
        elif message.action == "get_industry":
            company_name = message.payload.get("company_name")
            if company_name in self._cache:
                industry = self._cache[company_name].get("industry", "Unknown")
            else:
                industry = self._infer_industry(company_name)
                
            return AgentMessage(
                sender=self.name,
                recipient=message.sender,
                message_type=MessageType.RESPONSE,
                action="industry_response",
                payload={"company_name": company_name, "industry": industry},
                conversation_id=message.conversation_id,
            )
            
        return None
    
    def _enrich_company(self, company_name: str, known_info: dict) -> dict:
        """Enrich a single company with additional data."""
        # Check cache first
        if company_name in self._cache:
            return self._cache[company_name]
        
        try:
            if self.gemini:
                enriched = self.gemini.enrich_company(company_name, known_info)
                self._cache[company_name] = enriched
                return enriched
        except Exception as e:
            self.log_status(f"Gemini enrichment failed for {company_name}: {e}")
        
        # Fallback: basic inference from known info
        return self._basic_enrichment(company_name, known_info)
    
    def _basic_enrichment(self, company_name: str, known_info: dict) -> dict:
        """Basic enrichment without Gemini."""
        result = {
            "industry": "Unknown",
            "size_estimate": "Unknown",
            "employee_count_estimate": None,
            "headquarters": "Unknown",
            "description": "",
            "confidence": "Low",
        }
        
        # Infer industry from company name or speaker titles
        name_lower = company_name.lower()
        
        industry_keywords = {
            "Manufacturing": ["manufacturing", "industrial", "equipment", "machinery"],
            "Healthcare/Medical": ["medical", "health", "pharma", "biotech", "hospital"],
            "Technology": ["tech", "software", "digital", "data", "cloud"],
            "Energy/Utilities": ["energy", "power", "utility", "electric", "gas", "oil"],
            "Telecommunications": ["telecom", "wireless", "network", "communications"],
            "Transportation": ["logistics", "transport", "shipping", "freight"],
            "Building/Construction": ["construction", "building", "hvac", "elevator"],
        }
        
        for industry, keywords in industry_keywords.items():
            if any(kw in name_lower for kw in keywords):
                result["industry"] = industry
                break
        
        # Infer from speaker/attendee titles if available
        speakers = known_info.get("speakers", [])
        for speaker in speakers:
            title = speaker.get("title", "").lower()
            if "field service" in title or "service" in title:
                result["field_service_relevance"] = "Has Field Service leadership"
                break
        
        return result
    
    def _infer_industry(self, company_name: str) -> str:
        """Quick industry inference for a company name."""
        if company_name in self._cache:
            return self._cache[company_name].get("industry", "Unknown")
            
        # Simple keyword matching
        name_lower = company_name.lower()
        
        if any(x in name_lower for x in ["medical", "health", "pharma"]):
            return "Healthcare/Medical"
        if any(x in name_lower for x in ["tech", "software", "digital"]):
            return "Technology"
        if any(x in name_lower for x in ["energy", "power", "electric"]):
            return "Energy/Utilities"
        if any(x in name_lower for x in ["manufacturing", "industrial"]):
            return "Manufacturing"
            
        return "Unknown"
