"""
Tools for Flight Booking Agent
Direct SQLite operations for booking management.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from strands import tool
from dependencies import get_db_manager

logger = logging.getLogger(__name__)


@tool
def check_availability(flight_id: int) -> str:
    # Check seat availability for a specific flight
    logger.info(f"Tool called: check_availability(flight_id={flight_id})")
    try:
        availability = get_db_manager().get_flight_availability(flight_id)
        
        if not availability:
            return json.dumps({"error": f"Flight with ID {flight_id} not found"})
        
        return json.dumps(availability, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"Database error: {str(e)}"})


@tool
def reserve_flight(flight_id: int, passengers: List[Dict[str, str]], requested_seats: List[str] = None) -> str:
    # Reserve seats on a flight for passengers
    logger.info(f"Tool called: reserve_flight(flight_id={flight_id}, passengers={len(passengers)})")
    try:
        reservation = get_db_manager().create_reservation(flight_id, passengers, requested_seats)
        return json.dumps(reservation, indent=2)
        
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Database error: {str(e)}"})


@tool
def confirm_booking(booking_number: str) -> str:
    # Confirm and finalize a flight booking
    logger.info(f"Tool called: confirm_booking(booking_number={booking_number})")
    try:
        confirmation = get_db_manager().confirm_booking(booking_number)
        return json.dumps(confirmation, indent=2)
        
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Database error: {str(e)}"})


@tool
def process_payment(booking_number: str, payment_method: str, amount: float = None) -> str:
    # Process payment for a booking (simulated)
    logger.info(f"Tool called: process_payment(booking_number={booking_number}, payment_method={payment_method})")
    try:
        payment_result = get_db_manager().process_payment(booking_number, payment_method, amount)
        return json.dumps(payment_result, indent=2)
        
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Database error: {str(e)}"})


@tool
def manage_reservation(booking_number: str, action: str, reason: str = None) -> str:
    # Update, view, or cancel existing reservations
    logger.info(f"Tool called: manage_reservation(booking_number={booking_number}, action={action})")
    try:
        db_manager = get_db_manager()
        if action == "view":
            booking_details = db_manager.get_booking_details(booking_number)
            return json.dumps(booking_details, indent=2)
            
        elif action == "cancel":
            if not reason:
                return json.dumps({"error": "Cancellation reason is required"})
            
            cancellation_result = db_manager.cancel_booking(booking_number, reason)
            return json.dumps(cancellation_result, indent=2)
            
        else:
            return json.dumps({"error": f"Unknown action: {action}. Supported actions: view, cancel"})
            
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Database error: {str(e)}"})


# TODO: Create tool whats able to dynamically search agents from MCP Registry
# example:
# @tool
# def delegate_to_agent(agent_capability: str, action: str, params: Dict) -> str:

FLIGHT_BOOKING_TOOLS = [
    check_availability,
    reserve_flight,
    confirm_booking,
    process_payment,
    manage_reservation
]