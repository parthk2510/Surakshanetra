#!/usr/bin/env python3
"""
Temporal Community Evolution Analysis - Main Execution Script

This script provides the main entry point for analyzing community evolution
in Bitcoin transaction networks across temporal snapshots.

Usage:
    # Using file paths
    python run_temporal_analysis.py --t1 day1_graph.json --t2 day3_graph.json
    
    # With custom algorithm
    python run_temporal_analysis.py --t1 day1.json --t2 day3.json --algorithm leiden
    
    # With output directory
    python run_temporal_analysis.py --t1 day1.json --t2 day3.json --output results/
    
    # Run demo with mock data
    python run_temporal_analysis.py --demo

Example:
    python run_temporal_analysis.py \\
        --t1 data/graph/snapshot_day1.json \\
        --t2 data/graph/snapshot_day3.json \\
        --algorithm louvain \\
        --resolution 1.0 \\
        --output results/ \\
        --verbose
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from temporal_analysis import TemporalAnalysisPipeline
from temporal_analysis.pipeline import create_mock_snapshots


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Reduce noise from external libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('matplotlib').setLevel(logging.WARNING)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Temporal Community Evolution Analysis for Bitcoin Transaction Networks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Input files
    parser.add_argument(
        '--t1', '--snapshot-t1',
        type=str,
        help='Path to first temporal snapshot (T1) JSON file'
    )
    parser.add_argument(
        '--t2', '--snapshot-t2',
        type=str,
        help='Path to second temporal snapshot (T2) JSON file'
    )
    
    # Algorithm options
    parser.add_argument(
        '--algorithm', '-a',
        type=str,
        default='louvain',
        choices=['louvain', 'leiden', 'label_propagation', 'infomap'],
        help='Community detection algorithm (default: louvain)'
    )
    parser.add_argument(
        '--resolution', '-r',
        type=float,
        default=1.0,
        help='Resolution parameter for Louvain/Leiden (default: 1.0)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed for reproducibility (default: 42)'
    )
    
    # Graph options
    parser.add_argument(
        '--directed',
        action='store_true',
        help='Build directed graphs (default: undirected)'
    )
    parser.add_argument(
        '--unweighted',
        action='store_true',
        help='Ignore edge weights (default: weighted)'
    )
    parser.add_argument(
        '--address-only',
        action='store_true',
        help='Analyze only address nodes (project bipartite graph)'
    )
    
    # Transition detection thresholds
    parser.add_argument(
        '--split-threshold',
        type=float,
        default=0.25,
        help='Threshold for split detection (default: 0.25)'
    )
    parser.add_argument(
        '--merge-threshold',
        type=float,
        default=0.25,
        help='Threshold for merge detection (default: 0.25)'
    )
    
    # Output options
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='.',
        help='Output directory for results (default: current directory)'
    )
    parser.add_argument(
        '--formats',
        nargs='+',
        default=['json', 'text', 'markdown'],
        choices=['json', 'text', 'markdown'],
        help='Output formats (default: all)'
    )
    parser.add_argument(
        '--no-export',
        action='store_true',
        help='Do not export results to files (print only)'
    )
    
    # Demo mode
    parser.add_argument(
        '--demo',
        action='store_true',
        help='Run demo with mock data'
    )
    
    # General options
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress all output except errors'
    )
    
    return parser.parse_args()


def run_demo() -> None:
    """Run a demonstration with mock data."""
    print("=" * 70)
    print("TEMPORAL COMMUNITY EVOLUTION ANALYSIS - DEMO MODE")
    print("=" * 70)
    print()
    print("This demo creates mock Bitcoin transaction network snapshots to")
    print("demonstrate the community evolution analysis capabilities.")
    print()
    
    # Create mock data
    data_t1, data_t2 = create_mock_snapshots()
    
    print(f"Created mock data:")
    print(f"  T1: {len(data_t1['nodes'])} nodes, {len(data_t1['edges'])} edges")
    print(f"  T2: {len(data_t2['nodes'])} nodes, {len(data_t2['edges'])} edges")
    print()
    
    # Create pipeline
    pipeline = TemporalAnalysisPipeline(
        algorithm='louvain',
        resolution=1.0,
        seed=42
    )
    
    # Run analysis
    timestamp_t1 = datetime.now() - timedelta(days=2)
    timestamp_t2 = datetime.now()
    
    result = pipeline.run_from_data(
        data_t1=data_t1,
        data_t2=data_t2,
        timestamp_t1=timestamp_t1,
        timestamp_t2=timestamp_t2,
        metadata={'demo_mode': True}
    )
    
    # Print summary
    pipeline.print_summary(result)
    
    print()
    print("Demo complete! In production use, provide --t1 and --t2 arguments")
    print("with paths to your Bitcoin transaction graph JSON files.")
    print()


def main() -> int:
    """Main entry point."""
    args = parse_arguments()
    
    # Setup logging
    if args.quiet:
        logging.disable(logging.CRITICAL)
    else:
        setup_logging(verbose=args.verbose)
    
    logger = logging.getLogger(__name__)
    
    # Demo mode
    if args.demo:
        run_demo()
        return 0
    
    # Validate inputs
    if not args.t1 or not args.t2:
        print("Error: --t1 and --t2 are required (or use --demo)")
        print("Use --help for usage information.")
        return 1
    
    t1_path = Path(args.t1)
    t2_path = Path(args.t2)
    
    if not t1_path.exists():
        print(f"Error: T1 file not found: {t1_path}")
        return 1
    
    if not t2_path.exists():
        print(f"Error: T2 file not found: {t2_path}")
        return 1
    
    try:
        # Create pipeline with configuration
        pipeline = TemporalAnalysisPipeline(
            algorithm=args.algorithm,
            resolution=args.resolution,
            seed=args.seed,
            directed=args.directed,
            weighted=not args.unweighted,
            use_address_graph=args.address_only,
            split_threshold=args.split_threshold,
            merge_threshold=args.merge_threshold
        )
        
        # Run analysis
        result = pipeline.run(
            snapshot_t1_path=t1_path,
            snapshot_t2_path=t2_path
        )
        
        # Print summary (unless quiet mode)
        if not args.quiet:
            pipeline.print_summary(result)
        
        # Export results
        if not args.no_export:
            exported = pipeline.export_results(
                result=result,
                output_dir=args.output,
                formats=args.formats
            )
            
            if not args.quiet:
                print()
                print("Exported files:")
                for fmt, path in exported.items():
                    print(f"  {fmt}: {path}")
        
        return 0
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 1
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.info("Install required packages with: pip install -r requirements.txt")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
