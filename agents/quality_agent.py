"""
Quality Agent

Responsible for reviewing and challenging ICP validation decisions.
Acts as a second opinion to ensure scoring accuracy.
"""
from typing import Optional

from agents.base_agent import BaseAgent
from models.schemas import AgentMessage, MessageType
from communication.message_bus import MessageBus
from communication.context import SharedContext
from llm.gemini_client import GeminiClient
from config import ICP_CRITERIA, ICP_THRESHOLDS


class QualityAgent(BaseAgent):
    """
    Agent that reviews ICP validation scores and disputes when necessary.
    
    Features:
    - Reviews high-value leads to prevent false negatives
    - Challenges scores that seem inconsistent
    - Provides second opinion using different reasoning
    """
    
    def __init__(self, message_bus: MessageBus, gemini_client: Optional[GeminiClient] = None):
        super().__init__("QualityAgent", message_bus)
        self.gemini = gemini_client
        self._reviews_completed: dict[str, dict] = {}
        
    def process(self, context: SharedContext) -> SharedContext:
        """Review all ICP results for quality."""
        if not context.icp_results:
            self.log_error("No ICP results to review")
            return context
            
        self.log(f"Reviewing {len(context.icp_results)} ICP validations...")
        
        disputes = 0
        confirmations = 0
        
        for result in context.icp_results:
            # Get company details for review
            company_info = context.get_company_details(result.company_name)
            
            # Review the score
            review = self._review_score(result, company_info)
            self._reviews_completed[result.company_name] = review
            
            if review["should_dispute"]:
                disputes += 1
                self.log_status(f"Disputing {result.company_name}: {review['reason']}")
                
                # Send dispute to validator
                self.send_message(
                    recipient="ICPValidatorAgent",
                    message_type=MessageType.DISPUTE,
                    action="dispute_score",
                    payload={
                        "company_name": result.company_name,
                        "reason": review["reason"],
                        "suggested_score": review.get("suggested_score"),
                    },
                )
            else:
                confirmations += 1
                
        self.log_success(f"Review complete: {confirmations} confirmed, {disputes} disputed")
        
        # Notify orchestrator
        self.send_message(
            recipient="OrchestratorAgent",
            message_type=MessageType.RESPONSE,
            action="quality_review_complete",
            payload={
                "total_reviewed": len(context.icp_results),
                "confirmed": confirmations,
                "disputed": disputes,
            }
        )
        
        return context
    
    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle incoming messages from other agents."""
        if message.action == "review_score":
            # Handle individual review request
            company_name = message.payload.get("company_name")
            result_data = message.payload.get("result", {})
            company_info = message.payload.get("company_info", {})
            
            # Create a minimal result object for review
            review = self._review_score_data(result_data, company_info)
            
            if review["should_dispute"]:
                return AgentMessage(
                    sender=self.name,
                    recipient=message.sender,
                    message_type=MessageType.DISPUTE,
                    action="dispute_score",
                    payload={
                        "company_name": company_name,
                        "reason": review["reason"],
                        "suggested_score": review.get("suggested_score"),
                    },
                    conversation_id=message.conversation_id,
                )
            else:
                return AgentMessage(
                    sender=self.name,
                    recipient=message.sender,
                    message_type=MessageType.CONFIRM,
                    action="score_confirmed",
                    payload={"company_name": company_name},
                    conversation_id=message.conversation_id,
                )
                
        elif message.action == "dispute_resolved":
            # Handle resolution response
            company_name = message.payload.get("company_name")
            accepted = message.payload.get("accepted", False)
            
            if company_name in self._reviews_completed:
                self._reviews_completed[company_name]["resolution"] = {
                    "accepted": accepted,
                    "original_score": message.payload.get("original_score"),
                    "revised_score": message.payload.get("revised_score"),
                }
                
            action = "accepted" if accepted else "rejected"
            self.log_status(f"Dispute for {company_name} was {action}")
            
        return None
    
    def _review_score(self, result, company_info: dict) -> dict:
        """Review a single ICP result."""
        return self._review_score_data(result.model_dump(), company_info)
    
    def _review_score_data(self, result_data: dict, company_info: dict) -> dict:
        """Review score data (dict format)."""
        company_name = result_data.get("company_name", "Unknown")
        score = result_data.get("score", 0)
        fit_level = result_data.get("fit_level", "Low")
        reasoning = result_data.get("reasoning", "")
        
        review = {
            "company_name": company_name,
            "original_score": score,
            "should_dispute": False,
            "reason": "",
            "suggested_score": None,
        }
        
        # Check for potential under-scoring
        speakers = company_info.get("speakers", [])
        
        # Rule 1: Companies with speakers should have higher scores
        if speakers and score < 60:
            review["should_dispute"] = True
            review["reason"] = f"Company has {len(speakers)} speaker(s) but score is only {score}"
            review["suggested_score"] = min(score + 15, 85)
            return review
        
        # Rule 2: Check for senior titles that might warrant higher scores
        senior_titles = ["SVP", "VP", "Chief", "Director", "President", "Head of"]
        has_senior_speaker = False
        for speaker in speakers:
            title = speaker.get("title", "")
            if any(st.lower() in title.lower() for st in senior_titles):
                has_senior_speaker = True
                break
        
        if has_senior_speaker and score < 70:
            review["should_dispute"] = True
            review["reason"] = f"Company has senior-level speaker but score is {score}"
            review["suggested_score"] = min(score + 20, 90)
            return review
        
        # Rule 3: Check for field service keywords in titles
        field_service_keywords = ["field service", "service", "aftermarket", "support"]
        has_fs_title = False
        for speaker in speakers:
            title = speaker.get("title", "")
            if any(kw in title.lower() for kw in field_service_keywords):
                has_fs_title = True
                break
        
        if has_fs_title and score < 75:
            review["should_dispute"] = True
            review["reason"] = f"Company has Field Service leadership but score is {score}"
            review["suggested_score"] = min(score + 15, 92)
            return review
        
        # Rule 4: Check for over-scoring without evidence
        if score >= 80 and not speakers and "Unknown" in reasoning:
            review["should_dispute"] = True
            review["reason"] = f"High score ({score}) with insufficient evidence"
            review["suggested_score"] = max(score - 15, 50)
            return review
        
        # Use Gemini for more nuanced review if available
        if self.gemini and score >= 50:
            try:
                gemini_review = self._gemini_review(result_data, company_info)
                if gemini_review.get("should_dispute"):
                    return gemini_review
            except Exception:
                pass  # Fall back to rule-based review
        
        return review
    
    def _gemini_review(self, result_data: dict, company_info: dict) -> dict:
        """Use Gemini to review the score."""
        import json
        
        prompt = f"""Review this ICP validation score for quality and consistency.

VALIDATION RESULT:
{json.dumps(result_data, indent=2)}

COMPANY INFORMATION:
{json.dumps(company_info, indent=2)}

ICP CRITERIA (for reference):
- Target Industries: Manufacturing, Industrial Equipment, Medical Devices, Field Service
- Target Titles: VP, SVP, Director, C-Level
- Target Departments: Field Service, Service, Operations, Support

Review the score and determine if it should be disputed:
{{
    "should_dispute": <true/false>,
    "reason": "<explanation if disputing>",
    "suggested_score": <new score if disputing, or null>,
    "confidence": "<High|Medium|Low>"
}}

Dispute only if the score seems significantly off (by 15+ points)."""

        response = self.gemini.generate_json(prompt)
        
        return {
            "company_name": result_data.get("company_name"),
            "original_score": result_data.get("score"),
            "should_dispute": response.get("should_dispute", False),
            "reason": response.get("reason", ""),
            "suggested_score": response.get("suggested_score"),
        }
