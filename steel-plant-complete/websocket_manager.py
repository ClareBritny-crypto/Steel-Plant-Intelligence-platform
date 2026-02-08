"""
WebSocket Manager - Real-time Broadcasting
"""
from fastapi import WebSocket
from typing import Set, Dict
import json
from datetime import datetime


class WSManager:
    def __init__(self):
        self.connections: Set[WebSocket] = set()
        self.equipment_subs: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.add(websocket)
        print(f"✅ WS connected (Total: {len(self.connections)})")
    
    def disconnect(self, websocket: WebSocket):
        self.connections.discard(websocket)
        for equip_id, subs in list(self.equipment_subs.items()):
            subs.discard(websocket)
            if not subs:
                del self.equipment_subs[equip_id]
        print(f"🔌 WS disconnected (Remaining: {len(self.connections)})")
    
    def subscribe_equipment(self, websocket: WebSocket, equip_id: str):
        if equip_id not in self.equipment_subs:
            self.equipment_subs[equip_id] = set()
        self.equipment_subs[equip_id].add(websocket)
    
    async def broadcast(self, message: Dict):
        if not self.connections:
            return
        
        msg_json = json.dumps(message)
        dead = set()
        
        for ws in self.connections:
            try:
                await ws.send_text(msg_json)
            except:
                dead.add(ws)
        
        for ws in dead:
            self.disconnect(ws)
    
    async def broadcast_equipment(self, equip_id: str, message: Dict):
        if equip_id not in self.equipment_subs:
            return
        
        msg_json = json.dumps(message)
        dead = set()
        
        for ws in self.equipment_subs[equip_id]:
            try:
                await ws.send_text(msg_json)
            except:
                dead.add(ws)
        
        for ws in dead:
            self.disconnect(ws)


ws_manager = WSManager()

def get_ws_manager():
    return ws_manager
