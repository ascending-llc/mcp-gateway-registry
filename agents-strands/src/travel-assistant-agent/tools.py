import json
import logging
from typing import List, Dict, Any, Optional
from strands import tool
from dependencies import get_db_manager

logger = logging.getLogger(__name__)

@tool
def search_flights(departure_city: str, arrival_city: str, departure_date: str) -> str:
    logger.info(f"Tool called: search_flights(departure_city={departure_city}, arrival_city={arrival_city}, departure_date={departure_date})")
    try:
        flights = get_db_manager().search_flights(departure_city, arrival_city, departure_date)
        
        result = {
            "query": {
                "departure_city": departure_city,
                "arrival_city": arrival_city,
                "departure_date": departure_date
            },
            "flights": flights,
            "count": len(flights)
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"Database error: {str(e)}"})


@tool
def check_prices(flight_id: int) -> str:
    # Get pricing and seat availability for a specific flight
    logger.info(f"Tool called: check_prices(flight_id={flight_id})")
    try:
        flight_details = get_db_manager().get_flight_details(flight_id)
        
        if not flight_details:
            return json.dumps({"error": f"Flight with ID {flight_id} not found"})
        
        return json.dumps(flight_details, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"Database error: {str(e)}"})


@tool
def get_recommendations(max_price: float, preferred_airlines: List[str] = None) -> str:
    # Get flight recommendations based on customer preferences
    logger.info(f"Tool called: get_recommendations(max_price={max_price}, preferred_airlines={preferred_airlines})")
    try:
        recommendations = get_db_manager().get_recommendations(max_price, preferred_airlines)
        
        result = {
            "criteria": {
                "max_price": max_price,
                "preferred_airlines": preferred_airlines or "Any"
            },
            "recommendations": recommendations,
            "count": len(recommendations)
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"Database error: {str(e)}"})


@tool
def create_trip_plan(departure_city: str, arrival_city: str, departure_date: str, 
                    return_date: str = None, budget: float = None) -> str:
    # Create and save a trip planning record
    logger.info(f"Tool called: create_trip_plan(departure_city={departure_city}, arrival_city={arrival_city}, departure_date={departure_date})")
    try:
        db_manager = get_db_manager()
        trip_plan_id = db_manager.create_trip_plan(
            departure_city, arrival_city, departure_date, return_date, budget
        )
        
        # Get available flights for the trip
        outbound_flights = db_manager.search_flights(departure_city, arrival_city, departure_date)
        return_flights = []
        
        if return_date:
            return_flights = db_manager.search_flights(arrival_city, departure_city, return_date)
        
        result = {
            "trip_plan_id": trip_plan_id,
            "trip_details": {
                "departure_city": departure_city.upper(),
                "arrival_city": arrival_city.upper(),
                "departure_date": departure_date,
                "return_date": return_date,
                "budget": budget,
                "status": "planning"
            },
            "outbound_flights": outbound_flights,
            "return_flights": return_flights,
            "next_steps": [
                "Review available flights",
                "Select preferred flights",
                "Contact Flight Booking Agent for reservation"
            ]
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"Database error: {str(e)}"})


# TODO: Create tool whats able to dynamically search agents from MCP Registry
# example:
# @tool
# def delegate_to_agent(agent_capability: str, action: str, params: Dict) -> str:


TRAVEL_ASSISTANT_TOOLS = [
    search_flights,
    check_prices,
    get_recommendations,
    create_trip_plan
]