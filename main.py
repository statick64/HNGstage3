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
    """NBA Agent for getting information about NBA games, teams, and players using SportsData.io API"""
    def __init__(self, api_key=None, aws_config=None):
        self.api_key = api_key
        self.aws_config = aws_config
        self.base_url = "https://api.sportsdata.io/v3/nba"
        self.headers = {
            "Ocp-Apim-Subscription-Key": self.api_key or os.getenv("SPORTSDATA_API_KEY", "")
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
        try:
            # SportsData.io uses different endpoints for different types of game data
            # Using the games by date endpoint as default
            if date:
                # Format should be YYYY-MMM-DD (e.g. 2023-NOV-01)
                formatted_date = datetime.strptime(date, '%Y-%m-%d').strftime('%Y-%b-%d')
                endpoint = f"{self.base_url}/scores/json/GamesByDate/{formatted_date}"
            elif team:
                # Get games by team
                season_year = season or "2023"
                endpoint = f"{self.base_url}/scores/json/Games/{season_year}"
            else:
                # Default to current season schedule
                season_year = season or "2023"
                endpoint = f"{self.base_url}/scores/json/Games/{season_year}"
            
            # SportsData.io uses API key as query parameter
            params = {}
            
            response = await self.http_client.get(endpoint, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            # If team was specified, filter the results
            if team and data:
                data = [game for game in data if team.lower() in game.get("HomeTeam", "").lower() or 
                                               team.lower() in game.get("AwayTeam", "").lower()]
            
            return {"response": data}
        except Exception as e:
            print(f"Error getting games data: {str(e)}")
            return {"error": str(e)}

    async def get_teams(self, league=None, season=None, team=None):
        """Get NBA teams information"""
        try:
            # SportsData.io teams endpoint
            endpoint = f"{self.base_url}/scores/json/teams"
            
            response = await self.http_client.get(endpoint, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            # Filter by team name if specified
            if team and data:
                data = [t for t in data if team.lower() in t.get("Name", "").lower() or 
                                           team.lower() in t.get("Key", "").lower()]
            
            return {"response": data}
        except Exception as e:
            print(f"Error getting teams data: {str(e)}")
            return {"error": str(e)}

    async def get_players(self, team=None, name=None):
        """Get NBA players information"""
        try:
            if team:
                # Get players by team
                endpoint = f"{self.base_url}/scores/json/Players/{team}"
            else:
                # Get all active players
                endpoint = f"{self.base_url}/scores/json/Players"
            
            response = await self.http_client.get(endpoint, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            # Filter by player name if specified
            if name and data:
                data = [p for p in data if name.lower() in (p.get("FirstName", "") + " " + p.get("LastName", "")).lower()]
            
            return {"response": data}
        except Exception as e:
            print(f"Error getting players data: {str(e)}")
            return {"error": str(e)}

    async def get_standings(self, league=None, season=None, team=None):
        """Get NBA standings information"""
        try:
            # Get the current season if not specified
            season_year = season or "2023"
            
            # SportsData.io standings endpoint
            endpoint = f"{self.base_url}/scores/json/Standings/{season_year}"
            
            response = await self.http_client.get(endpoint, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            # Filter by team if specified
            if team and data:
                data = [s for s in data if team.lower() in s.get("Name", "").lower() or 
                                           team.lower() in s.get("Key", "").lower()]
            
            return {"response": data}
        except Exception as e:
            print(f"Error getting standings data: {str(e)}")
            return {"error": str(e)}

    async def get_statistics(self, game_id=None, team=None, player=None):
        """Get NBA statistics information"""
        try:
            if game_id:
                # Get box score for a specific game
                endpoint = f"{self.base_url}/stats/json/BoxScore/{game_id}"
            elif player:
                # Get player season stats
                endpoint = f"{self.base_url}/stats/json/PlayerSeasonStatsByPlayer/{player}"
            elif team:
                # Get team season stats
                season_year = "2023"
                endpoint = f"{self.base_url}/stats/json/TeamSeasonStats/{season_year}"
                response = await self.http_client.get(endpoint, headers=self.headers)
                response.raise_for_status()
                all_team_stats = response.json()
                # Filter for the requested team
                data = [ts for ts in all_team_stats if team.lower() in ts.get("Name", "").lower() or 
                                                    team.lower() in ts.get("Team", "").lower()]
                return {"response": data}
            else:
                # Default to league leaders in points
                endpoint = f"{self.base_url}/stats/json/PlayerSeasonStats/2023"
            
            response = await self.http_client.get(endpoint, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            return {"response": data}
        except Exception as e:
            print(f"Error getting statistics data: {str(e)}")
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
                season = "2023" if "2023" in query else "2023"  # SportsData uses just the year
                games_data = await self.get_games(season=season)
                response_text = f"Here are the NBA games for the {season} season:\n\n"
                
                if "error" in games_data:
                    response_text = f"Sorry, I couldn't retrieve games data: {games_data['error']}"
                else:
                    for i, game in enumerate(games_data.get("response", [])[:5]):
                        # Update field names to match SportsData.io response format
                        home_team = game.get("HomeTeam", "Unknown")
                        away_team = game.get("AwayTeam", "Unknown")
                        date = game.get("DateTime", "Unknown date")
                        status = game.get("Status", "")
                        home_score = game.get("HomeTeamScore", "")
                        away_score = game.get("AwayTeamScore", "")
                        
                        if status == "Final":
                            result = f"Final: {away_team} {away_score} - {home_team} {home_score}"
                        else:
                            result = f"{away_team} @ {home_team} - {date}"
                            
                        response_text += f"{i+1}. {result}\n"
                    
                    if len(games_data.get("response", [])) > 5:
                        response_text += f"\nShowing 5 of {len(games_data.get('response', []))} games."
            
            elif any(word in query.lower() for word in ["teams", "team", "franchise"]):
                teams_data = await self.get_teams()
                response_text = "Here are the NBA teams:\n\n"
                
                if "error" in teams_data:
                    response_text = f"Sorry, I couldn't retrieve team data: {teams_data['error']}"
                else:
                    for i, team in enumerate(teams_data.get("response", [])[:15]):
                        # Update the field names to match SportsData.io response format
                        name = team.get("Name", "Unknown")
                        city = team.get("City", "")
                        key = team.get("Key", "")
                        conference = team.get("Conference", "")
                        response_text += f"{i+1}. {city} {name} ({key}) - {conference}\n"
                    
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
                        # Update field names to match SportsData.io response format
                        name = f"{player.get('FirstName', '')} {player.get('LastName', '')}"
                        team = player.get("Team", "Unknown team")
                        position = player.get("Position", "")
                        jersey = player.get("Jersey", "")
                        response_text += f"{i+1}. {name} - #{jersey} {position} ({team})\n"
                    
                    if len(players_data.get("response", [])) > 10:
                        response_text += f"\nShowing 10 of {len(players_data.get('response', []))} players."
            
            elif any(word in query.lower() for word in ["standings", "ranking", "leaderboard"]):
                season = "2023" if "2023" in query else "2023"  # SportsData uses just the year
                standings_data = await self.get_standings(season=season)
                response_text = f"Here are the NBA standings for the {season} season:\n\n"
                
                if "error" in standings_data:
                    response_text = f"Sorry, I couldn't retrieve standings data: {standings_data['error']}"
                else:
                    for i, standing in enumerate(standings_data.get("response", [])[:15]):
                        # Update field names to match SportsData.io response format
                        team = standing.get("Name", "Unknown")
                        city = standing.get("City", "")
                        conference = standing.get("Conference", "")
                        division = standing.get("Division", "")
                        wins = standing.get("Wins", 0)
                        losses = standing.get("Losses", 0)
                        percentage = standing.get("Percentage", 0)
                        response_text += f"{i+1}. {city} {team} ({conference}/{division}): {wins}-{losses} ({percentage:.3f})\n"
                    
                    if len(standings_data.get("response", [])) > 15:
                        response_text += f"\nShowing 15 of {len(standings_data.get('response', []))} teams."
            
            elif any(word in query.lower() for word in ["stats", "statistics"]):
                stats_data = await self.get_statistics()
                response_text = "Here are some NBA statistics:\n\n"
                
                if "error" in stats_data:
                    response_text = f"Sorry, I couldn't retrieve statistics data: {stats_data['error']}"
                else:
                    # Show top players based on points if no specific request
                    response_text = "Here are some top NBA player stats:\n\n"
                    players = sorted(stats_data.get("response", []), 
                                    key=lambda x: x.get("Points", 0) if x.get("Points") is not None else 0, 
                                    reverse=True)
                    
                    for i, player in enumerate(players[:10]):
                        name = f"{player.get('FirstName', '')} {player.get('LastName', '')}"
                        team = player.get('Team', '')
                        points = player.get('Points', 0)
                        rebounds = player.get('Rebounds', 0)
                        assists = player.get('Assists', 0)
                        
                        response_text += f"{i+1}. {name} ({team}): {points} PTS, {rebounds} REB, {assists} AST\n"
                    
                    if len(players) > 10:
                        response_text += f"\nShowing top 10 players by points."
            
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
        api_key=os.getenv("SPORTSDATA_API_KEY"),
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
