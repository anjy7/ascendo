"""
Google Gemini API Client

Wrapper for the Gemini API with retry logic, prompt templates,
and structured output parsing.
"""
import json
import time
from typing import Any, Optional

from rich.console import Console

from config import GEMINI_API_KEY, GEMINI_CONFIG

console = Console()


class GeminiClient:
    """
    Client for interacting with Google Gemini API.
    
    Features:
    - Automatic retry with exponential backoff
    - Structured JSON output parsing
    - Prompt templates for common tasks
    - Token usage tracking
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        if not self.api_key:
            raise ValueError(
                "Gemini API key not found. Set GEMINI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        # Use the new google-genai package
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            self.model_name = GEMINI_CONFIG["model"]
            self._use_new_sdk = True
        except ImportError:
            # Fallback to old SDK if new one not available
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(GEMINI_CONFIG["model"])
                self._use_new_sdk = False
            except ImportError:
                raise ImportError("Neither google-genai nor google-generativeai is installed")
        
        self._total_tokens = 0
        
    def generate(self, 
                 prompt: str, 
                 system_instruction: Optional[str] = None,
                 max_retries: int = 3) -> str:
        """
        Generate text using Gemini.
        
        Args:
            prompt: The user prompt
            system_instruction: Optional system instruction
            max_retries: Number of retries on failure
            
        Returns:
            Generated text response
        """
        for attempt in range(max_retries):
            try:
                if self._use_new_sdk:
                    # New SDK approach
                    full_prompt = prompt
                    if system_instruction:
                        full_prompt = f"{system_instruction}\n\n{prompt}"
                    
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=full_prompt,
                    )
                    return response.text
                else:
                    # Old SDK approach
                    import google.generativeai as genai
                    if system_instruction:
                        model = genai.GenerativeModel(
                            GEMINI_CONFIG["model"],
                            system_instruction=system_instruction
                        )
                    else:
                        model = self.model
                    
                    response = model.generate_content(prompt)
                    return response.text
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    console.print(f"[yellow]Gemini API error, retrying in {wait_time}s: {e}[/yellow]")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"Gemini API failed after {max_retries} attempts: {e}")
    
    def generate_json(self, 
                      prompt: str,
                      system_instruction: Optional[str] = None,
                      max_retries: int = 3) -> dict[str, Any]:
        """
        Generate JSON output using Gemini.
        
        Args:
            prompt: The user prompt (should ask for JSON output)
            system_instruction: Optional system instruction
            max_retries: Number of retries on failure
            
        Returns:
            Parsed JSON as dictionary
        """
        # Add JSON instruction to prompt
        json_prompt = f"""{prompt}

IMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation, just the JSON object."""

        response = self.generate(json_prompt, system_instruction, max_retries)
        
        # Clean up response - remove markdown code blocks if present
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse Gemini response as JSON: {e}\nResponse: {response[:500]}")
    
    def validate_icp(self, company_info: dict[str, Any], icp_criteria: dict) -> dict:
        """
        Validate a company against ICP criteria.
        
        Args:
            company_info: Information about the company
            icp_criteria: The ICP criteria to validate against
            
        Returns:
            Dictionary with score, fit_level, and reasoning
        """
        prompt = f"""Analyze this company for Ideal Customer Profile (ICP) fit.

COMPANY INFORMATION:
{json.dumps(company_info, indent=2)}

ICP CRITERIA:
- Target Industries: {', '.join(icp_criteria.get('target_industries', []))}
- Target Titles: {', '.join(icp_criteria.get('target_titles', []))}
- Target Departments: {', '.join(icp_criteria.get('target_departments', []))}
- Minimum Company Size: {icp_criteria.get('min_company_size', 'Not specified')} employees
- Target Geography: {', '.join(icp_criteria.get('target_geography', []))}

SCORING WEIGHTS:
- Industry Match: {icp_criteria.get('score_weights', {}).get('industry_match', 30)}%
- Title Match: {icp_criteria.get('score_weights', {}).get('title_match', 25)}%
- Department Match: {icp_criteria.get('score_weights', {}).get('department_match', 20)}%
- Company Size: {icp_criteria.get('score_weights', {}).get('company_size', 15)}%
- Speaker Bonus: {icp_criteria.get('score_weights', {}).get('speaker_bonus', 10)}%

Analyze the company and provide a JSON response with:
{{
    "score": <0-100>,
    "fit_level": "<High|Medium|Low>",
    "industry_score": <0-30>,
    "title_score": <0-25>,
    "department_score": <0-20>,
    "size_score": <0-15>,
    "speaker_bonus": <0-10>,
    "inferred_industry": "<best guess of industry>",
    "reasoning": "<2-3 sentence explanation>"
}}

Use High for score >= 75, Medium for score >= 50, Low for score < 50."""

        system_instruction = """You are an expert B2B sales analyst specializing in 
Ideal Customer Profile (ICP) validation for a field service AI/automation company. 
Be objective and thorough in your analysis. If information is missing, make reasonable 
inferences based on company name, job titles, and industry context."""

        return self.generate_json(prompt, system_instruction)
    
    def orchestrate_agents(self, 
                           context_summary: str, 
                           recent_messages: list[dict],
                           available_agents: list[str]) -> dict:
        """
        Use Gemini to decide the next action in the agent pipeline.
        
        Args:
            context_summary: Summary of current pipeline state
            recent_messages: Recent agent messages
            available_agents: List of available agent names
            
        Returns:
            Decision dictionary with next_agent and action
        """
        prompt = f"""You are orchestrating a multi-agent system for conference lead collection.

CURRENT STATE:
{context_summary}

RECENT AGENT MESSAGES:
{json.dumps(recent_messages, indent=2)}

AVAILABLE AGENTS:
{', '.join(available_agents)}

Decide the next action. Respond with JSON:
{{
    "next_agent": "<agent name or 'COMPLETE' if done>",
    "action": "<specific action for the agent>",
    "reasoning": "<why this is the right next step>",
    "parallel_actions": [<list of actions that can run in parallel, if any>]
}}"""

        system_instruction = """You are a workflow orchestrator. Make efficient decisions 
about which agent should act next. Prefer parallel execution when possible. 
Complete the pipeline when all companies are validated."""

        return self.generate_json(prompt, system_instruction)
    
    def resolve_dispute(self,
                        original_score: dict,
                        dispute: dict,
                        company_info: dict) -> dict:
        """
        Resolve a dispute between agents about an ICP score.
        
        Args:
            original_score: The original ICP validation result
            dispute: The dispute raised by QualityAgent
            company_info: Full company information
            
        Returns:
            Resolution with final_score and explanation
        """
        prompt = f"""You are resolving a dispute between agents about an ICP score.

ORIGINAL VALIDATION:
{json.dumps(original_score, indent=2)}

DISPUTE RAISED:
{json.dumps(dispute, indent=2)}

COMPANY INFORMATION:
{json.dumps(company_info, indent=2)}

Analyze both perspectives and provide a final decision:
{{
    "resolution": "<ACCEPT_ORIGINAL|ACCEPT_DISPUTE|COMPROMISE>",
    "final_score": <0-100>,
    "final_fit_level": "<High|Medium|Low>",
    "explanation": "<explanation of the decision>",
    "adjustments": "<what was changed and why>"
}}"""

        system_instruction = """You are a senior analyst resolving scoring disputes. 
Be fair and consider all evidence. Prioritize accuracy over consistency."""

        return self.generate_json(prompt, system_instruction)
    
    def enrich_company(self, company_name: str, known_info: dict) -> dict:
        """
        Use Gemini to infer additional company information.
        
        Args:
            company_name: Name of the company
            known_info: Already known information
            
        Returns:
            Enriched company information
        """
        prompt = f"""Based on your knowledge, provide information about this company:

COMPANY NAME: {company_name}

KNOWN INFORMATION:
{json.dumps(known_info, indent=2)}

Provide your best knowledge about this company:
{{
    "industry": "<primary industry>",
    "size_estimate": "<Small (<500)|Mid-market (500-5000)|Enterprise (5000+)>",
    "employee_count_estimate": <number or null>,
    "headquarters": "<city, country or 'Unknown'>",
    "description": "<1-2 sentence description>",
    "field_service_relevance": "<why they might need field service solutions>",
    "confidence": "<High|Medium|Low>"
}}

If you don't know, say 'Unknown' rather than guessing."""

        system_instruction = """You are a business intelligence analyst. 
Provide accurate information based on your training data. 
Be honest about uncertainty."""

        return self.generate_json(prompt, system_instruction)
