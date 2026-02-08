"""
Database Module - SQLite for Steel Plant Data
"""
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
import json

DB_PATH = "steel_plant.db"


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS equipment (
                equip_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                type_display TEXT NOT NULL,
                stage_id TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equip_id TEXT NOT NULL,
                sensor_name TEXT NOT NULL,
                value REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sensor_readings 
            ON sensor_readings(equip_id, sensor_name, timestamp DESC)
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equip_id TEXT NOT NULL,
                failure_probability REAL NOT NULL,
                health_score REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id TEXT PRIMARY KEY,
                equip_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                acknowledged BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def insert_sensor_reading(self, equip_id: str, sensor_name: str, value: float):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sensor_readings (equip_id, sensor_name, value)
            VALUES (?, ?, ?)
        """, (equip_id, sensor_name, value))
        conn.commit()
        conn.close()
    
    def insert_prediction(self, equip_id: str, failure_prob: float, health_score: float):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO predictions (equip_id, failure_probability, health_score)
            VALUES (?, ?, ?)
        """, (equip_id, failure_prob, health_score))
        conn.commit()
        conn.close()
    
    def insert_alert(self, alert_data: Dict):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO alerts 
            (alert_id, equip_id, severity, message, acknowledged)
            VALUES (?, ?, ?, ?, ?)
        """, (
            alert_data["alert_id"],
            alert_data["equipment"],
            alert_data["severity"],
            alert_data["message"],
            alert_data.get("acknowledged", False)
        ))
        conn.commit()
        conn.close()


_db = None

def get_db():
    global _db
    if _db is None:
        _db = Database()
    return _db
