# Custom Exceptions
class ConfigError(Exception):
    """Exception raised for errors in configuration"""
    pass

class APIError(Exception):
    """Exception raised for API errors"""
    pass

class ValidationError(Exception):
    """Exception raised for validation errors"""
    pass

class TokenError(Exception):
    """Exception raised for token errors"""
    pass