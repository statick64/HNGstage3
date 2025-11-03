# telex_agent.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os
import json
import httpx
import uuid
import asyncio
import boto3
import botocore
import io
from datetime import datetime
from typing import List, Dict, Any, Optional

from webhook_handler import send_webhook_response
from context_manager import ContextManager
from response_generator import ResponseGenerator
from logger import TelexLogger

from models.a2a import JSONRPCRequest, JSONRPCResponse, TaskResult, TaskStatus, Artifact, MessagePart, A2AMessage

load_dotenv()

class TelexAgent:
    """Telex Agent for handling natural language conversations using the A2A protocol"""
    def __init__(self, aws_config=None, deployment_type=None, contexts_dir="./contexts", logs_dir="./logs"):
        self.aws_config = aws_config
        self.deployment_type = deployment_type or os.getenv("DEPLOYMENT_TYPE", "direct")
        self.http_client = httpx.AsyncClient()
        self.context_manager = ContextManager(storage_dir=contexts_dir)
        self.logger = TelexLogger(log_dir=logs_dir)
        
        # Initialize AWS S3 client if config is provided
        self.s3_client = None
        self.bucket_name = None
        if aws_config:
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=aws_config.get('access_key_id'),
                    aws_secret_access_key=aws_config.get('secret_access_key'),
                    region_name=aws_config.get('region_name', 'us-east-1')
                )
                self.bucket_name = aws_config.get('bucket_name')
                print(f"AWS S3 client initialized for bucket: {self.bucket_name}")
            except Exception as e:
                print(f"Error initializing AWS S3 client: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.http_client.aclose()
        
    async def upload_file(self, file_data, filename, content_type):
        """Upload a file to AWS S3 storage"""
        if not self.s3_client or not self.bucket_name:
            return {"error": "AWS S3 client not configured"}
            
        try:
            # Convert file data to bytes if needed
            if isinstance(file_data, str):
                file_data = file_data.encode('utf-8')
                
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=filename,
                Body=file_data,
                ContentType=content_type
            )
            
            # Generate a presigned URL for the uploaded file (valid for 7 days)
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': filename
                },
                ExpiresIn=60*60*24*7  # 7 days in seconds
            )
            
            return {
                "success": True,
                "filename": filename,
                "url": url
            }
            
        except botocore.exceptions.ClientError as e:
            print(f"Error uploading file to AWS S3: {str(e)}")
            return {"error": str(e)}
    
    async def get_file_url(self, filename):
        """Get a presigned URL for accessing a file"""
        if not self.s3_client or not self.bucket_name:
            return {"error": "AWS S3 client not configured"}
            
        try:
            # Generate a URL for the file (valid for 1 day)
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': filename
                },
                ExpiresIn=60*60*24  # 1 day in seconds
            )
            
            return {
                "success": True,
                "filename": filename,
                "url": url
            }
            
        except botocore.exceptions.ClientError as e:
            print(f"Error getting file URL from AWS S3: {str(e)}")
            return {"error": str(e)}
    
    async def process_messages(self, messages, context_id=None, task_id=None, config=None):
        """Process messages from the user and return a task result"""
        # Generate IDs if not provided
        task_id = task_id or str(uuid4())
        context_id = context_id or str(uuid4())
        
        # Get the context, which will be initialized if it doesn't exist
        context = self.context_manager.get_context(context_id)
        
        # Get the last user message
        user_message = messages[-1]  # Assume the last message is from the user
        
        # Store user message in history
        self.context_manager.add_message(context_id, user_message)
        
        try:
            # Process the user's message
            result = await self._process_query(
                query=user_message.parts[0].text if user_message.parts else "",  # Get the text from the message
                context_id=context_id,
                task_id=task_id
            )
            
            # Check if webhook response is required and config has webhook URL
            webhook_config = None
            if config and hasattr(config, "pushNotificationConfig") and config.pushNotificationConfig:
                webhook_config = config.pushNotificationConfig
            
            if self.deployment_type == "webhook" and webhook_config:
                # Send webhook response
                webhook_response = await send_webhook_response(
                    message=result.model_dump(),
                    webhook_url=webhook_config.url,
                    webhook_token=webhook_config.token
                )
                print(f"Webhook response: {webhook_response}")
            
            return result
            
        except Exception as e:
            print(f"Error processing message: {str(e)}")
            return self._create_error_result(task_id, context_id, str(e))

    async def _process_query(self, query, context_id, task_id):
        """Process a user query and return appropriate response"""
        try:
            print(f"Processing query: {query}")
            
            # Get conversation history for context
            history = self.context_manager.get_history(context_id)
            
            # Use the response generator to create a response
            response_text, file_data = ResponseGenerator.generate_response(query, history)
            
            # Create message parts from response text and file data
            response_parts = await ResponseGenerator.create_message_parts(self, response_text, file_data)
            
            # Create a response message with all parts
            response_message = A2AMessage(
                role="agent",
                parts=response_parts
            )
            
            # Add the response to the history
            self.context_manager.add_message(context_id, response_message)
            
            # Create a task status
            status = TaskStatus(
                state="completed",
                message=response_message
            )
            
            # Create and return the task result
            result = TaskResult(
                id=task_id,
                contextId=context_id,
                status=status,
                history=self.context_manager.get_history(context_id)
            )
            
            return result
            
        except Exception as e:
            print(f"Error processing query: {str(e)}")
            return self._create_error_result(task_id, context_id, str(e))

    def _create_error_result(self, task_id, context_id, error_message):
        """Create an error task result"""
        error_message = A2AMessage(
            role="agent",
            parts=[MessagePart(
                kind="text",
                text=f"Error: {error_message}"
            )]
        )
        
        status = TaskStatus(
            state="failed",
            message=error_message
        )
        
        return TaskResult(
            id=task_id,
            contextId=context_id,
            status=status
        )

# Initialize Telex agent
telex_agent = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global telex_agent

    # Startup: Initialize the Telex agent
    telex_agent = TelexAgent(
        aws_config={
            "access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
            "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "region_name": os.getenv("AWS_REGION_NAME", "us-east-1"),
            "bucket_name": os.getenv("AWS_BUCKET_NAME")
        } if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY") and os.getenv("AWS_BUCKET_NAME") else None,
        deployment_type=os.getenv("DEPLOYMENT_TYPE", "direct")
    )

    yield

    # Shutdown: Cleanup
    if telex_agent:
        await telex_agent.cleanup()

app = FastAPI(
    title="Telex Agent A2A",
    description="An AI agent with A2A protocol support for Telex",
    version="1.0.0",
    lifespan=lifespan
)

@app.post("/a2a/telex")
async def a2a_endpoint(request: Request):
    """Main A2A endpoint for Telex agent"""
    try:
        # Parse request body
        body = await request.json()
        request_id = body.get("id", "unknown")

        # Log the incoming request
        telex_agent.logger.log_info(f"Received request: {request_id}")

        # Validate JSON-RPC request
        if body.get("jsonrpc") != "2.0" or "id" not in body:
            error_msg = "Invalid Request: jsonrpc must be '2.0' and id is required"
            telex_agent.logger.log_error(request_id, error_msg)
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32600,
                        "message": error_msg
                    }
                }
            )

        rpc_request = JSONRPCRequest(**body)

        # Extract messages
        messages = []
        context_id = None
        task_id = None
        config = None
        user_id = None

        if rpc_request.method == "message/send":
            messages = [rpc_request.params.message]
            config = rpc_request.params.configuration
            
            # Try to extract metadata
            if hasattr(messages[0], "metadata") and messages[0].metadata:
                user_id = messages[0].metadata.get("telex_user_id")
                if not context_id:
                    context_id = messages[0].metadata.get("telex_channel_id")
            
        elif rpc_request.method == "execute":
            messages = rpc_request.params.messages
            context_id = rpc_request.params.contextId
            task_id = rpc_request.params.taskId
        
        # Log request details
        telex_agent.logger.log_request(
            request_id=rpc_request.id,
            method=rpc_request.method,
            user_id=user_id,
            context_id=context_id
        )

        # Process with Telex agent
        result = await telex_agent.process_messages(
            messages=messages,
            context_id=context_id,
            task_id=task_id,
            config=config
        )
        
        # Log response
        if result:
            telex_agent.logger.log_response(
                request_id=rpc_request.id,
                task_id=result.id,
                state=result.status.state if result.status else "unknown",
                response_length=len(result.status.message.parts) if result.status and result.status.message else 0
            )

        # Build response
        response = JSONRPCResponse(
            id=rpc_request.id,
            result=result
        )

        return response.model_dump()

    except Exception as e:
        # Get request ID if available
        request_id = body.get("id") if "body" in locals() and isinstance(body, dict) else "unknown"
        
        # Log the error
        telex_agent.logger.log_error(request_id, f"Internal error: {str(e)}")
        
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": {"details": str(e)}
                }
            }
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "agent": "telex"}

@app.get("/contexts/{context_id}")
async def get_context(context_id: str):
    """Get a specific context"""
    try:
        context = telex_agent.context_manager.get_context(context_id)
        return {"context_id": context_id, "context": context}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Context not found: {str(e)}")

@app.delete("/contexts/{context_id}")
async def delete_context(context_id: str):
    """Delete a specific context"""
    success = telex_agent.context_manager.delete_context(context_id)
    if success:
        return {"status": "deleted", "context_id": context_id}
    else:
        raise HTTPException(status_code=404, detail=f"Context not found")

@app.get("/contexts")
async def list_contexts():
    """List all available contexts"""
    context_ids = list(telex_agent.context_manager.contexts.keys())
    return {"contexts": context_ids}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5001))
    uvicorn.run(app, host="0.0.0.0", port=port)
