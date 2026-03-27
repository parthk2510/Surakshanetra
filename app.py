#!/usr/bin/env python3

import sys
from pathlib import Path

# ── Load .env before any backend imports so CHAINBREAK_SECRET_KEY is available ──
_env_file = Path(__file__).parent / '.env'
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)
    except ImportError:
        pass  # python-dotenv not installed; env vars must be set manually

sys.path.insert(0, str(Path(__file__).parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent / "crypto_threat_intel_package" / "scrapers"))

from backend import api_root as api_module
from backend.chainbreak import ChainBreak

# ── Expose ASGI app at module level so uvicorn/gunicorn can import it directly:
#      uvicorn app:app --host 0.0.0.0 --port 5000
#      gunicorn app:app --worker-class uvicorn.workers.UvicornWorker
from backend.api_root import app  # noqa: F401  (re-export)
import argparse
import logging
logger = logging.getLogger(__name__)

def run_standalone_analysis(address: str = None):
    """Run standalone ChainBreak analysis"""
    try:
        print("🔗 ChainBreak - Blockchain Forensic Analysis Tool")
        print("=" * 60)

        # Initialize ChainBreak
        print("Initializing ChainBreak...")
        chainbreak = ChainBreak()

        # Check system status
        print("\nChecking system status...")
        status = chainbreak.get_system_status()
        print(f"System Status: {status['system_status']}")
        print(f"Neo4j Connection: {status['neo4j_connection']}")

        if status['system_status'] != 'operational':
            print(
                "❌ System not operational. Please check configuration and Neo4j connection.")
            return

        if not address:
            address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
            print(f"\nNo address provided, using test address: {address}")

        # Run analysis
        print(f"\n🚀 Starting analysis of address: {address}")
        print("This may take several minutes depending on transaction volume...")

        results = chainbreak.analyze_address(
            address, generate_visualizations=True)

        if 'error' in results:
            print(f"❌ Analysis failed: {results['error']}")
            return

        # Display results
        print("\n✅ Analysis completed successfully!")
        print("\n📊 Analysis Summary:")
        print(f"  Address: {results['address']}")
        print(f"  Blockchain: {results['blockchain']}")
        print(f"  Risk Level: {results['risk_score']['risk_level']}")
        print(f"  Risk Score: {results['risk_score']['total_risk_score']:.3f}")
        print(f"  Total Anomalies: {results['summary']['total_anomalies']}")
        print(f"  Layering Patterns: {results['summary']['layering_count']}")
        print(f"  Smurfing Patterns: {results['summary']['smurfing_count']}")
        print(
            f"  Volume Anomalies: {results['summary']['volume_anomaly_count']}")

        # Display recommendations
        if results['summary']['recommendations']:
            print("\n💡 Recommendations:")
            for rec in results['summary']['recommendations']:
                print(f"  • {rec}")

        # Export to Gephi if requested
        export_choice = input(
            "\n📤 Export network to Gephi format? (y/n): ").lower().strip()
        if export_choice in ['y', 'yes']:
            print("Exporting to Gephi...")
            export_file = chainbreak.export_network_to_gephi(address)
            if export_file:
                print(f"✅ Network exported to: {export_file}")
            else:
                print("❌ Export failed")

        print("\n🎉 Analysis complete! Check the generated visualizations and log files.")

    except KeyboardInterrupt:
        print("\n\n⚠️  Analysis interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during analysis: {str(e)}")
        logger.error(f"Standalone analysis error: {str(e)}")
    finally:
        if 'chainbreak' in locals():
            chainbreak.close()


def run_api_server(port: int = 5000):
    """Start the FastAPI server via uvicorn"""
    try:
        import uvicorn
        print("Starting ChainBreak API Server (FastAPI)...")
        print("=" * 50)

        from backend.database.models import init_db, SessionLocal
        from backend.database.rbac import RBACManager
        from backend.logger.app_logger import setup_logging
        setup_logging()
        init_db()
        db = SessionLocal()
        try:
            RBACManager.create_default_roles(db)
        finally:
            db.close()

        print(f"API Docs: http://localhost:{port}/docs")
        print(f"Server running on http://localhost:{port}")
        print("Press Ctrl+C to stop the server")

        uvicorn.run(
            "backend.api_root:app",
            host="0.0.0.0",
            port=port,
            reload=False,
            log_level="info",
        )

    except KeyboardInterrupt:
        print("\n\n⚠️  API server stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting API server: {str(e)}")
        logger.error(f"API server error: {str(e)}")



def main():
    """Main application entry point"""
    parser = argparse.ArgumentParser(
        description="ChainBreak - Blockchain Forensic Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app.py                           # Run standalone analysis
  python app.py --api                     # Start API server
  python app.py --analyze 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
  python app.py --config custom_config.yaml
        """
    )

    parser.add_argument(
        '--api',
        action='store_true',
        help='Start the FastAPI server powered by uvicorn'
    )

    parser.add_argument(
        '--analyze',
        metavar='ADDRESS',
        help='Analyze a specific Bitcoin address'
    )

    parser.add_argument(
        '--config',
        metavar='CONFIG_FILE',
        default='config.yaml',
        help='Configuration file path (default: config.yaml)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Port to run the API server on (default: 5000)'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check if config file exists
    if not Path(args.config).exists():
        print(f"Configuration file {args.config} not found, using defaults")

    # Run appropriate mode
    if args.api:
        run_api_server(port=args.port)
    elif args.analyze:
        run_standalone_analysis(args.analyze)
    else:
        run_standalone_analysis()


if __name__ == '__main__':
    main()
