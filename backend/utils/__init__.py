"""
Utility Functions for ChainBreak
Batch processing and performance optimization utilities
"""

import logging
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handles batch processing for large datasets"""

    def __init__(self, neo4j_driver, batch_size: int = 1000, max_workers: int = 4):
        self.driver = neo4j_driver
        self.batch_size = batch_size
        self.max_workers = max_workers

    def process_transactions_batch(self, transaction_hashes: List[str],
                                   processor_func: Callable) -> Dict[str, Any]:
        """Process transactions in batches for better performance"""
        try:
            logger.info(
                f"Starting batch processing of {len(transaction_hashes)} transactions")
            start_time = time.time()

            results = {
                'total_processed': 0,
                'successful': 0,
                'failed': 0,
                'errors': [],
                'processing_time': 0
            }

            # Process in batches
            for i in range(0, len(transaction_hashes), self.batch_size):
                batch = transaction_hashes[i:i + self.batch_size]
                batch_num = (i // self.batch_size) + 1
                total_batches = (len(transaction_hashes) +
                                 self.batch_size - 1) // self.batch_size

                logger.info(
                    f"Processing batch {batch_num}/{total_batches} ({len(batch)} transactions)")

                try:
                    batch_result = processor_func(batch)
                    results['successful'] += len(batch)
                    results['total_processed'] += len(batch)

                except Exception as e:
                    logger.error(
                        f"Error processing batch {batch_num}: {str(e)}")
                    results['failed'] += len(batch)
                    results['errors'].append({
                        'batch': batch_num,
                        'error': str(e),
                        'transaction_count': len(batch)
                    })

            results['processing_time'] = time.time() - start_time
            logger.info(f"Batch processing completed: {results['successful']} successful, "
                        f"{results['failed']} failed in {results['processing_time']:.2f}s")

            return results

        except Exception as e:
            logger.error(f"Error in batch processing: {str(e)}")
            return {
                'total_processed': 0,
                'successful': 0,
                'failed': len(transaction_hashes),
                'errors': [{'error': str(e)}],
                'processing_time': 0
            }

    def process_with_threading(self, items: List[Any], processor_func: Callable,
                               max_workers: int = None) -> Dict[str, Any]:
        """Process items using multiple threads for parallel execution"""
        if max_workers is None:
            max_workers = self.max_workers

        try:
            logger.info(
                f"Starting threaded processing of {len(items)} items with {max_workers} workers")
            start_time = time.time()

            results = {
                'total_processed': 0,
                'successful': 0,
                'failed': 0,
                'errors': [],
                'processing_time': 0
            }

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_item = {
                    executor.submit(processor_func, item): item
                    for item in items
                }

                # Process completed tasks
                for future in as_completed(future_to_item):
                    item = future_to_item[future]
                    try:
                        result = future.result()
                        results['successful'] += 1
                        results['total_processed'] += 1

                    except Exception as e:
                        logger.error(f"Error processing item {item}: {str(e)}")
                        results['failed'] += 1
                        results['errors'].append({
                            'item': str(item),
                            'error': str(e)
                        })

            results['processing_time'] = time.time() - start_time
            logger.info(f"Threaded processing completed: {results['successful']} successful, "
                        f"{results['failed']} failed in {results['processing_time']:.2f}s")

            return results

        except Exception as e:
            logger.error(f"Error in threaded processing: {str(e)}")
            return {
                'total_processed': 0,
                'successful': 0,
                'failed': len(items),
                'errors': [{'error': str(e)}],
                'processing_time': 0
            }

    def _process_batch(self, batch: List[str]) -> bool:
        """Process a single batch of transactions"""
        query = """
        UNWIND $batch as tx_hash
        MATCH (t:Transaction {tx_hash: tx_hash})
        SET t.processed = true, t.processed_at = datetime()
        """

        with self.driver.session() as session:
            session.run(query, batch=batch)

        return True


class PerformanceMonitor:
    """Monitors and optimizes system performance"""

    def __init__(self):
        self.metrics = {}
        self.start_times = {}

    def start_timer(self, operation: str):
        """Start timing an operation"""
        self.start_times[operation] = time.time()

    def end_timer(self, operation: str) -> float:
        """End timing an operation and return duration"""
        if operation in self.start_times:
            duration = time.time() - self.start_times[operation]
            if operation not in self.metrics:
                self.metrics[operation] = []
            self.metrics[operation].append(duration)
            del self.start_times[operation]
            return duration
        return 0.0

    def get_average_time(self, operation: str) -> float:
        """Get average time for an operation"""
        if operation in self.metrics and self.metrics[operation]:
            return sum(self.metrics[operation]) / len(self.metrics[operation])
        return 0.0

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        summary = {}
        for operation, times in self.metrics.items():
            if times:
                summary[operation] = {
                    'count': len(times),
                    'average_time': sum(times) / len(times),
                    'min_time': min(times),
                    'max_time': max(times),
                    'total_time': sum(times)
                }
        return summary

    def reset_metrics(self):
        """Reset all performance metrics"""
        self.metrics.clear()
        self.start_times.clear()


class CacheManager:
    """Simple in-memory cache for frequently accessed data"""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache = {}
        self.access_times = {}

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if key in self.cache:
            # Check if expired
            if time.time() - self.access_times[key] > self.ttl_seconds:
                del self.cache[key]
                del self.access_times[key]
                return None

            # Update access time
            self.access_times[key] = time.time()
            return self.cache[key]
        return None

    def set(self, key: str, value: Any):
        """Set value in cache"""
        # Check if cache is full
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            oldest_key = min(self.access_times.keys(),
                             key=lambda k: self.access_times[k])
            del self.cache[oldest_key]
            del self.access_times[oldest_key]

        self.cache[key] = value
        self.access_times[key] = time.time()

    def clear(self):
        """Clear all cached data"""
        self.cache.clear()
        self.access_times.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'ttl_seconds': self.ttl_seconds,
            'utilization': len(self.cache) / self.max_size
        }


class DataValidator:
    """Validates data integrity and format"""

    @staticmethod
    def validate_bitcoin_address(address: str) -> bool:
        """Validate Bitcoin address format"""
        if not address:
            return False

        # Basic Bitcoin address validation
        if len(address) < 26 or len(address) > 35:
            return False

        # Check if starts with common prefixes
        valid_prefixes = ['1', '3', 'bc1']
        if not any(address.startswith(prefix) for prefix in valid_prefixes):
            return False

        return True

    @staticmethod
    def validate_transaction_hash(tx_hash: str) -> bool:
        """Validate transaction hash format"""
        if not tx_hash:
            return False

        # Bitcoin transaction hash is 64 characters hex
        if len(tx_hash) != 64:
            return False

        # Check if it's valid hex
        try:
            int(tx_hash, 16)
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_timestamp(timestamp) -> bool:
        """Validate timestamp format"""
        if not timestamp:
            return False

        try:
            if isinstance(timestamp, str):
                datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            elif isinstance(timestamp, (int, float)):
                datetime.fromtimestamp(timestamp)
            else:
                return False
            return True
        except (ValueError, OSError):
            return False

    @staticmethod
    def validate_numeric_value(value, min_value: float = 0) -> bool:
        """Validate numeric value"""
        try:
            num_value = float(value)
            return num_value >= min_value
        except (ValueError, TypeError):
            return False


class ConfigManager:
    """Manages configuration and environment variables"""

    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = config_file
        self.config = {}
        self.load_config()

    def load_config(self):
        """Load configuration from file"""
        try:
            import yaml
            with open(self.config_file, 'r') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {self.config_file}")
        except Exception as e:
            logger.warning(f"Error loading config: {str(e)}")
            self.config = self._get_default_config()

    def get(self, key: str, default=None):
        """Get configuration value"""
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value):
        """Set configuration value"""
        keys = key.split('.')
        config = self.config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save_config(self):
        """Save configuration to file"""
        try:
            import yaml
            with open(self.config_file, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
            logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Error saving config: {str(e)}")

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            'neo4j': {
                'uri': 'bolt://localhost:7687',
                'username': 'neo4j',
                'password': 'password'
            },
            'blockcypher': {
                'api_key': 'your_api_key_here',
                'timeout': 30
            },
            'analysis': {
                'time_window_hours': 24,
                'min_transactions': 5,
                'volume_threshold': 1000000
            },
            'performance': {
                'batch_size': 1000,
                'max_workers': 4,
                'cache_size': 1000,
                'cache_ttl': 3600
            }
        }


class LogManager:
    """Manages logging configuration and rotation"""

    def __init__(self, log_file: str = "logs/chainbreak.log", max_size_mb: int = 100,
                 backup_count: int = 5):
        self.log_file = log_file
        self.max_size_mb = max_size_mb
        self.backup_count = backup_count
        self.setup_logging()

    def setup_logging(self):
        """Setup logging with rotation"""
        try:
            from logging.handlers import RotatingFileHandler

            # Create formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

            # Create rotating file handler
            file_handler = RotatingFileHandler(
                self.log_file,
                maxBytes=self.max_size_mb * 1024 * 1024,
                backupCount=self.backup_count
            )
            file_handler.setFormatter(formatter)

            # Create console handler
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)

            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)
            if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
                root_logger.addHandler(file_handler)
            if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
                root_logger.addHandler(console_handler)

            logger.info("Logging setup completed")

        except Exception as e:
            print(f"Error setting up logging: {str(e)}")

    def cleanup_old_logs(self):
        """Clean up old log files"""
        import os
        import glob

        try:
            log_dir = os.path.dirname(self.log_file)
            if not log_dir:
                log_dir = "."

            # Find old log files
            pattern = os.path.join(
                log_dir, f"{os.path.basename(self.log_file)}.*")
            old_logs = glob.glob(pattern)

            # Sort by modification time
            old_logs.sort(key=lambda x: os.path.getmtime(x), reverse=True)

            # Remove excess logs
            for old_log in old_logs[self.backup_count:]:
                try:
                    os.remove(old_log)
                    logger.info(f"Removed old log file: {old_log}")
                except Exception as e:
                    logger.warning(
                        f"Error removing old log {old_log}: {str(e)}")

        except Exception as e:
            logger.error(f"Error cleaning up old logs: {str(e)}")


__all__ = [
    'BatchProcessor',
    'PerformanceMonitor',
    'CacheManager',
    'DataValidator',
    'ConfigManager',
    'LogManager',
]
