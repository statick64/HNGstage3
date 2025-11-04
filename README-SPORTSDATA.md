# NBA Agent with SportsData.io API

This project is an NBA information agent built using the SportsData.io NBA API and implementing the A2A (Agent-to-Agent) protocol. The agent can provide information about NBA games, teams, players, standings, and statistics.

## Setup Instructions

### 1. Get a SportsData.io API Key

1. Visit [SportsData.io](https://sportsdata.io/developers/api-documentation/nba)
2. Register for an account and subscribe to the NBA API package
3. Retrieve your API key from your dashboard

### 2. Configure Environment Variables

Create a `.env` file in the root directory with the following variables:

```
# SportsData.io API Key (required)
SPORTSDATA_API_KEY=your_sportsdata_api_key_here

# AWS S3 Configuration (optional, for file storage)
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_REGION_NAME=us-east-1
AWS_BUCKET_NAME=your_bucket_name

# Server Configuration
PORT=5001
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the Server

```bash
python main.py
```

Or use the batch file:

```bash
start_telex_agent.bat
```

## API Endpoints

The NBA Agent exposes the following endpoints:

### Main A2A Endpoint
- **URL**: `/a2a/nba`
- **Method**: POST
- Handles NBA-related queries using the A2A protocol

### Health Check
- **URL**: `/health`
- **Method**: GET
- Returns the health status of the agent

### Context Management
- **URL**: `/contexts`
- **Method**: GET
- Lists all available conversation contexts

- **URL**: `/contexts/{context_id}`
- **Method**: GET
- Gets a specific conversation context

- **URL**: `/contexts/{context_id}`
- **Method**: DELETE
- Deletes a specific conversation context

## SportsData.io API Endpoints Used

This agent integrates with the following SportsData.io endpoints:

1. **Games**
   - `/scores/json/GamesByDate/{date}`
   - `/scores/json/Games/{season}`

2. **Teams**
   - `/scores/json/teams`

3. **Players**
   - `/scores/json/Players`
   - `/scores/json/Players/{team}`

4. **Standings**
   - `/scores/json/Standings/{season}`

5. **Statistics**
   - `/stats/json/BoxScore/{game_id}`
   - `/stats/json/PlayerSeasonStatsByPlayer/{player}`
   - `/stats/json/TeamSeasonStats/{season}`

## Testing the API

You can test the API using the included test client:

```bash
python test_telex_client.py
```

Or use Postman with the endpoints documented above.

## Deploying to Railway

To deploy this project to Railway:

1. Make sure you have the `Procfile` in your project (already included)
2. Set up your Railway project with the required environment variables
3. Connect your GitHub repository to Railway
4. Railway will automatically deploy the application

## License

[MIT](LICENSE)
