import os
import sqlite3
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class BookingDatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        logger.info(f"Initializing BookingDatabaseManager with db_path: {db_path}")
        self.init_database()
    
    def init_database(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            self.create_tables(conn)
            self.insert_seed_data(conn)
    
    def create_tables(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS flights (
                id INTEGER PRIMARY KEY,
                flight_number TEXT UNIQUE NOT NULL,
                airline TEXT NOT NULL,
                departure_city TEXT NOT NULL,
                arrival_city TEXT NOT NULL,
                departure_time DATETIME NOT NULL,
                arrival_time DATETIME NOT NULL,
                duration_minutes INTEGER,
                price DECIMAL(10,2),
                available_seats INTEGER DEFAULT 100,
                aircraft_type TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_number TEXT UNIQUE NOT NULL,
                flight_id INTEGER NOT NULL,
                total_price DECIMAL(10,2),
                status TEXT CHECK(status IN ('pending', 'confirmed', 'paid', 'cancelled')) DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                confirmed_at DATETIME,
                FOREIGN KEY (flight_id) REFERENCES flights(id)
            )
        """)
        
        # Booking passengers table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS booking_passengers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                passenger_name TEXT NOT NULL,
                email TEXT,
                seat_number TEXT,
                FOREIGN KEY (booking_id) REFERENCES bookings(id)
            )
        """)
        
        # Payments table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                amount DECIMAL(10,2),
                status TEXT CHECK(status IN ('pending', 'completed', 'failed')) DEFAULT 'pending',
                payment_method TEXT,
                transaction_id TEXT,
                processed_at DATETIME,
                FOREIGN KEY (booking_id) REFERENCES bookings(id)
            )
        """)
        
        # Seat inventory table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seat_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flight_id INTEGER NOT NULL,
                seat_row TEXT,
                seat_column TEXT,
                status TEXT CHECK(status IN ('available', 'reserved', 'booked')) DEFAULT 'available',
                FOREIGN KEY (flight_id) REFERENCES flights(id)
            )
        """)
        
        # Cancellations table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cancellations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                reason TEXT,
                refund_amount DECIMAL(10,2),
                cancelled_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (booking_id) REFERENCES bookings(id)
            )
        """)
    
    def insert_seed_data(self, conn):
        

        cursor = conn.execute("SELECT COUNT(*) FROM flights")
        if cursor.fetchone()[0] == 0:
            flight_data = [
                (1, 'UA101', 'United', 'SF', 'NY', '2025-11-15 08:00', '2025-11-15 16:30', 330, 250.00, 85, 'B737'),
                (2, 'AA202', 'American', 'SF', 'NY', '2025-11-15 10:15', '2025-11-15 18:45', 330, 280.00, 45, 'A320'),
                (3, 'DL303', 'Delta', 'SF', 'NY', '2025-11-15 14:30', '2025-11-15 23:00', 330, 220.00, 120, 'B757'),
                (4, 'UA104', 'United', 'SF', 'LA', '2025-11-16 07:00', '2025-11-16 08:30', 90, 120.00, 95, 'B737')
            ]
            
            conn.executemany("""
                INSERT OR IGNORE INTO flights 
                (id, flight_number, airline, departure_city, arrival_city, 
                 departure_time, arrival_time, duration_minutes, price, 
                 available_seats, aircraft_type) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, flight_data)
        
        cursor = conn.execute("SELECT COUNT(*) FROM bookings")
        if cursor.fetchone()[0] == 0:
            booking_data = [
                ('BK001', 1, 500.00, 'confirmed', '2025-11-01 10:00:00', '2025-11-01 10:15:00'),
                ('BK002', 1, 250.00, 'pending', '2025-11-01 11:00:00', None),
                ('BK003', 2, 560.00, 'confirmed', '2025-11-01 12:00:00', '2025-11-01 12:10:00'),
                ('BK004', 3, 440.00, 'confirmed', '2025-11-01 13:00:00', '2025-11-01 13:05:00')
            ]
            
            conn.executemany("""
                INSERT INTO bookings (booking_number, flight_id, total_price, status, created_at, confirmed_at) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, booking_data)
            

            passenger_data = [
                (1, 'John Smith', 'john@example.com', '12A'),
                (1, 'Jane Smith', 'jane@example.com', '12B'),
                (2, 'Bob Johnson', 'bob@example.com', '14C'),
                (3, 'Alice Williams', 'alice@example.com', '1A'),
                (4, 'Charlie Brown', 'charlie@example.com', '5B')
            ]
            
            conn.executemany("""
                INSERT INTO booking_passengers (booking_id, passenger_name, email, seat_number) 
                VALUES (?, ?, ?, ?)
            """, passenger_data)
            

            payment_data = [
                (1, 500.00, 'completed', 'credit_card', 'TXN001', '2025-11-01 10:15:00'),
                (2, 250.00, 'pending', 'credit_card', None, None),
                (3, 560.00, 'completed', 'credit_card', 'TXN003', '2025-11-01 12:10:00'),
                (4, 440.00, 'completed', 'paypal', 'TXN004', '2025-11-01 13:05:00')
            ]
            
            conn.executemany("""
                INSERT INTO payments (booking_id, amount, status, payment_method, transaction_id, processed_at) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, payment_data)
            

            seat_data = [
                (1, '1', 'A', 'booked'), (1, '1', 'B', 'booked'), (1, '1', 'C', 'available'), (1, '1', 'D', 'available'),
                (1, '12', 'A', 'booked'), (1, '12', 'B', 'booked'), (1, '12', 'C', 'available'), (1, '12', 'D', 'available'),
                (1, '14', 'C', 'booked'), (1, '14', 'D', 'available')
            ]
            
            conn.executemany("""
                INSERT INTO seat_inventory (flight_id, seat_row, seat_column, status) 
                VALUES (?, ?, ?, ?)
            """, seat_data)
            
            conn.commit()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def get_flight_availability(self, flight_id: int) -> Optional[Dict[str, Any]]:
        logger.info(f"Checking availability for flight_id: {flight_id}")
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT f.flight_number, f.airline, f.departure_city, f.arrival_city,
                       f.departure_time, f.available_seats, f.price
                FROM flights f
                WHERE f.id = ?
            """, (flight_id,))
            
            row = cursor.fetchone()
            if not row:
                logger.warning(f"Flight not found: flight_id={flight_id}")
                return None
            
            logger.info(f"Flight availability retrieved: {row[0]}, available_seats={row[5]}")
            
            return {
                "flight_id": flight_id,
                "flight_number": row[0],
                "airline": row[1],
                "route": f"{row[2]} → {row[3]}",
                "departure_time": row[4],
                "available_seats": row[5],
                "price_per_seat": float(row[6]),
                "availability_status": "Available" if row[5] > 0 else "Sold Out"
            }
    
    def create_reservation(self, flight_id: int, passengers: List[Dict[str, str]], 
                          requested_seats: List[str] = None) -> Dict[str, Any]:
        logger.info(f"Creating reservation for flight_id: {flight_id}, passengers: {len(passengers)}")
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT price, available_seats FROM flights WHERE id = ?", (flight_id,))
            flight_row = cursor.fetchone()
            
            if not flight_row:
                logger.error(f"Flight not found: flight_id={flight_id}")
                raise ValueError(f"Flight with ID {flight_id} not found")
            
            price_per_seat, available_seats = flight_row
            num_passengers = len(passengers)
            
            if available_seats < num_passengers:
                logger.warning(f"Insufficient seats: requested={num_passengers}, available={available_seats}")
                raise ValueError(f"Not enough seats available. Requested: {num_passengers}, Available: {available_seats}")
            

            booking_number = f"BK{uuid.uuid4().hex[:6].upper()}"
            total_price = float(price_per_seat) * num_passengers
            logger.info(f"Generated booking_number: {booking_number}, total_price: {total_price}")
            

            cursor = conn.execute("""
                INSERT INTO bookings (booking_number, flight_id, total_price, status)
                VALUES (?, ?, ?, 'pending')
            """, (booking_number, flight_id, total_price))
            
            booking_id = cursor.lastrowid
            

            assigned_seats = []
            for i, passenger in enumerate(passengers):
                seat_number = requested_seats[i] if requested_seats and i < len(requested_seats) else f"AUTO{i+1}"
                
                conn.execute("""
                    INSERT INTO booking_passengers (booking_id, passenger_name, email, seat_number)
                    VALUES (?, ?, ?, ?)
                """, (booking_id, passenger["name"], passenger.get("email", ""), seat_number))
                
                assigned_seats.append(seat_number)
            
            conn.execute("""
                UPDATE flights 
                SET available_seats = available_seats - ? 
                WHERE id = ?
            """, (num_passengers, flight_id))
            
            conn.commit()
            logger.info(f"Reservation created successfully: booking_number={booking_number}, booking_id={booking_id}")
            
            return {
                "booking_number": booking_number,
                "booking_id": booking_id,
                "flight_id": flight_id,
                "status": "reserved",
                "total_price": total_price,
                "passengers": passengers,
                "assigned_seats": assigned_seats,
                "reservation_expires": "24 hours from creation",
                "next_steps": ["Confirm booking", "Process payment"]
            }
    
    def confirm_booking(self, booking_number: str) -> Dict[str, Any]:
        logger.info(f"Confirming booking: {booking_number}")
        with self.get_connection() as conn:
            # Get booking details
            cursor = conn.execute("""
                SELECT id, flight_id, status, total_price
                FROM bookings 
                WHERE booking_number = ?
            """, (booking_number,))
            
            booking_row = cursor.fetchone()
            if not booking_row:
                logger.error(f"Booking not found: {booking_number}")
                raise ValueError(f"Booking {booking_number} not found")
            
            booking_id, flight_id, current_status, total_price = booking_row
            
            if current_status != 'pending':
                logger.warning(f"Cannot confirm booking {booking_number}, status: {current_status}")
                raise ValueError(f"Booking {booking_number} cannot be confirmed. Current status: {current_status}")
            
            # Update booking status
            confirmation_time = datetime.now().isoformat()
            conn.execute("""
                UPDATE bookings 
                SET status = 'confirmed', confirmed_at = ?
                WHERE booking_number = ?
            """, (confirmation_time, booking_number))
            
            conn.commit()
            
            # Generate confirmation code
            confirmation_code = f"CONF{uuid.uuid4().hex[:8].upper()}"
            logger.info(f"Booking confirmed: {booking_number}, confirmation_code: {confirmation_code}")
            
            return {
                "booking_number": booking_number,
                "confirmation_code": confirmation_code,
                "status": "confirmed",
                "confirmed_at": confirmation_time,
                "total_price": float(total_price),
                "next_steps": ["Process payment to complete booking"]
            }
    
    def process_payment(self, booking_number: str, payment_method: str, amount: float = None) -> Dict[str, Any]:
        logger.info(f"Processing payment for booking: {booking_number}, method: {payment_method}")
        with self.get_connection() as conn:
            # Get booking details
            cursor = conn.execute("""
                SELECT id, total_price, status
                FROM bookings 
                WHERE booking_number = ?
            """, (booking_number,))
            
            booking_row = cursor.fetchone()
            if not booking_row:
                logger.error(f"Booking not found: {booking_number}")
                raise ValueError(f"Booking {booking_number} not found")
            
            booking_id, total_price, booking_status = booking_row
            payment_amount = amount if amount is not None else float(total_price)
            
            # Generate transaction ID
            transaction_id = f"TXN{uuid.uuid4().hex[:8].upper()}"
            processed_time = datetime.now().isoformat()
            logger.info(f"Payment transaction created: {transaction_id}, amount: {payment_amount}")
            
            # Insert payment record
            conn.execute("""
                INSERT INTO payments (booking_id, amount, status, payment_method, transaction_id, processed_at)
                VALUES (?, ?, 'completed', ?, ?, ?)
            """, (booking_id, payment_amount, payment_method, transaction_id, processed_time))
            
            # Update booking status to paid
            conn.execute("""
                UPDATE bookings 
                SET status = 'paid'
                WHERE booking_number = ?
            """, (booking_number,))
            
            conn.commit()
            logger.info(f"Payment completed: booking={booking_number}, transaction={transaction_id}")
            
            return {
                "booking_number": booking_number,
                "transaction_id": transaction_id,
                "payment_status": "completed",
                "amount_paid": payment_amount,
                "payment_method": payment_method,
                "processed_at": processed_time,
                "booking_status": "paid",
                "message": "Payment processed successfully. Booking is now complete."
            }
    
    def get_booking_details(self, booking_number: str) -> Dict[str, Any]:
        with self.get_connection() as conn:
            # Get complete booking details
            cursor = conn.execute("""
                SELECT b.id, b.booking_number, b.flight_id, b.total_price, b.status,
                       b.created_at, b.confirmed_at, f.flight_number, f.airline,
                       f.departure_city, f.arrival_city, f.departure_time
                FROM bookings b
                JOIN flights f ON b.flight_id = f.id
                WHERE b.booking_number = ?
            """, (booking_number,))
            
            booking_row = cursor.fetchone()
            if not booking_row:
                raise ValueError(f"Booking {booking_number} not found")
            
            # Get passengers
            passenger_cursor = conn.execute("""
                SELECT passenger_name, email, seat_number
                FROM booking_passengers
                WHERE booking_id = ?
            """, (booking_row[0],))
            
            passengers = []
            for p_row in passenger_cursor.fetchall():
                passengers.append({
                    "name": p_row[0],
                    "email": p_row[1],
                    "seat": p_row[2]
                })
            
            return {
                "booking_number": booking_number,
                "flight": {
                    "flight_number": booking_row[7],
                    "airline": booking_row[8],
                    "route": f"{booking_row[9]} → {booking_row[10]}",
                    "departure_time": booking_row[11]
                },
                "booking_details": {
                    "status": booking_row[4],
                    "total_price": float(booking_row[3]),
                    "created_at": booking_row[5],
                    "confirmed_at": booking_row[6]
                },
                "passengers": passengers
            }
    
    def cancel_booking(self, booking_number: str, reason: str) -> Dict[str, Any]:
        logger.info(f"Cancelling booking: {booking_number}, reason: {reason}")
        with self.get_connection() as conn:
            # Get booking details
            cursor = conn.execute("""
                SELECT id, flight_id, status, total_price
                FROM bookings 
                WHERE booking_number = ?
            """, (booking_number,))
            
            booking_row = cursor.fetchone()
            if not booking_row:
                logger.error(f"Booking not found: {booking_number}")
                raise ValueError(f"Booking {booking_number} not found")
            
            booking_id, flight_id, current_status, total_price = booking_row
            
            if current_status == 'cancelled':
                logger.warning(f"Booking already cancelled: {booking_number}")
                raise ValueError(f"Booking {booking_number} is already cancelled")
            
            # Calculate refund amount (simplified logic)
            refund_amount = float(total_price) * 0.8  # 80% refund
            
            # Insert cancellation record
            conn.execute("""
                INSERT INTO cancellations (booking_id, reason, refund_amount)
                VALUES (?, ?, ?)
            """, (booking_id, reason, refund_amount))
            
            # Update booking status
            conn.execute("""
                UPDATE bookings 
                SET status = 'cancelled'
                WHERE booking_number = ?
            """, (booking_number,))
            
            # Get passenger count to free up seats
            cursor = conn.execute("""
                SELECT COUNT(*) FROM booking_passengers WHERE booking_id = ?
            """, (booking_id,))
            num_seats = cursor.fetchone()[0]
            
            # Update available seats count
            conn.execute("""
                UPDATE flights 
                SET available_seats = available_seats + ? 
                WHERE id = ?
            """, (num_seats, flight_id))
            
            conn.commit()
            logger.info(f"Booking cancelled: {booking_number}, refund_amount: {refund_amount}, seats_freed: {num_seats}")
            
            return {
                "booking_number": booking_number,
                "status": "cancelled",
                "cancellation_reason": reason,
                "refund_amount": refund_amount,
                "cancelled_at": datetime.now().isoformat(),
                "message": "Booking cancelled successfully. Refund will be processed within 5-7 business days."
            }


