# webhook_handler.py
import os
import httpx
from dotenv import load_dotenv
from typing import Dict, Any, Optional

load_dotenv()

async def send_webhook_response(message: Dict[str, Any], webhook_url: Optional[str] = None, webhook_token: Optional[str] = None):
    """
    Send a response to a webhook URL.
    
    Args:
        message: The message to send
        webhook_url: The URL to send the webhook to (overrides env variable)
        webhook_token: The token for webhook authentication (overrides env variable)
    
    Returns:
        Dict with response status
    """
    url = webhook_url or os.getenv("WEBHOOK_URL")
    token = webhook_token or os.getenv("WEBHOOK_TOKEN")
    
    if not url:
        return {"error": "No webhook URL provided"}
    
    try:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=message,
                headers=headers,
                timeout=10.0
            )
            
            return {
                "success": response.status_code < 400,
                "status_code": response.status_code,
                "response": response.text
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
