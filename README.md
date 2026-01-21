# Multi-Agent Conference Lead Collection System

An advanced multi-agent system powered by Google Gemini that autonomously scrapes conference websites, validates companies against ICP (Ideal Customer Profile) criteria, and generates prioritized lead lists. The system uses a sophisticated message-based architecture where specialized AI agents collaborate, challenge each other's decisions, and ensure high-quality lead scoring.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Agent Roles](#agent-roles)
- [Installation](#installation)
- [Configuration](#configuration)
- [Mistral AI Integration](#mistral-ai-integration)
- [Usage](#usage)
- [Output Format](#output-format)
- [Agent Communication](#agent-communication)
- [ICP Criteria](#icp-criteria)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Extending the System](#extending-the-system)
- [Use Cases](#use-cases)

## Features

- **Autonomous Multi-Agent System**: 5 specialized agents that communicate and collaborate autonomously
- **Agent Communication**: Message-based system with disputes, confirmations, and quality reviews
- **Gemini AI Integration**: Powered by Google Gemini for intelligent scoring and reasoning
- **Quality Assurance**: Agents can challenge and revise each other's decisions through disputes
- **Rich CLI Output**: Beautiful terminal output with progress tracking and detailed statistics
- **PDF Support**: Extract attendee lists from PDF files using Mistral AI OCR (for scanned documents) or pdfplumber (for text-based PDFs)
- **Web Scraping**: Intelligent scraping of conference websites for speakers, attendees, and sponsors
- **Prioritized Leads**: Companies scored and ranked by ICP fit (High/Medium/Low)
- **Extensible Architecture**: Easy to add new agents and extend functionality

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    OrchestratorAgent                        │
│                  (Gemini-powered brain)                     │
│              Coordinates pipeline & resolves conflicts       │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  Scraper    │ │  Enricher   │ │    ICP      │ │   Quality   │
│   Agent     │ │   Agent     │ │  Validator  │ │   Agent     │
│             │ │             │ │   Agent     │ │             │
│ • Web       │ │ • Industry  │ │ • Scoring   │ │ • Review    │
│   scraping  │ │ • Company   │ │ • ICP match │ │ • Disputes  │
│ • PDF OCR   │ │   size      │ │ • Reasoning │ │ • Validation│
│ • Extract   │ │ • Context   │ │             │ │             │
│   data      │ │             │ │             │ │             │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
         │              │              │              │
         └──────────────┴──────────────┴──────────────┘
                              │
                    ┌─────────────────┐
                    │   Message Bus   │
                    │ (Agent Comms)   │
                    │ • Request/Reply  │
                    │ • Disputes      │
                    │ • Confirmations │
                    └─────────────────┘
```

## Agent Roles

| Agent | Responsibility | Key Functions |
|-------|---------------|---------------|
| **OrchestratorAgent** | Pipeline coordinator | Coordinates workflow, resolves conflicts, manages agent lifecycle |
| **ScraperAgent** | Data extraction | Extracts speakers, attendees, companies from websites and PDFs |
| **EnricherAgent** | Data enrichment | Adds industry classification, company size, and contextual data |
| **ICPValidatorAgent** | ICP scoring | Scores companies against ICP criteria using AI reasoning |
| **QualityAgent** | Quality assurance | Reviews scores, raises disputes, validates final decisions |

## Installation

### Prerequisites

- Python 3.8 or higher
- Google Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))
- (Optional) Mistral AI API key for advanced PDF OCR ([Get one here](https://mistral.ai))

### Step-by-Step Setup

1. **Clone or navigate to the project**
   ```bash
   cd ascendo
   ```

2. **Create a virtual environment**
   ```bash
   # Windows
   python -m venv venv
   
   # Mac/Linux
   python3 -m venv venv
   ```

3. **Activate the virtual environment**
   ```bash
   # Windows PowerShell
   .\venv\Scripts\Activate.ps1
   
   # Windows CMD
   .\venv\Scripts\activate.bat
   
   # Mac/Linux
   source venv/bin/activate
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Set up environment variables**
   
   Create a `.env` file in the project root (or set environment variables):
   ```bash
   # .env file
   GEMINI_API_KEY=your-api-key-here
   MISTRAL_API_KEY=your-mistral-key-here  # Optional, for PDF OCR
   ```
   
   Or set them directly:
   ```bash
   # Windows PowerShell
   $env:GEMINI_API_KEY = "your-api-key-here"
   
   # Windows CMD
   set GEMINI_API_KEY=your-api-key-here
   
   # Mac/Linux
   export GEMINI_API_KEY="your-api-key-here"
   ```

## Configuration

Configuration is managed in `config.py`. Key settings:

- **ICP Criteria**: Target industries, titles, departments, company sizes
- **Scoring Weights**: How different factors contribute to the final score
- **Thresholds**: Score ranges for High/Medium/Low fit classifications
- **Scraper Settings**: Request delays, timeouts, retry logic
- **Gemini Settings**: Model selection, temperature, token limits

See `config.py` for detailed configuration options.

## Mistral AI Integration

The system integrates with Mistral AI for advanced PDF OCR (Optical Character Recognition) capabilities. This is particularly useful for processing scanned PDF documents or image-based attendee lists that cannot be parsed with standard text extraction methods.

### How Mistral OCR Works

1. **PDF Upload**: When you provide a PDF file with `--attendee-pdf`, the system uploads it to Mistral AI
2. **OCR Processing**: Mistral OCR extracts text and structure from the PDF, handling:
   - Scanned documents
   - Image-based PDFs
   - Complex table layouts
   - Multi-page documents
3. **Intelligent Extraction**: The extracted text is then processed by Gemini AI to intelligently identify and extract company names, attendee information, and team sizes
4. **Fallback**: If Mistral is unavailable, the system automatically falls back to `pdfplumber` for text-based PDFs

### Setting Up Mistral AI

1. **Get API Key**: Sign up at [Mistral AI](https://mistral.ai) and obtain an API key
2. **Set Environment Variable**:
   ```bash
   # Windows PowerShell
   $env:MISTRAL_API_KEY = "your-mistral-api-key"
   
   # Windows CMD
   set MISTRAL_API_KEY=your-mistral-api-key
   
   # Mac/Linux
   export MISTRAL_API_KEY="your-mistral-api-key"
   ```
   
   Or add to `.env` file:
   ```bash
   MISTRAL_API_KEY=your-mistral-api-key
   ```

### When to Use Mistral OCR

- **Scanned PDFs**: Documents that were scanned from paper
- **Image-based PDFs**: PDFs containing images of text rather than selectable text
- **Complex Layouts**: Tables with complex formatting that standard parsers struggle with
- **Low Quality Scans**: Documents with poor image quality that need advanced OCR

### Mistral vs pdfplumber

| Feature | Mistral OCR | pdfplumber |
|---------|------------|------------|
| Scanned PDFs | Yes | No |
| Image-based PDFs | Yes | No |
| Text-based PDFs | Yes | Yes |
| Complex Tables | Excellent | Good |
| Cost | API usage | Free |
| Speed | Slower (API call) | Faster (local) |

**Recommendation**: Use Mistral OCR for scanned or image-based PDFs. For text-based PDFs, pdfplumber is faster and free.

### Using Pre-Extracted OCR Text

If you've already extracted OCR text from a PDF (using Mistral or another tool), you can skip the OCR step and provide the text directly:

```bash
python main.py run --url "https://conference.com" --ocr-text ocr_output.txt
```

This is faster and avoids API costs if you've already processed the PDF elsewhere.

## Usage

### Basic Usage

Run the full pipeline on a conference website:

```bash
python main.py run --url "https://fieldserviceusa.wbresearch.com/speakers"
```

### Common Commands

```bash
# Basic run with default settings
python main.py run --url "https://example-conference.com/speakers"

# Verbose mode - see agent conversations
python main.py run --url "https://example-conference.com" --verbose

# Custom output file
python main.py run --url "https://example-conference.com" --output my_leads.csv

# Include PDF attendee list
python main.py run --url "https://example-conference.com" --attendee-pdf attendeelist.pdf

# Use pre-extracted OCR text (faster than PDF processing)
python main.py run --url "https://example-conference.com" --ocr-text ocr_output.txt

# Run with demo data (for testing without API calls)
python main.py run --demo --output demo_leads.csv

# Combine options
python main.py run --url "https://example-conference.com" \
                   --attendee-pdf attendeelist.pdf \
                   --verbose \
                   --output prioritized_leads.csv
```

### Example Output

```
╔═══════════════════════════════════════════════════════════════╗
║     Multi-Agent Conference Lead Collection System             ║
╚═══════════════════════════════════════════════════════════════╝

✓ Gemini API initialized

[OrchestratorAgent] Starting multi-agent pipeline
[ScraperAgent] Scraping conference: https://fieldserviceusa.wbresearch.com
[ScraperAgent] ✓ Found 47 speakers
[ScraperAgent] ✓ Found 23 company logos
[ScraperAgent] ✓ Loaded 156 attendees from PDF
[EnricherAgent] Enriching 65 companies...
[ICPValidatorAgent] Validating 65 companies against ICP...
[QualityAgent] Reviewing 65 ICP validations...
[QualityAgent] ✓ Raised 3 disputes, all resolved

┌──────────────────────────────────────────────────────────┐
│             ICP Validation Results Summary                │
├────────────┬───────┬─────────────────────────────────────┤
│ Fit Level  │ Count │ Top Companies                       │
├────────────┼───────┼─────────────────────────────────────┤
│ High       │    18 │ Schneider Electric, IBM, Bell+Howell│
│ Medium     │    15 │ Genpact, McKinstry, Tennant Co.     │
│ Low        │     9 │ 9 companies                         │
└────────────┴───────┴─────────────────────────────────────┘

✓ Results exported to: output/leads_20260120_143022.csv

Pipeline completed in 45.32 seconds
Total messages exchanged: 142
```

## Output Format

The system exports a CSV file with the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| `name` | Person name | "John Smith" |
| `title` | Job title | "VP of Field Service" |
| `company` | Company name | "Schneider Electric" |
| `type` | Source type | "Speaker", "Attendee", "Logo", or "PDF Attendee" |
| `industry` | Inferred/enriched industry | "Industrial Equipment" |
| `company_size` | Estimated employee count | "5000" |
| `icp_score` | 0-100 ICP score | "87" |
| `icp_fit` | Fit classification | "High", "Medium", or "Low" |
| `reasoning` | Explanation of score | "Strong industry match, VP title..." |

The CSV is sorted by ICP score (highest first), making it easy to prioritize outreach efforts.

## Agent Communication

The system uses a sophisticated message bus for agent-to-agent communication. With `--verbose` flag, you can see agents communicating:

```
┌─────────────────────────────────────────────────────────────┐
│ [ScraperAgent → ICPValidatorAgent] REQUEST                  │
│ Action: validate_company                                    │
│ Payload: {"company_name": "Schneider Electric", ...}        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ [ICPValidatorAgent → QualityAgent] REQUEST                  │
│ Action: review_score                                        │
│ Payload: {"score": 87, "fit_level": "High", ...}            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ [QualityAgent → ICPValidatorAgent] DISPUTE                  │
│ Action: dispute_score                                       │
│ Payload: {"reason": "Has SVP speaker, should be 92+", ...}  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ [ICPValidatorAgent → QualityAgent] CONFIRM                  │
│ Action: confirm_revision                                    │
│ Payload: {"new_score": 93, "reason": "Adjusted for SVP"}    │
└─────────────────────────────────────────────────────────────┘
```

### Message Types

- **REQUEST**: Agent requests action from another agent
- **RESPONSE**: Response to a request
- **DISPUTE**: Challenge a decision (e.g., score too low/high)
- **CONFIRM**: Confirm a revision or decision
- **ERROR**: Error notification
- **STATUS**: Status update

## ICP Criteria

The system validates companies against configurable ICP criteria (see `config.py`):

### Target Industries
Manufacturing, Industrial Equipment, Medical Devices, Healthcare Technology, Field Service, HVAC, Utilities, Telecommunications, Industrial Automation, Building Automation, Energy, Oil & Gas, Aerospace, Defense, and more.

### Target Titles
VP, Vice President, SVP, Senior Vice President, EVP, Executive Vice President, Director, Senior Director, Chief, C-Level, COO, CTO, CIO, Head of, General Manager, President.

### Target Departments
Field Service, Service, Customer Service, Customer Support, Technical Support, Operations, Service Operations, Aftermarket, Service Delivery, Digital, Technology, IT, Innovation.

### Scoring Factors
- **Industry Match** (30%): How well the company's industry aligns
- **Title Match** (25%): Relevance of contact titles
- **Department Match** (20%): Alignment with target departments
- **Company Size** (15%): Preference for 500+ employees
- **Speaker Bonus** (10%): Additional points for companies with speakers

### Fit Levels
- **High**: Score ≥ 75 - Priority targets for immediate outreach
- **Medium**: Score 50-74 - Secondary targets for follow-up
- **Low**: Score < 50 - Lower priority or out of scope

## Troubleshooting

### Common Issues

**Problem: "GEMINI_API_KEY not set"**
- **Solution**: Set the `GEMINI_API_KEY` environment variable or add it to a `.env` file
- The system will fall back to rule-based validation, but AI-powered scoring won't be available

**Problem: "No data scraped"**
- **Solution**: 
  - Check if the URL is accessible
  - Some websites may require JavaScript rendering (Selenium is used automatically)
  - Try using `--verbose` to see detailed scraping logs
  - Consider providing a PDF attendee list with `--attendee-pdf`

**Problem: "PDF parsing failed"**
- **Solution**:
  - For text-based PDFs: Ensure `pdfplumber` is installed: `pip install pdfplumber`
  - For scanned/image-based PDFs: Set `MISTRAL_API_KEY` for Mistral AI OCR support
  - Check that the PDF file is accessible and not corrupted
  - Try using `--ocr-text` with pre-extracted text instead
  - Verify your Mistral API key is valid and has sufficient quota

**Problem: "Rate limit exceeded"**
- **Solution**: 
  - The system includes automatic retries and delays
  - Adjust `SCRAPER_CONFIG["request_delay"]` in `config.py` to slow down requests
  - Check your Gemini API quota

**Problem: Import errors**
- **Solution**: 
  - Ensure virtual environment is activated
  - Reinstall dependencies: `pip install -r requirements.txt`
  - Check Python version: `python --version` (requires 3.8+)

### Debug Mode

Use `--verbose` flag to see:
- Detailed agent conversations
- Scraping progress and errors
- ICP scoring reasoning
- Quality review decisions

## Project Structure

```
ascendo/
├── agents/
│   ├── base_agent.py           # Abstract base class for all agents
│   ├── scraper_agent.py        # Web scraping and PDF parsing
│   ├── enricher_agent.py       # Data enrichment (industry, size)
│   ├── icp_validator_agent.py  # ICP scoring and validation
│   ├── quality_agent.py        # Quality review and disputes
│   └── orchestrator_agent.py   # Pipeline coordination
├── communication/
│   ├── message_bus.py          # Agent messaging system
│   └── context.py              # Shared state management
├── models/
│   └── schemas.py              # Pydantic data models
├── llm/
│   └── gemini_client.py        # Gemini API wrapper
├── main.py                     # CLI entry point
├── config.py                   # Configuration settings
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Extending the System

### Adding a New Agent

1. **Create agent file** in `agents/` directory
   ```python
   from agents.base_agent import BaseAgent
   
   class MyNewAgent(BaseAgent):
       def process(self, context):
           # Your logic here
           return context
       
       def handle_message(self, message):
           # Handle incoming messages
           pass
   ```

2. **Register with OrchestratorAgent** in `orchestrator_agent.py`
   ```python
   self.my_agent = MyNewAgent(self.message_bus, self.gemini_client)
   ```

3. **Add to pipeline** in `orchestrator.process()`

### Example Agent Ideas

- **`OutreachAgent`**: Generate personalized email drafts for high-fit leads
- **`LinkedInAgent`**: Find LinkedIn profiles for contacts
- **`CRMAgent`**: Push leads directly to Salesforce/HubSpot/CRM systems
- **`EmailAgent`**: Send automated outreach emails
- **`AnalyticsAgent`**: Track conversion rates and pipeline metrics
- **`DeduplicationAgent`**: Merge duplicate companies across conferences

### Customizing ICP Criteria

Edit `config.py` to adjust:
- Target industries, titles, departments
- Scoring weights
- Fit level thresholds
- Company size preferences

## Use Cases

### 1. Pre-Conference Lead Generation
Run the system before attending a conference to identify high-value targets and prioritize meetings.

```bash
python main.py run --url "https://upcoming-conference.com" --output pre_conference_leads.csv
```

### 2. Post-Conference Follow-Up
Process attendee lists from conferences you've attended to identify missed opportunities.

```bash
python main.py run --url "https://conference.com" \
                   --attendee-pdf conference_attendees.pdf \
                   --output follow_up_leads.csv
```

### 3. Multi-Conference Analysis
Run on multiple conferences to build a comprehensive lead database. The system handles deduplication automatically.

### 4. Market Intelligence
Understand which companies are active in your target market by analyzing conference participation patterns.

### 5. Sales Team Prioritization
Generate prioritized lists for sales teams, focusing on High-fit companies first.

---

Example agent ideas:
- `OutreachAgent`: Generate personalized email drafts
- `LinkedInAgent`: Find LinkedIn profiles for contacts
- `CRMAgent`: Push leads directly to Salesforce/HubSpot
