# response_generator.py
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import re
import random
from models.a2a import MessagePart

class ResponseGenerator:
    """Generates structured responses for the Telex agent"""
    
    @staticmethod
    def generate_response(query: str, history: List[Dict[str, Any]] = None) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Generate a text response and optional file attachment based on the query.
        
        Args:
            query: The user query text
            history: Conversation history
            
        Returns:
            Tuple of (response text, file data or None)
        """
        history = history or []
        
        # Simple keyword-based response generation
        if not query:
            return "Hello! I'm a Telex AI agent. How can I assist you today?", None
            
        query_lower = query.lower()
        
        # Check for greeting
        if any(greeting in query_lower for greeting in ["hello", "hi", "hey", "greetings"]):
            greetings = [
                "Hello there! I'm your Telex AI assistant. How can I help you today?",
                "Hi! Nice to meet you. I'm a Telex agent built with A2A protocol. What can I do for you?",
                "Hey! I'm here to assist you. What would you like to know?"
            ]
            return random.choice(greetings), None
            
        # Check for help request
        if "help" in query_lower or "what can you do" in query_lower:
            return "I'm a Telex AI agent that can assist you with various tasks. I can have conversations, answer questions, and provide information on different topics.", None
            
        # Check for identity questions
        if "who are you" in query_lower or "what are you" in query_lower:
            return "I'm a Telex AI agent built with the A2A (Agent-to-Agent) protocol. I'm designed to have conversations and assist with various tasks.", None
            
        # Check for thanks
        if "thank" in query_lower:
            thanks_responses = [
                "You're welcome! Feel free to ask if you need anything else.",
                "My pleasure! I'm here to help.",
                "Glad to be of assistance!"
            ]
            return random.choice(thanks_responses), None
            
        # Check for goodbye
        if "bye" in query_lower or "goodbye" in query_lower:
            goodbye_responses = [
                "Goodbye! Feel free to return whenever you need assistance.",
                "See you later! Have a great day.",
                "Until next time! Take care."
            ]
            return random.choice(goodbye_responses), None
            
        # Check for image/file request
        file_data = None
        if "image" in query_lower or "picture" in query_lower or "file" in query_lower:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            
            if "cat" in query_lower:
                filename = f"cat_image_{timestamp}.txt"
                content = "This is a placeholder for a cat image. In a real implementation, this would be an actual cat image."
                file_data = {
                    "filename": filename,
                    "content": content,
                    "content_type": "text/plain"
                }
                return "Here's a cat image placeholder for you. In a real implementation, this would be an actual image of a cat.", file_data
                
            elif "dog" in query_lower:
                filename = f"dog_image_{timestamp}.txt"
                content = "This is a placeholder for a dog image. In a real implementation, this would be an actual dog image."
                file_data = {
                    "filename": filename,
                    "content": content,
                    "content_type": "text/plain"
                }
                return "Here's a dog image placeholder for you. In a real implementation, this would be an actual image of a dog.", file_data
                
            else:
                filename = f"telex_response_{timestamp}.txt"
                content = "This is a placeholder for an image file that would be generated based on the query."
                file_data = {
                    "filename": filename,
                    "content": content,
                    "content_type": "text/plain"
                }
                return "Here's a placeholder for the image you requested. In a real implementation, this would be an actual image.", file_data
            
        # Default response with context awareness
        if len(history) > 2:
            return f"Thank you for your message: '{query}'. We're having a good conversation! How can I assist you further?", None
        else:
            return f"I received your message: '{query}'. I'm a Telex AI agent built with the A2A protocol. How can I help you today?", None
    
    @staticmethod
    async def create_message_parts(agent, response_text: str, file_data: Optional[Dict[str, Any]] = None) -> List[MessagePart]:
        """
        Create message parts from response text and optional file data.
        
        Args:
            agent: The agent instance (for file uploads)
            response_text: The text response
            file_data: Optional file data dictionary
            
        Returns:
            List of MessagePart objects
        """
        parts = []
        
        # Add text part
        parts.append(MessagePart(
            kind="text",
            text=response_text
        ))
        
        # Add file part if available
        if file_data:
            try:
                upload_result = await agent.upload_file(
                    file_data=file_data["content"],
                    filename=file_data["filename"],
                    content_type=file_data["content_type"]
                )
                
                if upload_result.get("success"):
                    parts.append(MessagePart(
                        kind="file",
                        file={
                            "name": file_data["filename"],
                            "mimeType": file_data["content_type"],
                            "bytes": None,
                            "uri": upload_result.get("url")
                        }
                    ))
            except Exception as e:
                print(f"Error uploading file: {str(e)}")
        
        return parts
