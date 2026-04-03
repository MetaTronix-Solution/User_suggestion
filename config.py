"""
Configuration management for the FastAPI
Supports development, testing, and production environments
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration"""
    DEBUG = False
    TESTING = False
    JSON_SORT_KEYS = False
    
    # Database
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', 5432)
    DB_NAME = os.getenv('DB_NAME', 'social_db')
    DB_USER = os.getenv('DB_USER', '')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    
    # API
    API_TIMEOUT = int(os.getenv('API_TIMEOUT', 30))
    MAX_RESULTS = int(os.getenv('MAX_RESULTS', 50))


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DB_NAME = 'social_db_test'


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    
    @staticmethod
    def init_app(app):
        """Production-specific initialization"""
        pass


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Get configuration based on ENVIRONMENT environment variable"""
    env = os.getenv('ENVIRONMENT', 'development')
    return config.get(env, config['default'])
