"""
Database models for School Bus Route Planner
Uses SQLite for storing route optimization history
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class RouteHistory(db.Model):
    """Stores optimization run results for later retrieval"""
    __tablename__ = 'route_history'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    name = db.Column(db.String(100), nullable=False)
    summary = db.Column(db.String(200))  # e.g., "5 Buses, 120km, 45 Students"
    
    # Store the full optimization result as JSON
    result_json = db.Column(db.JSON, nullable=False)
    
    # Optional: Store input parameters for reference
    input_params = db.Column(db.JSON)
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'name': self.name,
            'summary': self.summary,
            'result_json': self.result_json,
            'input_params': self.input_params
        }
    
    def to_summary_dict(self):
        """Lightweight dict for listing (without full result_json)"""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'name': self.name,
            'summary': self.summary
        }


class VehicleType(db.Model):
    """Template for vehicle categories (e.g., 11-Seater, 45-Seater)"""
    __tablename__ = 'vehicle_type'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)          # "19-Seater Van"
    routing_profile = db.Column(db.String(30), default='van')  # "van", "allbus"
    capacity = db.Column(db.Integer, nullable=False)          # 19
    label = db.Column(db.String(30))                          # Display label/icon
    
    vehicles = db.relationship('Vehicle', backref='vehicle_type', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'routing_profile': self.routing_profile,
            'capacity': self.capacity,
            'label': self.label,
            'vehicle_count': len(self.vehicles)
        }


class Vehicle(db.Model):
    """Individual buses in the fleet"""
    __tablename__ = 'vehicle'
    
    id = db.Column(db.Integer, primary_key=True)
    plate_number = db.Column(db.String(20), unique=True)      # "SG1234X"
    nickname = db.Column(db.String(50))                        # "Blue Bus"
    driver_name = db.Column(db.String(100))
    status = db.Column(db.String(20), default='active')        # active/maintenance
    
    type_id = db.Column(db.Integer, db.ForeignKey('vehicle_type.id'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'plate_number': self.plate_number,
            'nickname': self.nickname,
            'driver_name': self.driver_name,
            'status': self.status,
            'type_id': self.type_id,
            'type_name': self.vehicle_type.name if self.vehicle_type else None,
            'capacity': self.vehicle_type.capacity if self.vehicle_type else None
        }
