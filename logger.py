# logger.py
import logging
import os
from datetime import datetime
from typing import Dict, Any
import json

class TelexLogger:
    """Logger for Telex agent requests and responses"""
    
    def __init__(self, log_dir="./logs"):
        self.log_dir = log_dir
        
        # Create log directory if it doesn't exist
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Set up logger
        self.logger = logging.getLogger("telex_agent")
        self.logger.setLevel(logging.INFO)
        
        # Add file handler
        log_file = os.path.join(log_dir, f"telex_agent_{datetime.now().strftime('%Y%m%d')}.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        
        # Add console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers to logger
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def log_request(self, request_id: str, method: str, user_id: str = None, context_id: str = None):
        """Log an incoming request"""
        self.logger.info(f"Request: {request_id} | Method: {method} | User: {user_id} | Context: {context_id}")
    
    def log_response(self, request_id: str, task_id: str, state: str, response_length: int = 0):
        """Log a response"""
        self.logger.info(f"Response: {request_id} | Task: {task_id} | State: {state} | Length: {response_length}")
    
    def log_error(self, request_id: str, error: str):
        """Log an error"""
        self.logger.error(f"Error: {request_id} | {error}")
    
    def log_info(self, message: str):
        """Log general information"""
        self.logger.info(message)
        
    def log_debug(self, message: str):
        """Log debug information"""
        self.logger.debug(message)
        
    def log_warning(self, message: str):
        """Log warning"""
        self.logger.warning(message)
