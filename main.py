#!/usr/bin/env python3
"""
Multi-Agent Conference Lead Collection System

A system of autonomous AI agents that work together to:
1. Scrape conference websites for speaker/attendee data
2. Enrich company information
3. Validate companies against ICP criteria
4. Quality review and dispute scores
5. Export prioritized leads to CSV

Usage:
    python main.py run --url "https://fieldserviceusa.wbresearch.com" --output leads.csv
    python main.py run --url "..." --verbose  # Show agent conversations
    python main.py run --demo  # Run with demo data
    python main.py run --url "..." --attendee-pdf attendeelist.pdf  # Include PDF attendee list
"""
import argparse
import os
import sys
from datetime import datetime

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from rich.console import Console

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.orchestrator_agent import OrchestratorAgent
from communication.message_bus import MessageBus
from communication.context import SharedContext
from llm.gemini_client import GeminiClient
from config import GEMINI_API_KEY

console = Console(force_terminal=True)


def display_banner():
    """Display the application banner."""
    banner = """
+---------------------------------------------------------------+
|     Multi-Agent Conference Lead Collection System             |
|                                                               |
|  Agents: Scraper -> Enricher -> Validator -> Quality -> Export|
+---------------------------------------------------------------+
    """
    console.print(banner, style="bold cyan")


def run_pipeline(url: str, output: str, verbose: bool = False, demo: bool = False, 
                 attendee_pdf: str = None, ocr_text_file: str = None):
    """Run the full multi-agent pipeline."""
    display_banner()
    
    # Initialize Gemini client if API key available
    gemini_client = None
    if GEMINI_API_KEY:
        try:
            gemini_client = GeminiClient()
            console.print("[green][OK] Gemini API initialized[/green]")
        except Exception as e:
            console.print(f"[yellow][!] Gemini API not available: {e}[/yellow]")
            console.print("[dim]Falling back to rule-based validation[/dim]")
    else:
        console.print("[yellow][!] GEMINI_API_KEY not set[/yellow]")
        console.print("[dim]Set GEMINI_API_KEY environment variable for AI-powered validation[/dim]")
        console.print("[dim]Falling back to rule-based validation[/dim]")
    
    console.print()
    
    # Initialize message bus with verbose mode
    message_bus = MessageBus(verbose=verbose)
    
    # Initialize orchestrator
    orchestrator = OrchestratorAgent(message_bus, gemini_client)
    
    # Create shared context
    context = SharedContext(url=url, verbose=verbose)
    
    # Load OCR text if provided
    ocr_text = None
    if ocr_text_file and os.path.exists(ocr_text_file):
        with open(ocr_text_file, "r", encoding="utf-8") as f:
            ocr_text = f.read()
        console.print(f"[green][OK] Loaded OCR text from {ocr_text_file}[/green]")
    
    try:
        if demo:
            # Run with demo data
            context = orchestrator.run_demo(context)
        else:
            # Run full pipeline with optional PDF/OCR attendee list
            context = orchestrator.process(context, attendee_pdf=attendee_pdf, ocr_text=ocr_text)
        
        # Export results
        if context.icp_results:
            output_path = orchestrator.export_to_csv(context, output)
            console.print(f"\n[bold green][OK] Results exported to: {output_path}[/bold green]")
        else:
            console.print("\n[yellow]No results to export[/yellow]")
            
        # Show stats
        stats = context.get_stats()
        console.print(f"\n[dim]Pipeline completed in {stats['elapsed_time']:.2f} seconds[/dim]")
        console.print(f"[dim]Total messages exchanged: {stats['message_count']}[/dim]")
        
        if stats.get('error_count', 0) > 0:
            console.print(f"[yellow]Errors encountered: {stats['error_count']}[/yellow]")
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Pipeline error: {e}[/bold red]")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Conference Lead Collection System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py run --url "https://fieldserviceusa.wbresearch.com/speakers"
  python main.py run --url "..." --attendee-pdf attendeelist.pdf
  python main.py run --url "..." --verbose
  python main.py run --demo --output demo_leads.csv
  
Environment Variables:
  GEMINI_API_KEY    Your Google Gemini API key for AI-powered validation
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run the full pipeline")
    run_parser.add_argument(
        "--url", "-u",
        default="https://fieldserviceusa.wbresearch.com/speakers",
        help="Conference website URL (default: Field Service USA speakers page)"
    )
    run_parser.add_argument(
        "--output", "-o",
        default=f"output/leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        help="Output CSV file path"
    )
    run_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show agent-to-agent conversations"
    )
    run_parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with demo data (for testing)"
    )
    run_parser.add_argument(
        "--attendee-pdf", "-p",
        help="Path to PDF file containing attendee list"
    )
    run_parser.add_argument(
        "--ocr-text", "-t",
        help="Path to text file containing pre-extracted OCR output"
    )
    
    # Scrape command (individual agent)
    scrape_parser = subparsers.add_parser("scrape", help="Run only the scraper agent")
    scrape_parser.add_argument("--url", "-u", required=True, help="URL to scrape")
    scrape_parser.add_argument("--output", "-o", default="scraped_data.json", help="Output file")
    
    # Validate command (individual agent)
    validate_parser = subparsers.add_parser("validate", help="Run ICP validation on data")
    validate_parser.add_argument("--input", "-i", required=True, help="Input JSON file")
    validate_parser.add_argument("--output", "-o", default="validated.csv", help="Output CSV")
    
    args = parser.parse_args()
    
    if args.command == "run":
        run_pipeline(
            url=args.url,
            output=args.output,
            verbose=args.verbose,
            demo=args.demo,
            attendee_pdf=getattr(args, 'attendee_pdf', None),
            ocr_text_file=getattr(args, 'ocr_text', None),
        )
    elif args.command == "scrape":
        # Individual scraper execution
        console.print("[yellow]Individual agent execution not yet implemented[/yellow]")
        console.print("Use 'run' command for full pipeline")
    elif args.command == "validate":
        # Individual validator execution
        console.print("[yellow]Individual agent execution not yet implemented[/yellow]")
        console.print("Use 'run' command for full pipeline")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
