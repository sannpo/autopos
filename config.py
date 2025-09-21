import json
import os
import datetime
from typing import Dict, Any
from exceptions import ConfigError

CONFIG_PATH = "config.json"
ADMIN_IDS = []  # Ini akan diisi dari environment variable

def load_config() -> Dict[str, Any]:
    """Load configuration from file with error handling"""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data.get("accounts", {}), dict):
                    data["accounts"] = {}
                if not isinstance(data.get("admins", {}), dict):
                    data["admins"] = {}
                return data
        return {"accounts": {}, "admins": {}}
    except (json.JSONDecodeError, IOError) as e:
        raise ConfigError(f"Failed to load configuration: {str(e)}")

def save_config(cfg: Dict[str, Any]) -> None:
    """Save configuration to file with error handling"""
    try:
        with open(CONFIG_PATH, "w", encoding='utf-8') as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except (IOError, TypeError) as e:
        raise ConfigError(f"Failed to save configuration: {str(e)}")

def is_admin(user_id: str) -> bool:
    """Check if user is admin"""
    try:
        config = load_config()
        admins = config.get("admins", {})
        return str(user_id) in admins and admins[str(user_id)].get("is_admin", False)
    except:
        return False

def add_admin(user_id: str, password: str) -> bool:
    """Add admin user"""
    config = load_config()
    user_id = str(user_id)

    # Pastikan selalu ada key "admins"
    if "admins" not in config or not isinstance(config["admins"], dict):
        config["admins"] = {}

    if user_id in config["admins"]:
        return False

    config["admins"][user_id] = {
        "is_admin": True,
        "password": password,  # ⚠️ Production sebaiknya hash password!
        "created_at": datetime.datetime.now().isoformat()
    }

    save_config(config)
    return True


def verify_admin(user_id: str, password: str) -> bool:
    """Verify admin credentials"""
    config = load_config()
    user_id = str(user_id)
    
    if user_id not in config["admins"]:
        return False
        
    return config["admins"][user_id].get("password") == password
CONFIG_PATH = "config.json"

def save_config(cfg: Dict[str, Any]) -> None:
    """Save configuration to file with error handling"""
    try:
        with open(CONFIG_PATH, "w", encoding='utf-8') as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except (IOError, TypeError) as e:
        raise ConfigError(f"Failed to save configuration: {str(e)}")