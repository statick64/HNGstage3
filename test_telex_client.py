# test_telex_client.py
import httpx
import json
import uuid
import asyncio
import sys
from typing import Dict, Any, List, Optional

async def send_message(
    message: str, 
    endpoint: str = "http://localhost:5001/a2a/telex",
    user_id: Optional[str] = None,
    channel_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send a message to the Telex agent and get the response.
    
    Args:
        message: The message text to send
        endpoint: The URL of the Telex agent endpoint
        user_id: Optional user ID for the request
        channel_id: Optional channel ID for the request
        
    Returns:
        The agent's response
    """
    # Generate IDs if not provided
    user_id = user_id or str(uuid.uuid4())
    channel_id = channel_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    
    # Create the request payload
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": message,
                        "metadata": None
                    }
                ],
                "metadata": {
                    "telex_user_id": user_id,
                    "telex_channel_id": channel_id
                },
                "messageId": message_id,
                "contextId": channel_id,
                "taskId": None
            },
            "configuration": {
                "blocking": True,
                "acceptedOutputModes": ["text/plain", "image/png", "image/svg+xml"],
                "pushNotificationConfig": None
            },
            "metadata": None
        }
    }
    
    # Send the request
    async with httpx.AsyncClient() as client:
        response = await client.post(
            endpoint,
            json=payload,
            timeout=30.0
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            result = response.json()
            return result
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return {"error": f"Request failed with status code {response.status_code}"}

def print_response(response: Dict[str, Any]) -> None:
    """
    Print the response from the Telex agent in a readable format.
    
    Args:
        response: The response from the Telex agent
    """
    if "error" in response:
        print(f"Error: {response['error']}")
        return
    
    if "result" in response and "status" in response["result"] and "message" in response["result"]["status"]:
        message = response["result"]["status"]["message"]
        
        print("\n=== Agent Response ===")
        
        # Print text parts
        for part in message.get("parts", []):
            if part.get("kind") == "text":
                print(part.get("text", ""))
            elif part.get("kind") == "file" and part.get("file", {}).get("uri"):
                print(f"\n[File attached]: {part['file']['name']} - {part['file']['uri']}")
        
        print("=====================\n")
    else:
        print("Response format not recognized:")
        print(json.dumps(response, indent=2))

async def interactive_session() -> None:
    """
    Start an interactive session with the Telex agent.
    """
    print("=== Telex Agent Interactive Client ===")
    print("Type 'exit' or 'quit' to end the session")
    print("=======================================")
    
    user_id = str(uuid.uuid4())
    channel_id = str(uuid.uuid4())
    
    while True:
        # Get user input
        user_input = input("\nYou: ")
        
        # Check if the user wants to exit
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("Goodbye!")
            break
            
        # Send the message to the agent
        try:
            response = await send_message(
                message=user_input,
                user_id=user_id,
                channel_id=channel_id
            )
            
            # Print the response
            print_response(response)
            
        except Exception as e:
            print(f"Error: {str(e)}")

if __name__ == "__main__":
    # Check if endpoint is provided as command line argument
    endpoint = "http://localhost:5001/a2a/telex"
    if len(sys.argv) > 1:
        endpoint = sys.argv[1]
    
    if len(sys.argv) > 2 and sys.argv[2] == "--single":
        # Single message mode
        message = input("Enter your message: ")
        asyncio.run(send_message(message, endpoint))
    else:
        # Interactive session
        asyncio.run(interactive_session())
