"""
Custom JSON Encoder for handling numpy and other non-serializable types
"""
import json
import numpy as np
from datetime import datetime, date
from decimal import Decimal


class NumpyEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that handles numpy types, datetime, and other
    Python objects that aren't natively JSON serializable.
    """
    def default(self, obj):
        # Handle numpy integers
        if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
            return int(obj)
        
        # Handle numpy floats
        if isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
            return float(obj)
        
        # Handle numpy arrays
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        
        # Handle numpy booleans
        if isinstance(obj, np.bool_):
            return bool(obj)
        
        # Handle datetime objects
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        
        # Handle Decimal
        if isinstance(obj, Decimal):
            return float(obj)
        
        # Handle sets
        if isinstance(obj, set):
            return list(obj)
        
        # Fallback to default behavior
        return super().default(obj)


def safe_json_dumps(obj, **kwargs):
    """
    Safely serialize an object to JSON, handling numpy and other types.
    
    Args:
        obj: Object to serialize
        **kwargs: Additional arguments to pass to json.dumps
        
    Returns:
        JSON string
    """
    return json.dumps(obj, cls=NumpyEncoder, **kwargs)


def safe_json_response(obj, ensure_ascii=False, **kwargs):
    """
    Create a JSON-safe dictionary for Flask responses.
    Recursively converts numpy types to native Python types.
    
    Args:
        obj: Object to convert
        ensure_ascii: Whether to ensure ASCII encoding
        **kwargs: Additional arguments
        
    Returns:
        JSON-safe object
    """
    if isinstance(obj, dict):
        return {key: safe_json_response(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [safe_json_response(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
        # Handle NaN and infinity
        if np.isnan(obj):
            return 0.0
        elif np.isinf(obj):
            return 0.0 if obj < 0 else  999999.0
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return [safe_json_response(item) for item in obj.tolist()]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, set):
        return [safe_json_response(item) for item in obj]
    else:
        return obj
