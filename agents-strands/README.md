# Travel Booking Agents

Two AI agents built with AWS Bedrock AgentCore and the Strands framework for flight search and booking.

## Agents

**Travel Assistant Agent** (`travel_assistant_agent`)
- Searches for available flights between cities
- Provides flight recommendations based on price and preferences
- Returns detailed flight information (times, prices, airlines)
- [Full specification](https://github.com/agentic-community/mcp-gateway-registry/issues/196)

**Flight Booking Agent** (`flight_booking_agent`)
- Checks flight availability and seat counts
- Creates flight reservations
- Manages booking database
- [Full specification](https://github.com/agentic-community/mcp-gateway-registry/issues/197)

## Deployment Options

### Local Docker Container

Run agents locally with full FastAPI server including custom API endpoints.

**Prerequisites:**
- Docker and Docker Compose
- AWS credentials (for Bedrock model access)
- `uv sync --extra dev` to install main dependencies and development ones

**Deploy:**
```bash
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_REGION=us-east-1

./deploy_local.sh
```

**Endpoints:**
- Travel Assistant: `http://localhost:9001`
- Flight Booking: `http://localhost:9002`
- Custom APIs: `/api/search-flights`, `/api/recommendations`, `/api/check-availability`
- Health check: `/ping`

### AgentCore Runtime (AWS)

Deploy agents to AWS managed infrastructure with automatic scaling.

**Prerequisites:**
- AWS credentials with AgentCore permissions
- AgentCore CLI: `pip install bedrock-agentcore-starter-toolkit`

**Deploy:**
```bash
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_REGION=us-east-1

./deploy_live.sh
```

**Access:**
- Agents accessible via A2A protocol only
- ARNs shown in deployment output
- CloudWatch logs for monitoring

## Testing

### Agent Card Endpoint (Local)

Test the agent card endpoint locally to verify agent metadata:

```bash
cd tst
./check_agent_cards.sh
```

> **Next Steps:** For remote testing of deployed agents, consider using the [A2A Inspector](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-testing.html) to interact with and debug your AgentCore Runtime deployments.

### Agent and API Tests

Run tests against local or live deployments:

```bash
# Test local Docker containers
cd tst
python3 simple_agents_test.py --endpoint local

# Test AgentCore Runtime
python3 simple_agents_test.py --endpoint live
```

## Key Differences

| Feature | Local Docker | AgentCore Runtime |
|---------|-------------|-------------------|
| A2A Protocol | ✅ | ✅ |
| Custom API Endpoints | ✅ | ❌ |
| Health Check `/ping` | ✅ | ❌ |
| Deployment | Docker Compose | AgentCore CLI |

**Note:** Custom FastAPI endpoints (like `/api/search-flights`) are only available in local Docker deployments. **AgentCore Runtime only wraps the container and exposes the standard A2A conversational interface.**
