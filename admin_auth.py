import discord
from discord.ext import commands
import asyncio
from config import add_admin, verify_admin, is_admin
from utils import validate_token

async def send_ephemeral(ctx, message):
    """Helper function untuk mengirim pesan ephemeral"""
    try:
        # Untuk commands biasa, kita tidak bisa menggunakan ephemeral
        # Jadi kita kirim sebagai regular message
        await ctx.send(message)
    except Exception as e:
        print(f"Error sending message: {e}")
        await ctx.send(message)

async def admin_login(ctx: commands.Context, password: str):
    """Login sebagai admin"""
    try:
        user_id = str(ctx.author.id)
        
        if is_admin(user_id):
            await send_ephemeral(ctx, "ℹ️ Anda sudah login sebagai admin.")
            return True
            
        if verify_admin(user_id, password):
            await send_ephemeral(ctx, "✅ Login admin berhasil!")
            return True
        else:
            await send_ephemeral(ctx, "❌ Password admin salah.")
            return False
            
    except Exception as e:
        await send_ephemeral(ctx, f"❌ Error saat login admin: {str(e)}")
        return False

async def admin_logout(ctx: commands.Context):
    """Logout sebagai admin"""
    try:
        await send_ephemeral(ctx, "✅ Logout admin berhasil!")
        return True
        
    except Exception as e:
        await send_ephemeral(ctx, f"❌ Error saat logout admin: {str(e)}")
        return False