import os
import sqlite3
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class FlightDatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        logger.info(f"Initializing FlightDatabaseManager with db_path: {db_path}")
        self.init_database()
    
    def init_database(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
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
                CREATE TABLE IF NOT EXISTS trip_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    departure_city TEXT NOT NULL,
                    arrival_city TEXT NOT NULL,
                    departure_date TEXT NOT NULL,
                    return_date TEXT,
                    budget DECIMAL(10,2),
                    status TEXT DEFAULT 'planning',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor = conn.execute("SELECT COUNT(*) FROM flights")
            if cursor.fetchone()[0] == 0:
                self._insert_seed_data(conn)
    
    def _insert_seed_data(self, conn):
        seed_data = [
            (1, 'UA101', 'United', 'SF', 'NY', '2025-11-15 08:00', '2025-11-15 16:30', 330, 250.00, 85, 'B737'),
            (2, 'AA202', 'American', 'SF', 'NY', '2025-11-15 10:15', '2025-11-15 18:45', 330, 280.00, 45, 'A320'),
            (3, 'DL303', 'Delta', 'SF', 'NY', '2025-11-15 14:30', '2025-11-15 23:00', 330, 220.00, 120, 'B757'),
            (4, 'UA104', 'United', 'SF', 'LA', '2025-11-16 07:00', '2025-11-16 08:30', 90, 120.00, 95, 'B737'),
            (5, 'AA205', 'American', 'NY', 'SF', '2025-11-17 09:00', '2025-11-17 12:30', 330, 260.00, 78, 'A321'),
            (6, 'DL306', 'Delta', 'LA', 'NY', '2025-11-18 11:00', '2025-11-18 19:30', 330, 240.00, 92, 'B757')
        ]
        
        conn.executemany("""
            INSERT OR IGNORE INTO flights 
            (id, flight_number, airline, departure_city, arrival_city, 
             departure_time, arrival_time, duration_minutes, price, 
             available_seats, aircraft_type) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, seed_data)
        
        conn.commit()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def search_flights(self, departure_city: str, arrival_city: str, departure_date: str) -> List[Dict[str, Any]]:
        logger.info(f"Searching flights: {departure_city} -> {arrival_city}, date: {departure_date}")
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, flight_number, airline, departure_city, arrival_city,
                       departure_time, arrival_time, duration_minutes, price, 
                       available_seats, aircraft_type
                FROM flights 
                WHERE departure_city = ? AND arrival_city = ? 
                AND DATE(departure_time) = ?
                ORDER BY price ASC
            """, (departure_city.upper(), arrival_city.upper(), departure_date))
            
            flights = []
            for row in cursor.fetchall():
                flights.append({
                    "id": row[0],
                    "flight_number": row[1],
                    "airline": row[2],
                    "departure_city": row[3],
                    "arrival_city": row[4],
                    "departure_time": row[5],
                    "arrival_time": row[6],
                    "duration_minutes": row[7],
                    "price": float(row[8]),
                    "available_seats": row[9],
                    "aircraft_type": row[10]
                })
            
            logger.info(f"Found {len(flights)} flights")
            return flights
    
    def get_flight_details(self, flight_id: int) -> Optional[Dict[str, Any]]:
        logger.info(f"Getting flight details for flight_id: {flight_id}")
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT flight_number, airline, departure_city, arrival_city,
                       departure_time, arrival_time, price, available_seats
                FROM flights 
                WHERE id = ?
            """, (flight_id,))
            
            row = cursor.fetchone()
            if not row:
                logger.warning(f"Flight not found: flight_id={flight_id}")
                return None
            
            logger.info(f"Flight details retrieved: {row[0]}")
            
            return {
                "flight_id": flight_id,
                "flight_number": row[0],
                "airline": row[1],
                "route": f"{row[2]} → {row[3]}",
                "departure_time": row[4],
                "arrival_time": row[5],
                "price": float(row[6]),
                "available_seats": row[7],
                "availability_status": "Available" if row[7] > 0 else "Sold Out"
            }
    
    def get_recommendations(self, max_price: float, preferred_airlines: List[str] = None) -> List[Dict[str, Any]]:
        logger.info(f"Getting recommendations: max_price={max_price}, airlines={preferred_airlines}")
        with self.get_connection() as conn:
            query = "SELECT * FROM flights WHERE price <= ? AND available_seats > 0"
            params = [max_price]
            
            if preferred_airlines:
                placeholders = ','.join(['?' for _ in preferred_airlines])
                query += f" AND airline IN ({placeholders})"
                params.extend(preferred_airlines)
            
            query += " ORDER BY price ASC, available_seats DESC"
            
            cursor = conn.execute(query, params)
            
            recommendations = []
            for row in cursor.fetchall():
                recommendations.append({
                    "id": row[0],
                    "flight_number": row[1],
                    "airline": row[2],
                    "route": f"{row[3]} → {row[4]}",
                    "departure_time": row[5],
                    "arrival_time": row[6],
                    "duration_minutes": row[7],
                    "price": float(row[8]),
                    "available_seats": row[9],
                    "aircraft_type": row[10],
                    "recommendation_score": min(100, int((max_price - float(row[8])) / max_price * 100))
                })
            
            logger.info(f"Found {len(recommendations)} recommendations")
            return recommendations
    
    def create_trip_plan(self, departure_city: str, arrival_city: str, departure_date: str, 
                        return_date: str = None, budget: float = None) -> int:
        logger.info(f"Creating trip plan: {departure_city} -> {arrival_city}, date: {departure_date}, budget: {budget}")
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO trip_plans 
                (departure_city, arrival_city, departure_date, return_date, budget)
                VALUES (?, ?, ?, ?, ?)
            """, (departure_city.upper(), arrival_city.upper(), departure_date, return_date, budget))
            
            trip_plan_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Trip plan created: trip_plan_id={trip_plan_id}")
            return trip_plan_id

