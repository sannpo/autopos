import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
from config import load_config, save_config

SUBSCRIPTION_FILE = "subscriptions.json"

def load_subscriptions() -> Dict:
    """Load data subscription dari file"""
    try:
        if os.path.exists(SUBSCRIPTION_FILE):
            with open(SUBSCRIPTION_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        return {}
    except (json.JSONDecodeError, IOError):
        return {}

def save_subscriptions(data: Dict) -> None:
    """Save data subscription ke file"""
    try:
        with open(SUBSCRIPTION_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except (IOError, TypeError) as e:
        raise Exception(f"Failed to save subscriptions: {str(e)}")

def create_subscription(user_id: str, package_type: str, duration_days: int) -> str:
    """Buat subscription baru dan return subscription ID"""
    subscriptions = load_subscriptions()
    
    # Generate unique subscription ID
    import uuid
    subscription_id = str(uuid.uuid4())[:8].upper()
    
    start_date = datetime.now()
    end_date = start_date + timedelta(days=duration_days)
    
    subscriptions[subscription_id] = {
        "user_id": user_id,
        "package_type": package_type,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "active": True,
        "discord_user_id": None  # Akan diisi saat login
    }
    
    save_subscriptions(subscriptions)
    return subscription_id

def validate_subscription(subscription_id: str, discord_user_id: str) -> bool:
    """Validasi subscription ID"""
    subscriptions = load_subscriptions()
    
    if subscription_id not in subscriptions:
        return False
        
    sub = subscriptions[subscription_id]
    
    # Cek apakah sudah expired
    end_date = datetime.fromisoformat(sub["end_date"])
    if datetime.now() > end_date:
        sub["active"] = False
        save_subscriptions(subscriptions)
        return False
    
    # Cek apakah sudah dipakai oleh user lain
    if sub["discord_user_id"] and sub["discord_user_id"] != discord_user_id:
        return False
        
    # Jika belum dipakai, assign ke user ini
    if not sub["discord_user_id"]:
        sub["discord_user_id"] = discord_user_id
        save_subscriptions(subscriptions)
    
    return sub["active"]

def get_user_subscription(discord_user_id: str) -> Optional[Dict]:
    """Dapatkan subscription info user"""
    subscriptions = load_subscriptions()
    
    for sub_id, sub_data in subscriptions.items():
        if sub_data.get("discord_user_id") == discord_user_id:
            return {
                "subscription_id": sub_id,
                **sub_data
            }
    return None

def get_subscription_info(subscription_id: str) -> Optional[Dict]:
    """Dapatkan info subscription"""
    subscriptions = load_subscriptions()
    return subscriptions.get(subscription_id)

def extend_subscription(subscription_id: str, additional_days: int) -> bool:
    """Perpanjang subscription"""
    subscriptions = load_subscriptions()
    
    if subscription_id not in subscriptions:
        return False
        
    sub = subscriptions[subscription_id]
    end_date = datetime.fromisoformat(sub["end_date"])
    new_end_date = end_date + timedelta(days=additional_days)
    
    sub["end_date"] = new_end_date.isoformat()
    sub["active"] = True
    
    save_subscriptions(subscriptions)
    return True

# Predefined packages
PACKAGES = {
    "1minggu": {"days": 7, "price": 2500, "name": "1 Minggu"},
    "1bulan": {"days": 30, "price": 10000, "name": "1 Bulan"},
    "3bulan": {"days": 90, "price": 25000, "name": "3 Bulan"}
}