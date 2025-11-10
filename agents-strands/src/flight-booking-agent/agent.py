import logging
from contextlib import asynccontextmanager
from strands import Agent
from strands.multiagent.a2a import A2AServer
import uvicorn
from fastapi import FastAPI
from dependencies import get_env, get_db_manager
from tools import FLIGHT_BOOKING_TOOLS, check_availability, reserve_flight, confirm_booking, process_payment, manage_reservation

logging.basicConfig(level=logging.INFO)

strands_agent = Agent(
    name="Flight Booking Agent",
    description="Flight booking and reservation management agent",
    tools=FLIGHT_BOOKING_TOOLS,
    callback_handler=None
)

env_settings = get_env()
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


app = FastAPI(title="Flight Booking Agent", lifespan=lifespan)

@app.get("/ping")
def ping():
    return {"status": "healthy"}

@app.get("/api/health")
def health():
    return {"status": "healthy", "agent": "flight_booking"}

@app.post("/api/check-availability")
def api_check_availability(flight_id: int):
    return {"result": check_availability(flight_id)}

@app.post("/api/reserve-flight")
def api_reserve_flight(flight_id: int, passengers: list, requested_seats: list = None):
    return {"result": reserve_flight(flight_id, passengers, requested_seats)}

@app.post("/api/confirm-booking")
def api_confirm_booking(booking_number: str):
    return {"result": confirm_booking(booking_number)}

@app.post("/api/process-payment")
def api_process_payment(booking_number: str, payment_method: str, amount: float = None):
    return {"result": process_payment(booking_number, payment_method, amount)}

@app.get("/api/reservation/{booking_number}")
def api_get_reservation(booking_number: str):
    return {"result": manage_reservation(booking_number, "view")}

@app.delete("/api/reservation/{booking_number}")
def api_cancel_reservation(booking_number: str, reason: str = "User requested cancellation"):
    return {"result": manage_reservation(booking_number, "cancel", reason)}

app.mount("/", a2a_server.to_fastapi_app())

if __name__ == "__main__":
    uvicorn.run(app, host=env_settings.host, port=env_settings.port)