"""
Configuration for the Multi-Agent Conference Lead System
"""
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# API KEYS
# =============================================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

# =============================================================================
# ICP (IDEAL CUSTOMER PROFILE) CRITERIA
# Adjust these based on Ascendo's actual target market
# =============================================================================
ICP_CRITERIA = {
    "target_industries": [
        "Manufacturing",
        "Industrial Equipment",
        "Medical Devices",
        "Healthcare Technology",
        "Field Service",
        "HVAC",
        "Utilities",
        "Telecommunications",
        "Industrial Automation",
        "Building Automation",
        "Elevator/Escalator",
        "Energy",
        "Oil & Gas",
        "Aerospace",
        "Defense",
    ],
    "target_titles": [
        "VP",
        "Vice President",
        "SVP",
        "Senior Vice President",
        "EVP",
        "Executive Vice President",
        "Director",
        "Senior Director",
        "Chief",
        "C-Level",
        "COO",
        "CTO",
        "CIO",
        "Head of",
        "General Manager",
        "President",
    ],
    "target_departments": [
        "Field Service",
        "Service",
        "Customer Service",
        "Customer Support",
        "Technical Support",
        "Operations",
        "Service Operations",
        "Aftermarket",
        "Service Delivery",
        "Digital",
        "Technology",
        "IT",
        "Innovation",
    ],
    "min_company_size": 500,  # employees
    "preferred_company_size": 1000,  # employees
    "target_geography": ["North America", "USA", "United States", "Canada"],
    "score_weights": {
        "industry_match": 30,
        "title_match": 25,
        "department_match": 20,
        "company_size": 15,
        "speaker_bonus": 10,
    },
}

# =============================================================================
# SCORING THRESHOLDS
# =============================================================================
ICP_THRESHOLDS = {
    "high": 75,    # Score >= 75 = High fit
    "medium": 50,  # Score >= 50 = Medium fit
    "low": 0,      # Score < 50 = Low fit
}

# =============================================================================
# SCRAPER SETTINGS
# =============================================================================
SCRAPER_CONFIG = {
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "request_delay": 2,  # seconds between requests
    "timeout": 30,  # request timeout in seconds
    "max_retries": 3,
}

# =============================================================================
# GEMINI SETTINGS
# =============================================================================
GEMINI_CONFIG = {
    "model": "gemini-3-flash-preview",
    "temperature": 0.3,
    "max_output_tokens": 2048,
}

# =============================================================================
# OUTPUT SETTINGS
# =============================================================================
OUTPUT_CONFIG = {
    "default_output_dir": "output",
    "csv_columns": [
        "name",
        "title",
        "company",
        "type",
        "industry",
        "company_size",
        "icp_score",
        "icp_fit",
        "reasoning",
    ],
}
