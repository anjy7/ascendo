"""
Scraper Agent

Responsible for crawling conference websites and extracting:
- Speaker information (name, title, company)
- Attendee lists (from web or PDF)
- Company logos/sponsors
"""
import os
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from rich.progress import Progress, SpinnerColumn, TextColumn

from agents.base_agent import BaseAgent
from models.schemas import (
    AgentMessage, 
    MessageType, 
    Speaker, 
    Attendee, 
    Company,
    ConferenceData,
)
from communication.message_bus import MessageBus
from communication.context import SharedContext
from config import SCRAPER_CONFIG

# PDF parsing with Mistral OCR
try:
    from mistralai import Mistral
    MISTRAL_OCR_SUPPORT = True
except ImportError:
    MISTRAL_OCR_SUPPORT = False

# Fallback PDF parsing
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False


class ScraperAgent(BaseAgent):
    """
    Agent that scrapes conference websites for lead data.
    
    Capabilities:
    - Extract speakers from /speakers pages
    - Extract attendees from /attendees pages  
    - Extract company logos from sponsor sections
    - Handle dynamic content with fallback strategies
    """
    
    def __init__(self, message_bus: MessageBus):
        super().__init__("ScraperAgent", message_bus)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": SCRAPER_CONFIG["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        
    def process(self, context: SharedContext) -> SharedContext:
        """Scrape conference website and extract data."""
        url = context.url
        self.log(f"Scraping conference: {url}")
        
        # Initialize conference data
        conference_data = ConferenceData(url=url)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.message_bus._subscribers and None,  # Suppress if verbose
        ) as progress:
            # Try to get main page first
            task = progress.add_task("Fetching main page...", total=None)
            main_html = self._fetch_page(url)
            
            if main_html:
                conference_data.conference_name = self._extract_conference_name(main_html, url)
                progress.update(task, description=f"Found: {conference_data.conference_name}")
            
            # Scrape speakers page
            progress.update(task, description="Scraping speakers...")
            speakers = self._scrape_speakers(url)
            conference_data.speakers = speakers
            self.log(f"Found {len(speakers)} speakers")
            
            # Scrape attendees page
            progress.update(task, description="Scraping attendees...")
            attendees = self._scrape_attendees(url)
            conference_data.attendees = attendees
            self.log(f"Found {len(attendees)} attendees")
            
            # Extract companies from all sources
            progress.update(task, description="Extracting companies...")
            companies = self._extract_companies(speakers, attendees, main_html)
            conference_data.companies = companies
            self.log(f"Found {len(companies)} unique companies")
        
        context.conference_data = conference_data
        
        # Notify other agents
        self.send_message(
            recipient="OrchestratorAgent",
            message_type=MessageType.RESPONSE,
            action="scrape_complete",
            payload={
                "speakers_count": len(speakers),
                "attendees_count": len(attendees),
                "companies_count": len(companies),
            }
        )
        
        return context
    
    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle incoming messages from other agents."""
        if message.action == "scrape_page":
            # Handle request to scrape a specific page
            url = message.payload.get("url")
            if url:
                html = self._fetch_page(url)
                return AgentMessage(
                    sender=self.name,
                    recipient=message.sender,
                    message_type=MessageType.RESPONSE,
                    action="page_content",
                    payload={"html": html[:5000] if html else None},
                    conversation_id=message.conversation_id,
                )
        return None
    
    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page with retry logic."""
        for attempt in range(SCRAPER_CONFIG["max_retries"]):
            try:
                response = self.session.get(
                    url, 
                    timeout=SCRAPER_CONFIG["timeout"]
                )
                if response.status_code == 200:
                    return response.text
                elif response.status_code == 403:
                    self.log_status(f"Access forbidden (403) for {url}")
                    return None
                else:
                    self.log_status(f"Got status {response.status_code} for {url}")
                    
            except requests.RequestException as e:
                self.log_status(f"Request failed: {e}")
                
            if attempt < SCRAPER_CONFIG["max_retries"] - 1:
                time.sleep(SCRAPER_CONFIG["request_delay"])
                
        return None
    
    def _extract_conference_name(self, html: str, url: str) -> str:
        """Extract conference name from page."""
        soup = BeautifulSoup(html, "lxml")
        
        # Try various selectors
        selectors = [
            "h1",
            ".conference-title",
            ".event-title",
            "title",
            'meta[property="og:title"]',
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                if selector.startswith("meta"):
                    return element.get("content", "")
                text = element.get_text(strip=True)
                if text and len(text) < 200:
                    return text
        
        # Fallback: extract from URL
        parsed = urlparse(url)
        return parsed.netloc.split(".")[0].replace("-", " ").title()
    
    def _scrape_speakers(self, base_url: str) -> list[Speaker]:
        """Scrape speaker information from the speakers page."""
        speakers = []
        
        # Try common speaker page URLs
        speaker_paths = [
            "/speakers",
            "/speakers/2024",
            "/speakers/2025",
            "/speakers/2026",
            "/agenda",
            "/agenda/speakers",
        ]
        
        for path in speaker_paths:
            url = urljoin(base_url, path)
            html = self._fetch_page(url)
            
            if html:
                # Try WBR-specific parsing first (for fieldserviceusa.wbresearch.com)
                if "wbresearch.com" in base_url:
                    page_speakers = self._parse_wbr_speakers_page(html)
                else:
                    page_speakers = self._parse_speakers_page(html)
                    
                if page_speakers:
                    speakers.extend(page_speakers)
                    self.log_status(f"Found {len(page_speakers)} speakers at {path}")
                    break
                    
            time.sleep(SCRAPER_CONFIG["request_delay"])
        
        # Deduplicate
        seen = set()
        unique_speakers = []
        for speaker in speakers:
            key = (speaker.name.lower(), speaker.company.lower())
            if key not in seen:
                seen.add(key)
                unique_speakers.append(speaker)
                
        return unique_speakers
    
    def _parse_wbr_speakers_page(self, html: str) -> list[Speaker]:
        """Parse speakers from WBR conference websites (fieldserviceusa.wbresearch.com)."""
        speakers = []
        soup = BeautifulSoup(html, "lxml")
        
        # WBR sites have speaker cards with h4 for name, then title/company below
        # Look for all h4 elements that could be speaker names
        h4_elements = soup.find_all("h4")
        
        for h4 in h4_elements:
            name = h4.get_text(strip=True)
            
            # Skip non-name h4s (like section headers)
            if not name or len(name) > 100 or name.lower() in ["our speakers", "become a speaker", "inspire others"]:
                continue
            
            # Look for title and company in surrounding elements
            title = ""
            company = ""
            
            # Check parent container for more info
            parent = h4.parent
            if parent:
                # Get all text content after the h4
                all_text = parent.get_text(separator="\n", strip=True)
                lines = [l.strip() for l in all_text.split("\n") if l.strip()]
                
                # Find the name's position and get subsequent lines
                for i, line in enumerate(lines):
                    if name in line:
                        # Next lines should be title and company
                        if i + 1 < len(lines):
                            title = lines[i + 1]
                        if i + 2 < len(lines):
                            company = lines[i + 2]
                        break
                
                # Also try to find company in bold/strong tags
                strong = parent.find("strong")
                if strong:
                    company = strong.get_text(strip=True)
            
            # Clean up - sometimes company has "Logo" suffix
            if company:
                company = re.sub(r'\s*Logo\s*$', '', company, flags=re.IGNORECASE)
            
            # Validate we have a real speaker entry
            if name and (title or company):
                # Skip if this looks like a sponsor/vendor (no title, just company)
                if title or len(name.split()) >= 2:
                    speakers.append(Speaker(
                        name=name,
                        title=title,
                        company=company
                    ))
        
        # Alternative parsing: look for specific WBR card structure
        if not speakers:
            # Try finding speaker containers by class patterns
            containers = soup.select('[class*="speaker"], [class*="card"], [class*="team"]')
            for container in containers:
                h4 = container.find("h4")
                if h4:
                    name = h4.get_text(strip=True)
                    if not name or len(name) > 100:
                        continue
                    
                    # Get all paragraph/span text
                    texts = []
                    for elem in container.find_all(["p", "span", "div"]):
                        text = elem.get_text(strip=True)
                        if text and text != name and len(text) < 200:
                            texts.append(text)
                    
                    title = texts[0] if len(texts) > 0 else ""
                    company = texts[1] if len(texts) > 1 else ""
                    
                    # Clean company name
                    if company:
                        company = re.sub(r'\s*Logo\s*$', '', company, flags=re.IGNORECASE)
                    
                    if name:
                        speakers.append(Speaker(name=name, title=title, company=company))
        
        # Final fallback: use text pattern matching
        if not speakers or len(speakers) < 10:
            text_speakers = self._parse_wbr_text_patterns(html)
            if len(text_speakers) > len(speakers):
                speakers = text_speakers
        
        return speakers
    
    def _parse_speakers_page(self, html: str) -> list[Speaker]:
        """Parse speaker information from HTML."""
        speakers = []
        soup = BeautifulSoup(html, "lxml")
        
        # Try various speaker card selectors
        card_selectors = [
            ".speaker-card",
            ".speaker",
            ".speaker-item",
            ".team-member",
            '[class*="speaker"]',
            ".agenda-speaker",
        ]
        
        cards = []
        for selector in card_selectors:
            cards = soup.select(selector)
            if cards:
                break
        
        for card in cards:
            speaker = self._parse_speaker_card(card)
            if speaker and speaker.name:
                speakers.append(speaker)
        
        # If no cards found, try parsing text patterns
        if not speakers:
            speakers = self._parse_speakers_from_text(soup)
            
        return speakers
    
    def _parse_speaker_card(self, card) -> Optional[Speaker]:
        """Parse a single speaker card element."""
        name = ""
        title = ""
        company = ""
        
        # Try various name selectors
        name_selectors = [".name", ".speaker-name", "h3", "h4", ".title"]
        for sel in name_selectors:
            elem = card.select_one(sel)
            if elem:
                name = elem.get_text(strip=True)
                if name and not any(x in name.lower() for x in ["vp", "director", "manager"]):
                    break
        
        # Try various title selectors
        title_selectors = [".job-title", ".position", ".role", ".speaker-title", "p"]
        for sel in title_selectors:
            elem = card.select_one(sel)
            if elem and elem != card.select_one(name_selectors[0] if name_selectors else ""):
                title = elem.get_text(strip=True)
                if title and title != name:
                    break
        
        # Try various company selectors
        company_selectors = [".company", ".organization", ".speaker-company"]
        for sel in company_selectors:
            elem = card.select_one(sel)
            if elem:
                company = elem.get_text(strip=True)
                break
        
        # Try to extract company from title if not found
        if not company and title:
            # Pattern: "VP of Service, Company Name" or "VP of Service at Company Name"
            patterns = [
                r",\s*([A-Z][A-Za-z\s&]+)$",
                r"\bat\s+([A-Z][A-Za-z\s&]+)$",
                r"\|\s*([A-Z][A-Za-z\s&]+)$",
            ]
            for pattern in patterns:
                match = re.search(pattern, title)
                if match:
                    company = match.group(1).strip()
                    title = title[:match.start()].strip().rstrip(",")
                    break
        
        if name:
            return Speaker(name=name, title=title, company=company)
        return None
    
    def _parse_speakers_from_text(self, soup) -> list[Speaker]:
        """Fallback: parse speakers from raw text patterns."""
        speakers = []
        text = soup.get_text()
        
        # Pattern: Name, Title, Company or Name | Title | Company
        patterns = [
            r"([A-Z][a-z]+ [A-Z][a-z]+),?\s*([A-Z][A-Za-z\s]+),?\s*([A-Z][A-Za-z\s&]+)",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches[:50]:  # Limit to prevent false positives
                if len(match) >= 3:
                    speakers.append(Speaker(
                        name=match[0].strip(),
                        title=match[1].strip(),
                        company=match[2].strip(),
                    ))
                    
        return speakers
    
    def _parse_wbr_text_patterns(self, html: str) -> list[Speaker]:
        """Parse WBR speaker page using text pattern matching."""
        speakers = []
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator="\n")
        
        # Split into lines
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        
        i = 0
        while i < len(lines) - 2:
            line = lines[i]
            
            # Check if this looks like a name (2-4 words, proper case, no common words)
            words = line.split()
            skip_words = ["our", "the", "and", "for", "logo", "speakers", "become", "speaker", 
                         "inspire", "others", "speaking", "opportunities", "view", "download",
                         "agenda", "sponsors", "contact", "phone", "fax", "copyright"]
            
            if (2 <= len(words) <= 5 and 
                all(w[0].isupper() for w in words if w) and
                not any(sw in line.lower() for sw in skip_words) and
                len(line) < 50):
                
                # Check next lines for title and company
                potential_title = lines[i + 1] if i + 1 < len(lines) else ""
                potential_company = lines[i + 2] if i + 2 < len(lines) else ""
                
                # Validate title looks like a job title
                title_keywords = ["vp", "vice president", "director", "manager", "head", 
                                 "chief", "president", "svp", "evp", "coo", "cto", "ceo",
                                 "cio", "senior", "global", "service", "field", "general"]
                
                if any(kw in potential_title.lower() for kw in title_keywords):
                    # Clean company name (remove "Logo" suffix)
                    company = re.sub(r'\s*Logo\s*$', '', potential_company, flags=re.IGNORECASE)
                    
                    if company and len(company) < 100:
                        speakers.append(Speaker(
                            name=line,
                            title=potential_title,
                            company=company
                        ))
                        i += 3  # Skip the lines we just processed
                        continue
            
            i += 1
        
        return speakers
    
    def _scrape_attendees(self, base_url: str) -> list[Attendee]:
        """Scrape attendee information.
        
        Note: Most conference sites don't have public attendee pages.
        Attendees are typically loaded from PDF files via --attendee-pdf or --ocr-text.
        This method is kept minimal to avoid unnecessary 404 errors.
        """
        # Skip automatic attendee scraping - use PDF/OCR instead
        # Attendee lists are typically gated/downloadable PDFs, not web pages
        return []
    
    def parse_pdf_attendees(self, pdf_path: str) -> list[Attendee]:
        """Parse attendee list from a PDF file using Mistral OCR."""
        if not os.path.exists(pdf_path):
            self.log_error(f"PDF file not found: {pdf_path}")
            return []
        
        self.log(f"Parsing PDF: {pdf_path}")
        
        # Try Mistral OCR first (best quality)
        if MISTRAL_OCR_SUPPORT:
            from config import MISTRAL_API_KEY
            if MISTRAL_API_KEY:
                attendees = self._parse_pdf_with_mistral(pdf_path, MISTRAL_API_KEY)
                if attendees:
                    return attendees
                self.log_status("Mistral OCR returned no results, trying fallback...")
            else:
                self.log_status("MISTRAL_API_KEY not set, using fallback PDF parser")
        
        # Fallback to pdfplumber
        if PDF_SUPPORT:
            return self._parse_pdf_with_pdfplumber(pdf_path)
        
        self.log_error("No PDF parser available. Install mistralai or pdfplumber.")
        return []
    
    def parse_ocr_text(self, ocr_text: str) -> list[Attendee]:
        """Parse pre-extracted OCR text using Gemini to extract companies."""
        self.log("Parsing OCR text with Gemini...")
        return self._parse_mistral_ocr_output(ocr_text, use_gemini=True)
    
    def _parse_pdf_with_mistral(self, pdf_path: str, api_key: str) -> list[Attendee]:
        """Parse PDF using Mistral OCR for high-quality extraction."""
        attendees = []
        
        try:
            self.log_status("Using Mistral OCR for PDF extraction...")
            client = Mistral(api_key=api_key)
            
            # Upload and process PDF with Mistral OCR
            with open(pdf_path, "rb") as f:
                # Upload file to Mistral
                uploaded_file = client.files.upload(
                    file={
                        "file_name": os.path.basename(pdf_path),
                        "content": f,
                    },
                    purpose="ocr"
                )
                
                # Get signed URL for the file
                signed_url = client.files.get_signed_url(file_id=uploaded_file.id)
                
                # Process with OCR
                ocr_response = client.ocr.process(
                    model="mistral-ocr-latest",
                    document={
                        "type": "document_url",
                        "document_url": signed_url.url,
                    }
                )
            
            # Extract text from all pages
            all_text = ""
            for page in ocr_response.pages:
                if hasattr(page, 'markdown') and page.markdown:
                    all_text += page.markdown + "\n"
                elif hasattr(page, 'text') and page.text:
                    all_text += page.text + "\n"
            
            self.log_status(f"Mistral OCR extracted {len(all_text)} characters")
            
            # Parse the markdown/text to extract attendees using Gemini
            attendees = self._parse_mistral_ocr_output(all_text, use_gemini=True)
            
            self.log(f"Extracted {len(attendees)} companies using Mistral OCR + Gemini")
            
        except Exception as e:
            self.log_error(f"Mistral OCR failed: {e}")
        
        return attendees
    
    def _parse_mistral_ocr_output(self, text: str, use_gemini: bool = True) -> list[Attendee]:
        """Parse Mistral OCR markdown output to extract attendees using Gemini."""
        
        # Use Gemini to intelligently extract companies/attendees from OCR output
        if use_gemini:
            from config import GEMINI_API_KEY
            if GEMINI_API_KEY:
                attendees = self._extract_with_gemini(text, GEMINI_API_KEY)
                if attendees:
                    return attendees
                self.log_status("Gemini extraction returned no results, trying fallback...")
        
        # Fallback: manual parsing
        return self._parse_ocr_tables_manually(text)
    
    def _extract_with_gemini(self, ocr_text: str, api_key: str) -> list[Attendee]:
        """Use Gemini to extract companies/attendees from OCR output."""
        import json
        
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            
            prompt = f"""You are parsing an OCR output from a conference attendee list PDF.
Extract ALL company names from this document. The document contains tables with company names.
Some companies have team sizes indicated like "IBM (Team of 15)" - extract just the company name.

OCR OUTPUT:
{ocr_text[:15000]}  

Return a JSON array of objects with this format:
[
    {{"company": "Company Name", "team_size": 1}},
    {{"company": "Another Company", "team_size": 5}}
]

Rules:
- Extract ONLY company/organization names, not section headers or marketing text
- If team size is mentioned like "(Team of X)", extract the number
- If no team size mentioned, use 1
- Skip entries like "REQUEST A QUOTE", "SPONSORSHIP", headers, etc.
- Return ONLY the JSON array, no explanation

JSON:"""

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            
            # Parse the response
            response_text = response.text.strip()
            
            # Clean up response
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            companies = json.loads(response_text)
            
            # Convert to Attendee objects (using company as the key identifier)
            attendees = []
            for item in companies:
                company_name = item.get("company", "").strip()
                team_size = item.get("team_size", 1)
                
                if company_name and len(company_name) > 1:
                    # Create one attendee entry per company (will be expanded to Company objects later)
                    attendees.append(Attendee(
                        name=f"Team ({team_size})" if team_size > 1 else "Representative",
                        title="Conference Attendee",
                        company=company_name
                    ))
            
            self.log(f"Gemini extracted {len(attendees)} companies from OCR output")
            return attendees
            
        except Exception as e:
            self.log_error(f"Gemini extraction failed: {e}")
            return []
    
    def _parse_ocr_tables_manually(self, text: str) -> list[Attendee]:
        """Fallback: manually parse OCR tables for company names."""
        attendees = []
        lines = text.split("\n")
        
        # Look for table structures in markdown
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            
            # Skip obvious non-company lines
            skip_patterns = [
                "request a quote", "sponsorship", "exhibition", "speaking",
                "field service", "audience", "job function", "seniority",
                "annual revenue", "click", "button", "contact", "img-",
                "billion", "million", "director", "manager", "c-level",
                "---", "===", "###", "**"
            ]
            if any(p in line.lower() for p in skip_patterns):
                continue
            
            # Parse markdown table rows
            if "|" in line:
                cells = [c.strip() for c in line.split("|") if c.strip()]
                
                for cell in cells:
                    # Clean up cell content
                    cell = cell.strip("*_ ")
                    
                    # Skip empty, numeric, or too short
                    if not cell or len(cell) < 3 or cell.replace(".", "").replace(",", "").isdigit():
                        continue
                    
                    # Skip percentage patterns
                    if "%" in cell:
                        continue
                    
                    # Extract company name and team size
                    company_name = cell
                    team_size = 1
                    
                    # Check for team size pattern "(Team of X)"
                    team_match = re.search(r'\(Team of (\d+)\)', cell)
                    if team_match:
                        team_size = int(team_match.group(1))
                        company_name = cell[:team_match.start()].strip()
                    
                    # Validate it looks like a company name
                    if company_name and len(company_name) > 2:
                        # Skip if it looks like a header or category
                        if company_name.lower() in ["company", "organization", "name", "attendee"]:
                            continue
                        
                        attendees.append(Attendee(
                            name=f"Team ({team_size})" if team_size > 1 else "Representative",
                            title="Conference Attendee",
                            company=company_name
                        ))
        
        # Deduplicate by company name
        seen = set()
        unique_attendees = []
        for att in attendees:
            if att.company.lower() not in seen:
                seen.add(att.company.lower())
                unique_attendees.append(att)
        
        return unique_attendees
    
    def _parse_pdf_with_pdfplumber(self, pdf_path: str) -> list[Attendee]:
        """Fallback PDF parsing using pdfplumber."""
        attendees = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                all_text = ""
                
                # Extract text from all pages
                for page in pdf.pages:
                    # Try to extract tables first
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            for row in table:
                                if row and len(row) >= 2:
                                    name = row[0] if row[0] else ""
                                    title = row[1] if len(row) > 1 and row[1] else ""
                                    company = row[2] if len(row) > 2 and row[2] else ""
                                    
                                    if name and name.lower() not in ["name", "attendee", "delegate", "first name"]:
                                        name = str(name).strip()
                                        title = str(title).strip() if title else ""
                                        company = str(company).strip() if company else ""
                                        
                                        if name and len(name) > 1:
                                            attendees.append(Attendee(
                                                name=name,
                                                title=title,
                                                company=company
                                            ))
                    
                    page_text = page.extract_text()
                    if page_text:
                        all_text += page_text + "\n"
                
                if not attendees:
                    attendees = self._parse_attendees_from_text(all_text)
                
        except Exception as e:
            self.log_error(f"pdfplumber failed: {e}")
        
        self.log(f"Extracted {len(attendees)} attendees from PDF (pdfplumber)")
        return attendees
    
    def _parse_attendees_from_text(self, text: str) -> list[Attendee]:
        """Parse attendees from raw text (fallback for PDFs without tables)."""
        attendees = []
        lines = text.split("\n")
        
        # Common patterns in attendee lists
        # Pattern 1: "Name | Title | Company" or "Name, Title, Company"
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue
            
            # Skip obvious non-attendee lines
            skip_words = ["page", "attendee list", "field service", "conference", 
                         "©", "copyright", "www.", "http", "email", "phone"]
            if any(sw in line.lower() for sw in skip_words):
                continue
            
            # Try splitting by common delimiters
            parts = None
            for delimiter in ["|", "\t", "  ", ","]:
                if delimiter in line:
                    parts = [p.strip() for p in line.split(delimiter) if p.strip()]
                    if len(parts) >= 2:
                        break
            
            if parts and len(parts) >= 2:
                name = parts[0]
                title = parts[1] if len(parts) > 1 else ""
                company = parts[2] if len(parts) > 2 else ""
                
                # Validate name (should look like a name)
                if (2 <= len(name.split()) <= 5 and 
                    name[0].isupper() and 
                    name.lower() not in ["name", "attendee", "title", "company"]):
                    attendees.append(Attendee(
                        name=name,
                        title=title,
                        company=company
                    ))
        
        return attendees
    
    def _extract_companies(self, 
                           speakers: list[Speaker],
                           attendees: list[Attendee],
                           main_html: Optional[str]) -> list[Company]:
        """Extract unique companies from all sources."""
        companies_dict = {}
        
        # From speakers
        for speaker in speakers:
            if speaker.company:
                name = speaker.company.strip()
                if name not in companies_dict:
                    companies_dict[name] = Company(name=name, source="speaker")
                companies_dict[name].speakers.append(speaker.name)
        
        # From attendees
        for attendee in attendees:
            if attendee.company:
                name = attendee.company.strip()
                if name not in companies_dict:
                    companies_dict[name] = Company(name=name, source="attendee")
                companies_dict[name].attendees.append(attendee.name)
        
        # From logos on main page
        if main_html:
            soup = BeautifulSoup(main_html, "lxml")
            logo_selectors = [
                ".sponsor-logo img",
                ".partner-logo img",
                ".logo-grid img",
                '[class*="sponsor"] img',
                '[class*="partner"] img',
            ]
            
            for selector in logo_selectors:
                logos = soup.select(selector)
                for logo in logos:
                    # Try to get company name from alt text or filename
                    alt = logo.get("alt", "")
                    src = logo.get("src", "")
                    
                    name = alt.strip()
                    if not name and src:
                        # Extract from filename
                        name = src.split("/")[-1].split(".")[0]
                        name = name.replace("-", " ").replace("_", " ").title()
                    
                    if name and len(name) > 2 and name not in companies_dict:
                        companies_dict[name] = Company(name=name, source="logo")
        
        return list(companies_dict.values())
