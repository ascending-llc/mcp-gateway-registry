import logging
from contextlib import asynccontextmanager
from strands import Agent
from strands.multiagent.a2a import A2AServer
import uvicorn
from fastapi import FastAPI
from dependencies import get_env, get_db_manager
from tools import TRAVEL_ASSISTANT_TOOLS, search_flights, check_prices, get_recommendations, create_trip_plan

logging.basicConfig(level=logging.INFO)

env_settings = get_env()

strands_agent = Agent(
    name="Travel Assistant Agent",
    description="Flight search and trip planning agent",
    tools=TRAVEL_ASSISTANT_TOOLS,
    callback_handler=None
)

a2a_server = A2AServer(
    agent=strands_agent,
    http_url=env_settings.agent_url,
    serve_at_root=True
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setups before sever startup
    get_db_manager() 
    
    # TODO: register agent with MCP Gateway Registry when path available

    yield
    # Triggered after server shutdown


app = FastAPI(title="Travel Assistant Agent", lifespan=lifespan)

@app.get("/ping")
def ping():
    return {"status": "healthy"}

@app.get("/api/health")
def health():
    return {"status": "healthy", "agent": "travel_assistant"}

@app.post("/api/search-flights")
def api_search_flights(departure_city: str, arrival_city: str, departure_date: str):
    return {"result": search_flights(departure_city, arrival_city, departure_date)}

@app.post("/api/check-prices")
def api_check_prices(flight_id: int):
    return {"result": check_prices(flight_id)}

@app.get("/api/recommendations")
def api_recommendations(max_price: float, preferred_airlines: str = None):
    airlines = preferred_airlines.split(",") if preferred_airlines else None
    return {"result": get_recommendations(max_price, airlines)}

@app.post("/api/create-trip-plan")
def api_create_trip_plan(departure_city: str, arrival_city: str, departure_date: str, 
                        return_date: str = None, budget: float = None):
    return {"result": create_trip_plan(departure_city, arrival_city, departure_date, return_date, budget)}

app.mount("/", a2a_server.to_fastapi_app())

if __name__ == "__main__":
    uvicorn.run(app, host=env_settings.host, port=env_settings.port)