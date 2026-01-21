"""
ICP Validator Agent

Responsible for validating companies against the Ideal Customer Profile (ICP).
Uses Gemini to analyze company fit and generate scores.
"""
from typing import Optional

from agents.base_agent import BaseAgent
from models.schemas import AgentMessage, MessageType, ICPResult
from communication.message_bus import MessageBus
from communication.context import SharedContext
from llm.gemini_client import GeminiClient
from config import ICP_CRITERIA, ICP_THRESHOLDS


class ICPValidatorAgent(BaseAgent):
    """
    Agent that validates companies against ICP criteria.
    
    Features:
    - Gemini-powered scoring with detailed reasoning
    - Component-based scoring (industry, title, size, etc.)
    - Can accept disputes from QualityAgent and revise scores
    """
    
    def __init__(self, message_bus: MessageBus, gemini_client: Optional[GeminiClient] = None):
        super().__init__("ICPValidatorAgent", message_bus)
        self.gemini = gemini_client
        self.icp_criteria = ICP_CRITERIA
        self.thresholds = ICP_THRESHOLDS
        self._pending_validations: dict[str, ICPResult] = {}
        
    def process(self, context: SharedContext) -> SharedContext:
        """Validate all companies against ICP criteria."""
        if not context.conference_data:
            self.log_error("No conference data to validate")
            return context
            
        companies = context.get_companies()
        self.log(f"Validating {len(companies)} companies against ICP...")
        
        for i, company_name in enumerate(companies):
            self.log_status(f"Validating {i+1}/{len(companies)}: {company_name}")
            
            # Get full company details
            company_info = context.get_company_details(company_name)
            
            # Request enrichment data if needed
            self.send_message(
                recipient="EnricherAgent",
                message_type=MessageType.REQUEST,
                action="enrich_company",
                payload={"company_name": company_name, "known_info": company_info},
            )
            
            # Validate against ICP
            result = self._validate_company(company_name, company_info)
            
            # Store for potential disputes
            self._pending_validations[company_name] = result
            
            # Request quality review for high/medium fits
            if result.score >= self.thresholds["medium"]:
                self.send_message(
                    recipient="QualityAgent",
                    message_type=MessageType.REQUEST,
                    action="review_score",
                    payload={
                        "company_name": company_name,
                        "result": result.model_dump(),
                        "company_info": company_info,
                    },
                )
            
            # Add to context
            context.add_icp_result(result)
        
        self.log_success(f"Validated {len(companies)} companies")
        
        # Summary
        high_fit = sum(1 for r in context.icp_results if r.fit_level == "High")
        medium_fit = sum(1 for r in context.icp_results if r.fit_level == "Medium")
        low_fit = sum(1 for r in context.icp_results if r.fit_level == "Low")
        self.log(f"Results: {high_fit} High, {medium_fit} Medium, {low_fit} Low fit")
        
        # Notify orchestrator
        self.send_message(
            recipient="OrchestratorAgent",
            message_type=MessageType.RESPONSE,
            action="validation_complete",
            payload={
                "total": len(companies),
                "high_fit": high_fit,
                "medium_fit": medium_fit,
                "low_fit": low_fit,
            }
        )
        
        return context
    
    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle incoming messages from other agents."""
        if message.action == "validate_company":
            # Handle single company validation request
            company_name = message.payload.get("company_name")
            company_info = message.payload.get("company_info", {})
            
            if company_name:
                result = self._validate_company(company_name, company_info)
                return AgentMessage(
                    sender=self.name,
                    recipient=message.sender,
                    message_type=MessageType.RESPONSE,
                    action="validation_result",
                    payload={"result": result.model_dump()},
                    conversation_id=message.conversation_id,
                )
                
        elif message.action == "dispute_score":
            # Handle dispute from QualityAgent
            company_name = message.payload.get("company_name")
            dispute_reason = message.payload.get("reason")
            suggested_score = message.payload.get("suggested_score")
            
            self.log_status(f"Received dispute for {company_name}: {dispute_reason}")
            
            # Consider the dispute
            if company_name in self._pending_validations:
                original = self._pending_validations[company_name]
                revised = self._handle_dispute(original, dispute_reason, suggested_score)
                
                return AgentMessage(
                    sender=self.name,
                    recipient=message.sender,
                    message_type=MessageType.RESPONSE,
                    action="dispute_resolved",
                    payload={
                        "company_name": company_name,
                        "original_score": original.score,
                        "revised_score": revised.score,
                        "accepted": revised.score != original.score,
                    },
                    conversation_id=message.conversation_id,
                )
                
        elif message.action == "company_enriched":
            # Handle enrichment data from EnricherAgent
            company_name = message.payload.get("company_name")
            enrichment = message.payload.get("data", {})
            
            # Update pending validation if exists
            if company_name in self._pending_validations:
                self._update_with_enrichment(company_name, enrichment)
                
        return None
    
    def _validate_company(self, company_name: str, company_info: dict) -> ICPResult:
        """Validate a single company against ICP criteria."""
        try:
            if self.gemini:
                # Use Gemini for intelligent validation
                result = self.gemini.validate_icp(company_info, self.icp_criteria)
                
                return ICPResult(
                    company_name=company_name,
                    score=result.get("score", 50),
                    fit_level=result.get("fit_level", "Medium"),
                    reasoning=result.get("reasoning", ""),
                    industry_score=result.get("industry_score", 0),
                    title_score=result.get("title_score", 0),
                    department_score=result.get("department_score", 0),
                    size_score=result.get("size_score", 0),
                    speaker_bonus=result.get("speaker_bonus", 0),
                    validated_by=self.name,
                )
        except Exception as e:
            self.log_status(f"Gemini validation failed for {company_name}: {e}")
        
        # Fallback: rule-based validation
        return self._rule_based_validation(company_name, company_info)
    
    def _rule_based_validation(self, company_name: str, company_info: dict) -> ICPResult:
        """Fallback rule-based validation without Gemini."""
        score = 0
        reasoning_parts = []
        
        weights = self.icp_criteria["score_weights"]
        
        # Industry score
        industry = company_info.get("industry", "").lower()
        industry_score = 0
        for target_industry in self.icp_criteria["target_industries"]:
            if target_industry.lower() in industry or industry in target_industry.lower():
                industry_score = weights["industry_match"]
                reasoning_parts.append(f"Industry match: {target_industry}")
                break
        
        # Title score - check speakers and attendees
        title_score = 0
        speakers = company_info.get("speakers", [])
        for speaker in speakers:
            title = speaker.get("title", "")
            for target_title in self.icp_criteria["target_titles"]:
                if target_title.lower() in title.lower():
                    title_score = weights["title_match"]
                    reasoning_parts.append(f"Title match: {title}")
                    break
            if title_score > 0:
                break
        
        # Department score
        department_score = 0
        for speaker in speakers:
            title = speaker.get("title", "")
            for dept in self.icp_criteria["target_departments"]:
                if dept.lower() in title.lower():
                    department_score = weights["department_match"]
                    reasoning_parts.append(f"Department match: {dept}")
                    break
            if department_score > 0:
                break
        
        # Size score (if available)
        size_score = 0
        company_size = company_info.get("size") or company_info.get("employee_count")
        if company_size:
            if company_size >= self.icp_criteria["preferred_company_size"]:
                size_score = weights["company_size"]
                reasoning_parts.append(f"Enterprise size: {company_size}+ employees")
            elif company_size >= self.icp_criteria["min_company_size"]:
                size_score = weights["company_size"] // 2
                reasoning_parts.append(f"Mid-market size: {company_size} employees")
        
        # Speaker bonus
        speaker_bonus = 0
        if speakers:
            speaker_bonus = weights["speaker_bonus"]
            reasoning_parts.append(f"Has {len(speakers)} speaker(s) at conference")
        
        # Calculate total score
        score = industry_score + title_score + department_score + size_score + speaker_bonus
        
        # Determine fit level
        if score >= self.thresholds["high"]:
            fit_level = "High"
        elif score >= self.thresholds["medium"]:
            fit_level = "Medium"
        else:
            fit_level = "Low"
        
        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Insufficient data for scoring"
        
        return ICPResult(
            company_name=company_name,
            score=score,
            fit_level=fit_level,
            reasoning=reasoning,
            industry_score=industry_score,
            title_score=title_score,
            department_score=department_score,
            size_score=size_score,
            speaker_bonus=speaker_bonus,
            validated_by=self.name,
        )
    
    def _handle_dispute(self, 
                        original: ICPResult, 
                        dispute_reason: str,
                        suggested_score: Optional[int]) -> ICPResult:
        """Handle a dispute from QualityAgent."""
        # Create a copy of the original result
        revised = ICPResult(
            company_name=original.company_name,
            score=original.score,
            fit_level=original.fit_level,
            reasoning=original.reasoning,
            industry_score=original.industry_score,
            title_score=original.title_score,
            department_score=original.department_score,
            size_score=original.size_score,
            speaker_bonus=original.speaker_bonus,
            validated_by=original.validated_by,
            disputed=True,
            dispute_reason=dispute_reason,
        )
        
        # If Gemini available, use it to resolve dispute
        if self.gemini:
            try:
                resolution = self.gemini.resolve_dispute(
                    original_score=original.model_dump(),
                    dispute={"reason": dispute_reason, "suggested_score": suggested_score},
                    company_info={"name": original.company_name},
                )
                
                revised.final_score = resolution.get("final_score", original.score)
                revised.score = revised.final_score
                revised.fit_level = resolution.get("final_fit_level", original.fit_level)
                revised.reasoning = f"{original.reasoning} | Dispute resolved: {resolution.get('explanation', '')}"
                
            except Exception as e:
                self.log_status(f"Dispute resolution failed: {e}")
                # Fallback: accept suggested score if reasonable
                if suggested_score and abs(suggested_score - original.score) <= 20:
                    revised.score = suggested_score
                    revised.final_score = suggested_score
        else:
            # Without Gemini, accept if within reasonable range
            if suggested_score and abs(suggested_score - original.score) <= 20:
                revised.score = suggested_score
                revised.final_score = suggested_score
        
        # Update fit level based on new score
        if revised.score >= self.thresholds["high"]:
            revised.fit_level = "High"
        elif revised.score >= self.thresholds["medium"]:
            revised.fit_level = "Medium"
        else:
            revised.fit_level = "Low"
        
        # Update in pending validations
        self._pending_validations[original.company_name] = revised
        
        return revised
    
    def _update_with_enrichment(self, company_name: str, enrichment: dict):
        """Update a pending validation with enrichment data."""
        if company_name not in self._pending_validations:
            return
            
        result = self._pending_validations[company_name]
        
        # Check if enrichment affects the score
        industry = enrichment.get("industry", "")
        if industry and result.industry_score == 0:
            for target in self.icp_criteria["target_industries"]:
                if target.lower() in industry.lower():
                    result.industry_score = self.icp_criteria["score_weights"]["industry_match"]
                    result.score += result.industry_score
                    result.reasoning += f"; Industry confirmed: {industry}"
                    break
        
        # Update fit level if score changed
        if result.score >= self.thresholds["high"]:
            result.fit_level = "High"
        elif result.score >= self.thresholds["medium"]:
            result.fit_level = "Medium"
