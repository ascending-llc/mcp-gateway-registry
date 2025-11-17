"""Tools for Flight Booking Agent - Direct SQLite operations for booking management."""

import json
import logging
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from strands import tool

from dependencies import get_db_manager

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


@tool
def check_availability(
    flight_id: int,
) -> str:
    """Check seat availability for a specific flight."""
    logger.info(f"Tool called: check_availability(flight_id={flight_id})")
    try:
        availability = get_db_manager().get_flight_availability(flight_id)

        if not availability:
            error_msg = f"Flight with ID {flight_id} not found"
            logger.warning(error_msg)
            return json.dumps({"error": error_msg})

        logger.debug(f"Availability result:\n{json.dumps(availability, indent=2)}")
        return json.dumps(availability, indent=2)

    except Exception as e:
        logger.error(f"Database error in check_availability: {e}")
        return json.dumps({"error": f"Database error: {str(e)}"})


@tool
def reserve_flight(
    flight_id: int,
    passengers: List[Dict[str, str]],
    requested_seats: Optional[List[str]] = None,
) -> str:
    """Reserve seats on a flight for passengers."""
    logger.info(f"Tool called: reserve_flight(flight_id={flight_id}, passengers={len(passengers)})")
    logger.debug(f"Passengers: {passengers}, Requested seats: {requested_seats}")
    try:
        reservation = get_db_manager().create_reservation(flight_id, passengers, requested_seats)
        logger.debug(f"Reservation result:\n{json.dumps(reservation, indent=2)}")
        return json.dumps(reservation, indent=2)

    except ValueError as e:
        logger.warning(f"Validation error in reserve_flight: {e}")
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Database error in reserve_flight: {e}")
        return json.dumps({"error": f"Database error: {str(e)}"})


@tool
def confirm_booking(
    booking_number: str,
) -> str:
    """Confirm and finalize a flight booking."""
    logger.info(f"Tool called: confirm_booking(booking_number={booking_number})")
    try:
        confirmation = get_db_manager().confirm_booking(booking_number)
        logger.debug(f"Confirmation result:\n{json.dumps(confirmation, indent=2)}")
        return json.dumps(confirmation, indent=2)

    except ValueError as e:
        logger.warning(f"Validation error in confirm_booking: {e}")
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Database error in confirm_booking: {e}")
        return json.dumps({"error": f"Database error: {str(e)}"})


@tool
def process_payment(
    booking_number: str,
    payment_method: str,
    amount: Optional[float] = None,
) -> str:
    """Process payment for a booking (simulated)."""
    logger.info(f"Tool called: process_payment(booking_number={booking_number}, payment_method={payment_method})")
    logger.debug(f"Payment amount: {amount}")
    try:
        payment_result = get_db_manager().process_payment(booking_number, payment_method, amount)
        logger.debug(f"Payment result:\n{json.dumps(payment_result, indent=2)}")
        return json.dumps(payment_result, indent=2)

    except ValueError as e:
        logger.warning(f"Validation error in process_payment: {e}")
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Database error in process_payment: {e}")
        return json.dumps({"error": f"Database error: {str(e)}"})


@tool
def manage_reservation(
    booking_number: str,
    action: str,
    reason: Optional[str] = None,
) -> str:
    """Update, view, or cancel existing reservations."""
    logger.info(f"Tool called: manage_reservation(booking_number={booking_number}, action={action})")
    logger.debug(f"Reason: {reason}")
    try:
        db_manager = get_db_manager()
        if action == "view":
            booking_details = db_manager.get_booking_details(booking_number)
            logger.debug(f"Booking details:\n{json.dumps(booking_details, indent=2)}")
            return json.dumps(booking_details, indent=2)

        elif action == "cancel":
            if not reason:
                error_msg = "Cancellation reason is required"
                logger.warning(error_msg)
                return json.dumps({"error": error_msg})

            cancellation_result = db_manager.cancel_booking(booking_number, reason)
            logger.debug(f"Cancellation result:\n{json.dumps(cancellation_result, indent=2)}")
            return json.dumps(cancellation_result, indent=2)

        else:
            error_msg = f"Unknown action: {action}. Supported actions: view, cancel"
            logger.warning(error_msg)
            return json.dumps({"error": error_msg})

    except ValueError as e:
        logger.warning(f"Validation error in manage_reservation: {e}")
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Database error in manage_reservation: {e}")
        return json.dumps({"error": f"Database error: {str(e)}"})


# TODO: Create tool that's able to dynamically search agents from MCP Registry
# example:
# @tool
# def delegate_to_agent(agent_capability: str, action: str, params: Dict) -> str:

FLIGHT_BOOKING_TOOLS = [check_availability, reserve_flight, confirm_booking, process_payment, manage_reservation]