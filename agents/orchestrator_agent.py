"""
Orchestrator Agent

The brain of the multi-agent system. Coordinates all agents,
manages the pipeline flow, and resolves conflicts.
"""
import csv
import os
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from agents.base_agent import BaseAgent
from agents.scraper_agent import ScraperAgent
from agents.enricher_agent import EnricherAgent
from agents.icp_validator_agent import ICPValidatorAgent
from agents.quality_agent import QualityAgent
from models.schemas import AgentMessage, MessageType
from communication.message_bus import MessageBus
from communication.context import SharedContext
from llm.gemini_client import GeminiClient
from config import OUTPUT_CONFIG

console = Console()


class OrchestratorAgent(BaseAgent):
    """
    Central orchestrator that coordinates all agents in the pipeline.
    
    Features:
    - Manages pipeline execution flow
    - Coordinates agent communication
    - Resolves conflicts between agents
    - Generates final output
    """
    
    def __init__(self, message_bus: MessageBus, gemini_client: Optional[GeminiClient] = None):
        super().__init__("OrchestratorAgent", message_bus)
        self.gemini = gemini_client
        
        # Create child agents
        self.scraper = ScraperAgent(message_bus)
        self.enricher = EnricherAgent(message_bus, gemini_client)
        self.validator = ICPValidatorAgent(message_bus, gemini_client)
        self.quality = QualityAgent(message_bus, gemini_client)
        
        self._pipeline_status = {}
        
    def process(self, context: SharedContext, attendee_pdf: str = None, ocr_text: str = None) -> SharedContext:
        """Run the full agent pipeline."""
        self.log("Starting multi-agent pipeline")
        self._display_pipeline_start(context.url)
        
        # Phase 1: Scrape conference data
        self._update_status("scraping", "in_progress")
        context = self.scraper.execute(context)
        self._update_status("scraping", "complete")
        
        # Phase 1b: Load attendees from OCR text if provided (uses Gemini for extraction)
        if ocr_text:
            self.log("Extracting companies from OCR text using Gemini...")
            ocr_attendees = self.scraper.parse_ocr_text(ocr_text)
            if ocr_attendees:
                if context.conference_data:
                    context.conference_data.attendees.extend(ocr_attendees)
                    self.log(f"Added {len(ocr_attendees)} companies from OCR text")
                    
                    # Extract companies from OCR attendees
                    for attendee in ocr_attendees:
                        if attendee.company:
                            existing = next(
                                (c for c in context.conference_data.companies 
                                 if c.name.lower() == attendee.company.lower()),
                                None
                            )
                            if not existing:
                                from models.schemas import Company
                                context.conference_data.companies.append(
                                    Company(name=attendee.company, source="ocr_attendee")
                                )
        
        # Phase 1c: Load attendees from PDF if provided
        if attendee_pdf:
            self.log(f"Loading attendees from PDF: {attendee_pdf}")
            pdf_attendees = self.scraper.parse_pdf_attendees(attendee_pdf)
            if pdf_attendees and context.conference_data:
                # Add PDF attendees to conference data
                context.conference_data.attendees.extend(pdf_attendees)
                self.log(f"Added {len(pdf_attendees)} companies from PDF")
                
                # Extract companies from PDF attendees
                for attendee in pdf_attendees:
                    if attendee.company:
                        # Check if company already exists
                        existing = next(
                            (c for c in context.conference_data.companies 
                             if c.name.lower() == attendee.company.lower()),
                            None
                        )
                        if not existing:
                            from models.schemas import Company
                            context.conference_data.companies.append(
                                Company(name=attendee.company, source="pdf_attendee")
                            )
        
        if not context.conference_data or not context.conference_data.companies:
            self.log_error("No data scraped. Pipeline cannot continue.")
            self._display_no_data_message(context.url)
            return context
        
        # Phase 2: Enrich company data
        self._update_status("enrichment", "in_progress")
        context = self.enricher.execute(context)
        self._update_status("enrichment", "complete")
        
        # Phase 3: Validate against ICP
        self._update_status("validation", "in_progress")
        context = self.validator.execute(context)
        self._update_status("validation", "complete")
        
        # Phase 4: Quality review
        self._update_status("quality_review", "in_progress")
        context = self.quality.execute(context)
        self._update_status("quality_review", "complete")
        
        # Display results summary
        self._display_results_summary(context)
        
        self.log_success("Pipeline complete!")
        context.set_status("complete")
        
        return context
    
    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle messages from child agents."""
        # Log status updates
        if message.message_type == MessageType.STATUS:
            self.log_status(f"{message.sender}: {message.action}")
            
        elif message.message_type == MessageType.RESPONSE:
            # Track completion of pipeline stages
            if message.action == "scrape_complete":
                payload = message.payload
                self.log(f"Scraping complete: {payload.get('speakers_count', 0)} speakers, "
                        f"{payload.get('companies_count', 0)} companies")
                        
            elif message.action == "validation_complete":
                payload = message.payload
                self.log(f"Validation complete: {payload.get('high_fit', 0)} High, "
                        f"{payload.get('medium_fit', 0)} Medium, {payload.get('low_fit', 0)} Low fit")
                        
            elif message.action == "quality_review_complete":
                payload = message.payload
                self.log(f"Quality review: {payload.get('confirmed', 0)} confirmed, "
                        f"{payload.get('disputed', 0)} disputed")
        
        elif message.message_type == MessageType.ERROR:
            self.log_error(f"{message.sender}: {message.payload.get('error', 'Unknown error')}")
            
        return None
    
    def export_to_csv(self, context: SharedContext, output_path: str) -> str:
        """Export results to CSV file."""
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                "Name", "Title", "Company", "Type", "Industry",
                "ICP Score", "ICP Fit", "Reasoning"
            ])
            
            # Get ICP results mapped by company
            icp_by_company = {r.company_name: r for r in context.icp_results}
            
            # Write speakers
            if context.conference_data:
                for speaker in context.conference_data.speakers:
                    icp = icp_by_company.get(speaker.company)
                    writer.writerow([
                        speaker.name,
                        speaker.title,
                        speaker.company,
                        "Speaker",
                        icp.reasoning.split(";")[0] if icp else "",
                        icp.final_score or icp.score if icp else "",
                        icp.fit_level if icp else "",
                        icp.reasoning if icp else "",
                    ])
                
                # Write attendees
                for attendee in context.conference_data.attendees:
                    icp = icp_by_company.get(attendee.company)
                    writer.writerow([
                        attendee.name,
                        attendee.title,
                        attendee.company,
                        "Attendee",
                        "",
                        icp.final_score or icp.score if icp else "",
                        icp.fit_level if icp else "",
                        icp.reasoning if icp else "",
                    ])
                
                # Write companies without speakers/attendees
                written_companies = set(s.company for s in context.conference_data.speakers)
                written_companies.update(a.company for a in context.conference_data.attendees)
                
                for company in context.conference_data.companies:
                    if company.name not in written_companies:
                        icp = icp_by_company.get(company.name)
                        writer.writerow([
                            "",
                            "",
                            company.name,
                            "Logo/Sponsor",
                            company.industry,
                            icp.final_score or icp.score if icp else "",
                            icp.fit_level if icp else "",
                            icp.reasoning if icp else "",
                        ])
        
        self.log_success(f"Exported to {output_path}")
        return output_path
    
    def _update_status(self, stage: str, status: str):
        """Update pipeline stage status."""
        self._pipeline_status[stage] = status
        
    def _display_pipeline_start(self, url: str):
        """Display pipeline start banner."""
        panel = Panel(
            f"[bold]Conference URL:[/bold] {url}\n"
            f"[bold]Started at:[/bold] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "[dim]Pipeline stages: Scrape → Enrich → Validate → Quality Review → Export[/dim]",
            title="[bold cyan]Multi-Agent Pipeline Started[/bold cyan]",
            border_style="cyan",
        )
        console.print(panel)
    
    def _display_no_data_message(self, url: str):
        """Display message when no data could be scraped."""
        console.print(Panel(
            f"[yellow]Could not scrape data from:[/yellow]\n{url}\n\n"
            "[dim]This may be due to:[/dim]\n"
            "• Website requires authentication\n"
            "• Page structure not recognized\n"
            "• Rate limiting or blocking\n\n"
            "[dim]Try:[/dim]\n"
            "• Using a different URL (e.g., /speakers page directly)\n"
            "• Checking if the website is accessible in a browser\n"
            "• Using sample data with --demo flag",
            title="[yellow]No Data Scraped[/yellow]",
            border_style="yellow",
        ))
    
    def _display_results_summary(self, context: SharedContext):
        """Display a summary table of results."""
        if not context.icp_results:
            return
            
        # Create summary table
        table = Table(title="ICP Validation Results Summary")
        table.add_column("Fit Level", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("Top Companies")
        
        # Group by fit level
        high_fit = [r for r in context.icp_results if r.fit_level == "High"]
        medium_fit = [r for r in context.icp_results if r.fit_level == "Medium"]
        low_fit = [r for r in context.icp_results if r.fit_level == "Low"]
        
        # Sort by score
        high_fit.sort(key=lambda x: x.final_score or x.score, reverse=True)
        medium_fit.sort(key=lambda x: x.final_score or x.score, reverse=True)
        
        # Add rows
        table.add_row(
            "[green]High[/green]",
            str(len(high_fit)),
            ", ".join(r.company_name for r in high_fit[:3]) or "None"
        )
        table.add_row(
            "[yellow]Medium[/yellow]",
            str(len(medium_fit)),
            ", ".join(r.company_name for r in medium_fit[:3]) or "None"
        )
        table.add_row(
            "[red]Low[/red]",
            str(len(low_fit)),
            f"{len(low_fit)} companies"
        )
        
        console.print("\n")
        console.print(table)
        
        # Show top leads
        if high_fit:
            console.print("\n[bold green]Top High-Fit Leads:[/bold green]")
            for i, result in enumerate(high_fit[:5], 1):
                score = result.final_score or result.score
                console.print(f"  {i}. [bold]{result.company_name}[/bold] (Score: {score})")
                reasoning_text = result.reasoning[:100] + "..." if len(result.reasoning) > 100 else result.reasoning
                console.print(f"     [dim]{reasoning_text}[/dim]")
    
    def run_demo(self, context: SharedContext) -> SharedContext:
        """Run pipeline with demo data when scraping fails."""
        from models.schemas import ConferenceData, Speaker, Company
        
        self.log("Running with demo data...")
        
        # Demo data based on Field Service USA speakers
        demo_speakers = [
            Speaker(name="Haroon Abbu", title="SVP, Digital, Data & Analytics", company="Bell + Howell"),
            Speaker(name="Adam Gloss", title="SVP, Service", company="McKinstry"),
            Speaker(name="Joseph Lang", title="VP Service Technology", company="Comfort Systems USA"),
            Speaker(name="Patrick Van Wert", title="VP Aftermarket", company="Tennant Co."),
            Speaker(name="Thomas Shanks", title="Director of Operations", company="TK Elevator"),
            Speaker(name="Alban Cambournac", title="VP Consulting & Digital Services", company="Schneider Electric"),
            Speaker(name="Chris Westlake", title="VP Life Sciences Technical Services", company="Genpact"),
            Speaker(name="Jessica Murillo", title="COO, Technology Lifecycle Services", company="IBM"),
            Speaker(name="Michelle Vaccarello", title="VP North America Services", company="Diebold Nixdorf"),
            Speaker(name="Nick Cribb", title="President & CEO", company="Sam Service Inc"),
        ]
        
        demo_companies = [
            Company(name="Bell + Howell", industry="Industrial Automation", source="speaker", speakers=["Haroon Abbu"]),
            Company(name="McKinstry", industry="Building Services", source="speaker", speakers=["Adam Gloss"]),
            Company(name="Comfort Systems USA", industry="HVAC", source="speaker", speakers=["Joseph Lang"]),
            Company(name="Tennant Co.", industry="Manufacturing", source="speaker", speakers=["Patrick Van Wert"]),
            Company(name="TK Elevator", industry="Elevator/Escalator", source="speaker", speakers=["Thomas Shanks"]),
            Company(name="Schneider Electric", industry="Energy/Automation", source="speaker", speakers=["Alban Cambournac"]),
            Company(name="Genpact", industry="Professional Services", source="speaker", speakers=["Chris Westlake"]),
            Company(name="IBM", industry="Technology", source="speaker", speakers=["Jessica Murillo"]),
            Company(name="Diebold Nixdorf", industry="Financial Services Tech", source="speaker", speakers=["Michelle Vaccarello"]),
            Company(name="Sam Service Inc", industry="Field Service", source="speaker", speakers=["Nick Cribb"]),
        ]
        
        context.conference_data = ConferenceData(
            url=context.url,
            conference_name="Field Service USA (Demo Data)",
            speakers=demo_speakers,
            companies=demo_companies,
        )
        
        # Run remaining pipeline
        self._update_status("scraping", "complete (demo)")
        
        context = self.enricher.execute(context)
        self._update_status("enrichment", "complete")
        
        context = self.validator.execute(context)
        self._update_status("validation", "complete")
        
        context = self.quality.execute(context)
        self._update_status("quality_review", "complete")
        
        self._display_results_summary(context)
        
        self.log_success("Demo pipeline complete!")
        context.set_status("complete")
        
        return context
