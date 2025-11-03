# context_manager.py
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from models.a2a import A2AMessage

class ContextManager:
    """Manager for handling conversation contexts and persistence"""
    def __init__(self, storage_dir="./contexts"):
        self.storage_dir = storage_dir
        self.contexts = {}
        self.max_context_age = timedelta(hours=24)  # Default expiration time
        
        # Create storage directory if it doesn't exist
        if not os.path.exists(storage_dir):
            os.makedirs(storage_dir)
        
        # Load existing contexts from disk
        self._load_contexts()
    
    def _load_contexts(self):
        """Load contexts from disk storage"""
        try:
            for filename in os.listdir(self.storage_dir):
                if filename.endswith(".json"):
                    context_id = filename[:-5]  # Remove .json extension
                    file_path = os.path.join(self.storage_dir, filename)
                    
                    try:
                        with open(file_path, "r") as file:
                            context_data = json.load(file)
                            
                            # Convert timestamps back to datetime
                            if "last_updated" in context_data:
                                context_data["last_updated"] = datetime.fromisoformat(context_data["last_updated"])
                            
                            # Reconstruct history objects if needed
                            if "history" in context_data and isinstance(context_data["history"], list):
                                # Leave history as is - will be converted when needed
                                pass
                                
                            self.contexts[context_id] = context_data
                    except Exception as e:
                        print(f"Error loading context {context_id}: {str(e)}")
        
        except Exception as e:
            print(f"Error loading contexts: {str(e)}")
    
    def save_context(self, context_id: str):
        """Save a context to disk"""
        if context_id in self.contexts:
            try:
                context_data = self.contexts[context_id].copy()
                
                # Convert datetime to string for JSON serialization
                if "last_updated" in context_data and isinstance(context_data["last_updated"], datetime):
                    context_data["last_updated"] = context_data["last_updated"].isoformat()
                
                # Convert history objects if needed
                if "history" in context_data and isinstance(context_data["history"], list):
                    serializable_history = []
                    for msg in context_data["history"]:
                        if hasattr(msg, "model_dump"):
                            serializable_history.append(msg.model_dump())
                        else:
                            serializable_history.append(msg)
                    context_data["history"] = serializable_history
                
                # Save to file
                file_path = os.path.join(self.storage_dir, f"{context_id}.json")
                with open(file_path, "w") as file:
                    json.dump(context_data, file, indent=2)
                    
            except Exception as e:
                print(f"Error saving context {context_id}: {str(e)}")
    
    def get_context(self, context_id: str) -> Dict[str, Any]:
        """Get a context by ID, initializing it if it doesn't exist"""
        # Clean expired contexts first
        self._clean_expired_contexts()
        
        # Initialize if not exists
        if context_id not in self.contexts:
            self.contexts[context_id] = {
                "history": [],
                "last_updated": datetime.now(),
                "metadata": {}
            }
        else:
            # Update the last access time
            self.contexts[context_id]["last_updated"] = datetime.now()
            
        return self.contexts[context_id]
    
    def add_message(self, context_id: str, message: A2AMessage):
        """Add a message to a context's history"""
        context = self.get_context(context_id)
        
        # Add the message to history
        if "history" not in context:
            context["history"] = []
        
        context["history"].append(message)
        context["last_updated"] = datetime.now()
        
        # Save after update
        self.save_context(context_id)
        
        return context
    
    def get_history(self, context_id: str) -> List[Dict[str, Any]]:
        """Get the message history for a context"""
        context = self.get_context(context_id)
        return context.get("history", [])
    
    def clear_context(self, context_id: str) -> bool:
        """Clear a context's history"""
        if context_id in self.contexts:
            self.contexts[context_id]["history"] = []
            self.contexts[context_id]["last_updated"] = datetime.now()
            self.save_context(context_id)
            return True
        return False
    
    def delete_context(self, context_id: str) -> bool:
        """Delete a context completely"""
        if context_id in self.contexts:
            del self.contexts[context_id]
            
            # Remove the file if it exists
            file_path = os.path.join(self.storage_dir, f"{context_id}.json")
            if os.path.exists(file_path):
                os.remove(file_path)
                
            return True
        return False
    
    def _clean_expired_contexts(self):
        """Remove expired contexts"""
        now = datetime.now()
        expired_contexts = []
        
        for context_id, context in self.contexts.items():
            last_updated = context.get("last_updated")
            if isinstance(last_updated, datetime) and (now - last_updated) > self.max_context_age:
                expired_contexts.append(context_id)
        
        for context_id in expired_contexts:
            self.delete_context(context_id)
