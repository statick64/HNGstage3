# main.py
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

from models.a2a import JSONRPCRequest, JSONRPCResponse, TaskResult, TaskStatus, Artifact, MessagePart, A2AMessage

load_dotenv()

class NBAAgent:
    """NBA Agent for getting information about NBA games, teams, and players"""
    def __init__(self, api_key=None, aws_config=None):
        self.api_key = api_key
        self.aws_config = aws_config
        self.base_url = "https://api-nba-v1.p.rapidapi.com"
        self.headers = {
            "X-RapidAPI-Key": self.api_key or os.getenv("RAPIDAPI_KEY", ""),
            "X-RapidAPI-Host": "api-nba-v1.p.rapidapi.com"
        }
        self.http_client = httpx.AsyncClient()
        self.contexts = {}
        
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
            print(f"Error generating URL for file: {str(e)}")
            return {"error": str(e)}

    async def get_games(self, date=None, team=None, season=None, league=None):
        """Get NBA games information"""
        params = {}
        endpoint = "/games"
        
        if date:
            params["date"] = date
        if team:
            params["team"] = team
        if season:
            params["season"] = season
        if league:
            params["league"] = league

        try:
            response = await self.http_client.get(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_teams(self, league=None, season=None, team=None):
        """Get NBA teams information"""
        params = {}
        endpoint = "/teams"
        
        if league:
            params["league"] = league
        if season:
            params["season"] = season
        if team:
            params["id"] = team

        try:
            response = await self.http_client.get(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_players(self, team=None, name=None):
        """Get NBA players information"""
        params = {}
        endpoint = "/players"
        
        if team:
            params["team"] = team
        if name:
            params["search"] = name

        try:
            response = await self.http_client.get(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_standings(self, league=None, season=None, team=None):
        """Get NBA standings information"""
        params = {}
        endpoint = "/standings"
        
        if league:
            params["league"] = league
        if season:
            params["season"] = season
        if team:
            params["team"] = team

        try:
            response = await self.http_client.get(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_statistics(self, game_id=None, team=None, player=None):
        """Get NBA statistics information"""
        params = {}
        endpoint = "/statistics"
        
        if game_id:
            params["game"] = game_id
        if team:
            params["team"] = team
        if player:
            params["player"] = player

        try:
            response = await self.http_client.get(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def process_messages(self, messages, context_id=None, task_id=None, config=None):
        """Process messages from the user and return a task result"""
        # Create context and task IDs if not provided
        if not context_id:
            context_id = str(uuid.uuid4())
        if not task_id:
            task_id = str(uuid.uuid4())

        # Store context if needed
        if context_id not in self.contexts:
            self.contexts[context_id] = {
                "history": []
            }

        # Process the last user message
        user_message = None
        for message in messages:
            if message.role == "user":
                user_message = message
                self.contexts[context_id]["history"].append(message)

        if not user_message:
            return self._create_error_result(
                task_id, context_id, "No user message provided"
            )

        # Extract the user's text query
        query_text = ""
        for part in user_message.parts:
            if part.kind == "text" and part.text:
                query_text += part.text + " "
        query_text = query_text.strip()

        # Process the query
        result = await self._process_query(query_text, context_id, task_id)
        
        # Return the task result
        return result

    async def _process_query(self, query, context_id, task_id):
        """Process a user query and return appropriate NBA data"""
        # Simple keyword-based query processing
        response_text = ""
        
        try:
            if any(word in query.lower() for word in ["games", "match", "schedule"]):
                # Default to current season if not specified
                season = "2023-2024" if "2023" in query or "2024" in query else "2023-2024"
                games_data = await self.get_games(season=season)
                response_text = f"Here are the NBA games for the {season} season:\n\n"
                
                if "error" in games_data:
                    response_text = f"Sorry, I couldn't retrieve games data: {games_data['error']}"
                else:
                    for i, game in enumerate(games_data.get("response", [])[:5]):
                        home_team = game.get("teams", {}).get("home", {}).get("name", "Unknown")
                        away_team = game.get("teams", {}).get("visitors", {}).get("name", "Unknown")
                        date = game.get("date", {}).get("start", "Unknown date")
                        response_text += f"{i+1}. {away_team} @ {home_team} - {date}\n"
                    
                    if len(games_data.get("response", [])) > 5:
                        response_text += f"\nShowing 5 of {len(games_data.get('response', []))} games."
            
            elif any(word in query.lower() for word in ["teams", "team", "franchise"]):
                teams_data = await self.get_teams()
                response_text = "Here are the NBA teams:\n\n"
                
                if "error" in teams_data:
                    response_text = f"Sorry, I couldn't retrieve team data: {teams_data['error']}"
                else:
                    for i, team in enumerate(teams_data.get("response", [])[:15]):
                        name = team.get("name", "Unknown")
                        nickname = team.get("nickname", "")
                        city = team.get("city", "")
                        response_text += f"{i+1}. {city} {name} ({nickname})\n"
                    
                    if len(teams_data.get("response", [])) > 15:
                        response_text += f"\nShowing 15 of {len(teams_data.get('response', []))} teams."
            
            elif any(word in query.lower() for word in ["players", "player", "roster"]):
                # Extract team or player name if present
                player_name = None
                team_id = None
                
                # Very basic extraction - in production would use NLP
                if "named" in query.lower() or "name" in query.lower() or "player" in query.lower():
                    # Extract player name (simple approach)
                    parts = query.split("named ", 1) if "named " in query else query.split("player ", 1)
                    if len(parts) > 1:
                        player_name = parts[1].split("?")[0].strip()
                
                players_data = await self.get_players(team=team_id, name=player_name)
                
                if player_name:
                    response_text = f"Here are players matching '{player_name}':\n\n"
                else:
                    response_text = "Here are some NBA players:\n\n"
                
                if "error" in players_data:
                    response_text = f"Sorry, I couldn't retrieve player data: {players_data['error']}"
                else:
                    for i, player in enumerate(players_data.get("response", [])[:10]):
                        name = f"{player.get('firstname', '')} {player.get('lastname', '')}"
                        team = player.get("team", {}).get("name", "Unknown team")
                        position = player.get("leagues", {}).get("standard", {}).get("pos", "")
                        response_text += f"{i+1}. {name} - {position} ({team})\n"
                    
                    if len(players_data.get("response", [])) > 10:
                        response_text += f"\nShowing 10 of {len(players_data.get('response', []))} players."
            
            elif any(word in query.lower() for word in ["standings", "ranking", "leaderboard"]):
                season = "2023-2024" if "2023" in query or "2024" in query else "2023-2024"
                standings_data = await self.get_standings(season=season)
                response_text = f"Here are the NBA standings for the {season} season:\n\n"
                
                if "error" in standings_data:
                    response_text = f"Sorry, I couldn't retrieve standings data: {standings_data['error']}"
                else:
                    for i, standing in enumerate(standings_data.get("response", [])[:15]):
                        team = standing.get("team", {}).get("name", "Unknown")
                        conference = standing.get("conference", {}).get("name", "")
                        rank = standing.get("conference", {}).get("rank", "")
                        wins = standing.get("games", {}).get("win", {}).get("total", 0)
                        losses = standing.get("games", {}).get("loss", {}).get("total", 0)
                        response_text += f"{i+1}. {rank}. {team} ({conference}): {wins}-{losses}\n"
                    
                    if len(standings_data.get("response", [])) > 15:
                        response_text += f"\nShowing 15 of {len(standings_data.get('response', []))} teams."
            
            elif any(word in query.lower() for word in ["stats", "statistics"]):
                stats_data = await self.get_statistics()
                response_text = "Here are some NBA statistics:\n\n"
                
                if "error" in stats_data:
                    response_text = f"Sorry, I couldn't retrieve statistics data: {stats_data['error']}"
                else:
                    # Statistics processing would depend on the actual structure
                    # This is a placeholder for the response format
                    response_text = "The NBA statistics API provides detailed game, player and team statistics. Please specify what specific statistics you're interested in (e.g., player stats, team stats, game stats)."
            
            else:
                response_text = "I'm an NBA Agent that can provide information about NBA games, teams, players, standings, and statistics. What would you like to know about the NBA?"
        
        except Exception as e:
            response_text = f"I encountered an error while processing your request: {str(e)}"
        
        # Create agent response message
        agent_message = A2AMessage(
            role="agent",
            parts=[
                MessagePart(
                    kind="text",
                    text=response_text
                )
            ]
        )
        
        # Add to history
        self.contexts[context_id]["history"].append(agent_message)
        
        # Create task status
        status = TaskStatus(
            state="completed",
            message=agent_message
        )
        
        # Create result
        result = TaskResult(
            id=task_id,
            contextId=context_id,
            status=status,
            history=self.contexts[context_id]["history"]
        )
        
        return result

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

# Initialize NBA agent
nba_agent = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global nba_agent

    # Startup: Initialize the NBA agent
    nba_agent = NBAAgent(
        api_key=os.getenv("RAPIDAPI_KEY"),
        aws_config={
            "access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
            "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "region_name": os.getenv("AWS_REGION_NAME", "us-east-1"),
            "bucket_name": os.getenv("AWS_BUCKET_NAME")
        } if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY") and os.getenv("AWS_BUCKET_NAME") else None
    )

    yield

    # Shutdown: Cleanup
    if nba_agent:
        await nba_agent.cleanup()

app = FastAPI(
    title="NBA Agent A2A",
    description="An NBA information agent with A2A protocol support",
    version="1.0.0",
    lifespan=lifespan
)

@app.post("/a2a/nba")
async def a2a_endpoint(request: Request):
    """Main A2A endpoint for NBA agent"""
    try:
        # Parse request body
        body = await request.json()

        # Validate JSON-RPC request
        if body.get("jsonrpc") != "2.0" or "id" not in body:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "error": {
                        "code": -32600,
                        "message": "Invalid Request: jsonrpc must be '2.0' and id is required"
                    }
                }
            )

        rpc_request = JSONRPCRequest(**body)

        # Extract messages
        messages = []
        context_id = None
        task_id = None
        config = None

        if rpc_request.method == "message/send":
            messages = [rpc_request.params.message]
            config = rpc_request.params.configuration
        elif rpc_request.method == "execute":
            messages = rpc_request.params.messages
            context_id = rpc_request.params.contextId
            task_id = rpc_request.params.taskId

        # Process with NBA agent
        result = await nba_agent.process_messages(
            messages=messages,
            context_id=context_id,
            task_id=task_id,
            config=config
        )

        # Build response
        response = JSONRPCResponse(
            id=rpc_request.id,
            result=result
        )

        return response.model_dump()

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": body.get("id") if "body" in locals() else None,
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
    return {"status": "healthy", "agent": "nba"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5001))
    uvicorn.run(app, host="0.0.0.0", port=port)
