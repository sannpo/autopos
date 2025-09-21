import discord
from discord.ext import commands
import asyncio
import aiohttp
from typing import Optional, Dict, Any
from config import load_config, save_config
from utils import validate_token
from subscription import validate_subscription, get_user_subscription, PACKAGES

async def login_with_subscription(ctx: commands.Context, token: str, subscription_id: str):
    """Login dengan token dan subscription ID"""
    try:
        user_id = str(ctx.author.id)
        
        # Validasi subscription
        if not validate_subscription(subscription_id, user_id):
            await ctx.send("❌ Subscription ID tidak valid atau sudah expired.", ephemeral=True)
            return False
            
        # Validasi token
        if not await validate_token(token):
            await ctx.send("❌ Token tidak valid. Silakan periksa kembali.", ephemeral=True)
            return False
            
        # Simpan ke config
        config = load_config()
        
        if user_id not in config["accounts"]:
            config["accounts"][user_id] = {
                "setups": {}, 
                "token": token,
                "subscription_id": subscription_id
            }
        else:
            config["accounts"][user_id]["token"] = token
            config["accounts"][user_id]["subscription_id"] = subscription_id
            
        save_config(config)
        
        await ctx.send("✅ Login berhasil! Subscription aktif.", ephemeral=True)
        return True
        
    except Exception as e:
        await ctx.send(f"❌ Error saat login: {str(e)}", ephemeral=True)
        return False

async def logout_user(ctx: commands.Context):
    """Logout user"""
    try:
        user_id = str(ctx.author.id)
        config = load_config()
        
        if user_id in config["accounts"]:
            # Hapus token dan subscription reference
            if "token" in config["accounts"][user_id]:
                del config["accounts"][user_id]["token"]
            if "subscription_id" in config["accounts"][user_id]:
                del config["accounts"][user_id]["subscription_id"]
                
            # Jika tidak ada setups, hapus seluruh user
            if not config["accounts"][user_id].get("setups"):
                del config["accounts"][user_id]
                
            save_config(config)
            
        await ctx.send("✅ Logout berhasil!", ephemeral=True)
        return True
        
    except Exception as e:
        await ctx.send(f"❌ Error saat logout: {str(e)}", ephemeral=True)
        return False

def is_logged_in(user_id: str) -> bool:
    """Cek apakah user sudah login dan memiliki subscription aktif"""
    config = load_config()
    user_data = config["accounts"].get(str(user_id), {})
    
    if "token" not in user_data or "subscription_id" not in user_data:
        return False
        
    # Validasi subscription masih aktif
    from subscription import validate_subscription
    return validate_subscription(user_data["subscription_id"], user_id)

def has_active_subscription(user_id: str) -> bool:
    """Cek apakah user memiliki subscription aktif"""
    return is_logged_in(user_id)

def get_subscription_info(user_id: str) -> Optional[Dict]:
    """Dapatkan info subscription user"""
    config = load_config()
    user_data = config["accounts"].get(str(user_id), {})
    
    if "subscription_id" not in user_data:
        return None
        
    from subscription import get_subscription_info
    return get_subscription_info(user_data["subscription_id"])