import os
import asyncio
import discord
import random
from dotenv import load_dotenv
from discord.ext import commands, tasks
from autopost import send_message
from datetime import datetime
from discord.ui import View, Button, Select
from subscription import create_subscription, PACKAGES, get_subscription_info, load_subscriptions
from typing import Dict, Any
import logging

# Load environment variables from .env file
load_dotenv()

# Import modul-modul kita
from config import load_config, save_config, is_admin, add_admin
from utils import setup_logger, validate_token
from models import MenuView, TokenModal
from auth import login_with_subscription, logout_user, is_logged_in, get_subscription_info
from admin_auth import admin_login, admin_logout
from admin_models import AdminPanelView
# Setup logging
logger = setup_logger()
logger = logging.getLogger(__name__)

# Bot initialization
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
config = load_config()

# Dictionary untuk menyimpan task yang sedang berjalan
running_tasks = {}

# Fungsi untuk mengirim pesan ephemeral (hanya visible untuk user)
async def send_ephemeral(ctx, message, delete_after=None):
    """Send ephemeral message using followup for commands"""
    try:
        # Coba kirim sebagai interaction response jika memungkinkan
        if hasattr(ctx, 'respond'):
            await ctx.respond(message, ephemeral=True, delete_after=delete_after)
        else:
            # Fallback: kirim regular message dan delete setelah beberapa detik
            msg = await ctx.send(message)
            if delete_after:
                await asyncio.sleep(delete_after)
                await msg.delete()
    except Exception as e:
        logger.error("Error sending ephemeral message: %s", e)
        await ctx.send(message)

# Fungsi baru untuk menjalankan satu setup secara kontinu
async def run_setup_continuously(user_id, setup_name, setup_data, token):
    """Jalankan satu setup secara terus menerus"""
    task_id = f"{user_id}_{setup_name}"
    
    try:
        while True:
            # Periksa status running dari config terbaru
            current_config = load_config()
            current_user = current_config["accounts"].get(user_id, {})
            current_setup = current_user.get("setups", {}).get(setup_name, {})
            
            if not current_setup.get("running", False):
                logger.info("Setup %s user %s dihentikan", setup_name, user_id)
                break

            message = setup_data["message"]
            base_interval = int(setup_data["interval"] * 60)  # menit -> detik
            channel_id = setup_data.get("channel")
            random_interval = int(setup_data.get("random_interval", 0) * 60)  # menit -> detik

            if not channel_id:
                logger.error("Setup %s user %s tidak punya channel", setup_name, user_id)
                break

            # Validate token before proceeding
            if not await validate_token(token):
                logger.error("Token tidak valid untuk user %s. Menonaktifkan setup %s.", user_id, setup_name)
                # Update config untuk nonaktifkan setup ini
                config = load_config()
                if user_id in config["accounts"] and setup_name in config["accounts"][user_id]["setups"]:
                    config["accounts"][user_id]["setups"][setup_name]["running"] = False
                    save_config(config)
                break

            # Kirim pesan ke channel
            logger.info("User %s - Setup %s: Mengirim pesan ke channel %s", user_id, setup_name, channel_id)
            success = await send_message(token, channel_id.strip(), message)
            if not success:
                logger.error("Gagal mengirim pesan ke channel %s", channel_id)

            # Delay sebelum cycle berikutnya
            random_extra = random.randint(0, random_interval)
            total_wait = base_interval + random_extra
            logger.info("User %s - Setup %s: Menunggu %s detik sebelum cycle berikutnya",
                        user_id, setup_name, total_wait)
            await asyncio.sleep(total_wait)

    except KeyError as e:
        logger.error("Config tidak valid untuk setup %s user %s: %s", setup_name, user_id, e)
    except Exception as e:
        logger.error("Error tidak terduga pada setup %s user %s: %s", setup_name, user_id, e)
        await asyncio.sleep(60)  # Tunggu 1 menit sebelum mencoba lagi
    finally:
        # Hapus task dari dictionary ketika selesai
        if task_id in running_tasks:
            del running_tasks[task_id]

# Task untuk memulai semua setup yang running saat bot start
@tasks.loop(seconds=2)
async def startup_manager():
    """Manager untuk memulai semua setup yang running saat bot start"""
    startup_manager.stop()  # Hanya jalankan sekali
    
    try:
        cfg = load_config()
        for user_id, user_data in cfg["accounts"].items():
            if "setups" not in user_data:
                continue

            token = user_data.get("token")
            if not token:
                logger.error("User %s tidak memiliki token", user_id)
                continue

            for setup_name, setup_data in user_data["setups"].items():
                if not setup_data.get("running", False):
                    continue
                
                # Jalankan setup yang running
                task_id = f"{user_id}_{setup_name}"
                if task_id not in running_tasks:
                    task = asyncio.create_task(
                        run_setup_continuously(user_id, setup_name, setup_data, token)
                    )
                    running_tasks[task_id] = task
                    logger.info("Memulai setup %s untuk user %s", setup_name, user_id)
                    
    except Exception as e:
        logger.error("Error dalam startup_manager: %s", e)
#
# Import admin models
from admin_models import AdminPanelView

# Command untuk admin panel
@bot.command()
@commands.check(lambda ctx: is_admin(str(ctx.author.id)))
async def admin_panel(ctx: commands.Context):
    """Open Admin Control Panel"""
    try:
        embed = discord.Embed(
            title="🛠️ Admin Control Panel",
            description="Pilih tool admin yang ingin digunakan:",
            color=discord.Color.gold()
        )
        embed.add_field(name="📊 Dashboard", value="Lihat statistik sistem", inline=True)
        embed.add_field(name="🎫 Manage Subs", value="Buat & kelola subscription", inline=True)
        embed.add_field(name="👥 Manage Users", value="Lihat & cari users", inline=True)
        embed.add_field(name="⚙️ System", value="Tools system admin", inline=True)
        
        await ctx.send(embed=embed, view=AdminPanelView())
        
    except Exception as e:
        logger.error("Error in admin_panel command: %s", e)
        await ctx.send("❌ Terjadi error saat membuka admin panel.")
    
# Quick command untuk buat subscription
@bot.command()
@commands.check(lambda ctx: is_admin(str(ctx.author.id)))
async def quick_sub(ctx: commands.Context, package_type: str, user_id: str):
    """Quick create subscription"""
    try:
        if package_type not in PACKAGES:
            await ctx.send(f"❌ Package tidak valid. Pilihan: {', '.join(PACKAGES.keys())}")
            return
            
        package = PACKAGES[package_type]
        sub_id = create_subscription(user_id, package_type, package["days"])
        
        await ctx.send(f"✅ Subscription created!\nID: `{sub_id}`\nFor: <@{user_id}>\nPackage: {package['name']}")
        
    except Exception as e:
        logger.error("Error in quick_sub command: %s", e)
        await ctx.send(f"❌ Error: {str(e)}")
        
# Command admin untuk generate subscription ID
@bot.command()
@commands.has_permissions(administrator=True)
async def generate_sub(ctx: commands.Context, package_type: str, user_id: str = None):
    """Generate subscription ID untuk customer"""
    try:
        if package_type not in PACKAGES:
            await send_ephemeral(ctx, f"❌ Package tidak valid. Pilihan: {', '.join(PACKAGES.keys())}")
            return
            
        target_user_id = user_id or str(ctx.author.id)
        package = PACKAGES[package_type]
        
        sub_id = create_subscription(target_user_id, package_type, package["days"])
        
        # Embed untuk admin
        embed_admin = discord.Embed(title="✅ Subscription Created", color=discord.Color.green())
        embed_admin.add_field(name="Subscription ID", value=f"`{sub_id}`", inline=False)
        embed_admin.add_field(name="Package", value=package["name"], inline=True)
        embed_admin.add_field(name="Duration", value=f"{package['days']} hari", inline=True)
        embed_admin.add_field(name="Price", value=f"Rp {package['price']:,}", inline=True)
        embed_admin.add_field(name="For User ID", value=target_user_id, inline=False)
        embed_admin.set_footer(text="Subscription ID juga telah dikirim ke user")
        
        # Embed untuk user
        embed_user = discord.Embed(title="🎉 Subscription Baru", color=discord.Color.blue())
        embed_user.add_field(name="Subscription ID", value=f"`{sub_id}`", inline=False)
        embed_user.add_field(name="Package", value=package["name"], inline=True)
        embed_user.add_field(name="Duration", value=f"{package['days']} hari", inline=True)
        embed_user.add_field(name="Status", value="✅ AKTIF", inline=True)
        embed_user.add_field(name="Cara Login", value="Gunakan `!login` dan ikuti instruksi", inline=False)
        embed_user.set_footer(text="Simpan Subscription ID Anda dengan aman!")
        
        # Kirim ke admin
        await ctx.author.send(embed=embed_admin)
        
        # Kirim ke user target (jika user_id berbeda dengan admin)
        if user_id and user_id != str(ctx.author.id):
            try:
                user = await bot.fetch_user(int(user_id))
                await user.send(embed=embed_user)
                await send_ephemeral(ctx, f"✅ Subscription ID telah dikirim ke admin dan user <@{user_id}>")
            except (discord.NotFound, discord.Forbidden):
                await send_ephemeral(ctx, f"✅ Subscription ID dibuat untuk user {user_id}, tetapi tidak bisa mengirim DM ke user tersebut.")
            except ValueError:
                await send_ephemeral(ctx, f"❌ User ID tidak valid: {user_id}")
        else:
            await send_ephemeral(ctx, "✅ Subscription ID telah dikirim via DM (hanya ke admin).")
        
    except Exception as e:
        logger.error("Error in generate_sub command: %s", e)
        await send_ephemeral(ctx, f"❌ Error: {str(e)}")

# Command untuk admin login
@bot.command()
async def admin_login_cmd(ctx: commands.Context, *, password: str = None):
    """Login sebagai admin"""
    try:
        if not password:
            # Minta password via DM untuk keamanan
            try:
                await ctx.author.send("🔐 **Admin Login**\nSilakan kirim password admin di DM ini:")
                await ctx.send("📩 Silakan cek DM untuk memasukkan password admin.")
            except discord.Forbidden:
                await ctx.send("❌ Tidak bisa mengirim DM. Pastikan DM terbuka.")
                return
                
            def check(m):
                return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
                
            try:
                msg = await bot.wait_for('message', timeout=60.0, check=check)
                password = msg.content.strip()
            except asyncio.TimeoutError:
                await ctx.author.send("⏰ Waktu login habis.")
                return
                
        success = await admin_login(ctx, password)
        
    except Exception as e:
        logger.error("Error in admin_login command: %s", e)
        await ctx.send("❌ Terjadi error saat login admin.")
# Command untuk debug config
@bot.command()
@commands.is_owner()
async def debug_config(ctx: commands.Context):
    """Debug config structure (Owner only)"""
    try:
        config = load_config()
        
        embed = discord.Embed(title="🔧 Debug Config", color=discord.Color.blue())
        embed.add_field(name="Accounts", value=f"{len(config.get('accounts', {}))} users", inline=True)
        embed.add_field(name="Admins", value=f"{len(config.get('admins', {}))} admins", inline=True)
        
        admin_list = []
        for user_id, admin_data in config.get('admins', {}).items():
            admin_list.append(f"<@{user_id}> - {admin_data.get('is_admin', False)}")
        
        if admin_list:
            embed.add_field(name="Admin List", value="\n".join(admin_list[:5]), inline=False)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error("Error in debug_config: %s", e)
        await ctx.send(f"❌ Error: {str(e)}")

# Command untuk admin logout
@bot.command()
async def admin_logout_cmd(ctx: commands.Context):
    """Logout sebagai admin"""
    try:
        success = await admin_logout(ctx)
    except Exception as e:
        logger.error("Error in admin_logout command: %s", e)
        await ctx.author.send("❌ Terjadi error saat logout admin.")

# Command untuk membuat admin baru (hanya untuk owner)
@bot.command()
@commands.is_owner()
async def create_admin(ctx: commands.Context, user_id: str, *, password: str):
    """Buat admin baru (Owner only)"""
    try:
        if add_admin(user_id, password):
            await ctx.author.send(f"✅ Admin {user_id} berhasil dibuat!")
        else:
            await ctx.author.send(f"❌ Admin {user_id} sudah ada atau error.")
    except Exception as e:
        logger.error("Error in create_admin command: %s", e)
        await ctx.author.send("❌ Terjadi error saat membuat admin.")

# Command untuk cek status admin
@bot.command()
async def admin_status(ctx: commands.Context):
    """Cek status admin Anda"""
    try:
        user_id = str(ctx.author.id)
        
        if is_admin(user_id):
            embed = discord.Embed(title="🛡️ Status Admin", color=discord.Color.gold())
            embed.add_field(name="Status", value="✅ ADMIN TERAUTENTIKASI", inline=False)
            embed.add_field(name="User ID", value=user_id, inline=True)
            embed.add_field(name="Permission", value="Full Access", inline=True)
            await ctx.author.send(embed=embed)
        else:
            embed = discord.Embed(title="🛡️ Status Admin", color=discord.Color.red())
            embed.add_field(name="Status", value="❌ BUKAN ADMIN", inline=False)
            embed.add_field(name="Action", value="Gunakan `!admin_login` jika memiliki akses", inline=True)
            await ctx.author.send(embed=embed)
            
    except Exception as e:
        logger.error("Error in admin_status command: %s", e)
        await ctx.author.send("❌ Terjadi error saat memeriksa status admin.")

# Command untuk login dengan subscription
@bot.command()
async def login(ctx: commands.Context):
    """Login dengan token dan subscription ID"""
    try:
        # Cek apakah sudah login
        if is_logged_in(str(ctx.author.id)):
            await send_ephemeral(ctx, "ℹ️ Anda sudah login. Gunakan `!logout` untuk logout terlebih dahulu.")
            return
            
        # Minta token dan subscription ID via DM
        try:
            await ctx.author.send("🔐 **Login System**\nSilakan kirim token Discord Anda dan Subscription ID dengan format:\n`token|subscription_id`\n\nContoh: `mfa.xxxxx|ABC12345`\n\n⚠️ **PERINGATAN:** Jangan bagikan token Anda kepada siapapun!")
            await send_ephemeral(ctx, "📩 Silakan cek DM untuk melanjutkan login.")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Saya tidak bisa mengirim DM kepada Anda. Pastikan DM Anda terbuka.")
            return
            
        # Fungsi untuk menunggu response di DM
        def check(m):
            return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
            
        try:
            msg = await bot.wait_for('message', timeout=120.0, check=check)
            content = msg.content.strip()
            
            if '|' not in content:
                await ctx.author.send("❌ Format salah. Gunakan format: `token|subscription_id`")
                return
                
            token, subscription_id = content.split('|', 1)
            token = token.strip()
            subscription_id = subscription_id.strip()
            
            # Validasi dan login
            success = await login_with_subscription(ctx, token, subscription_id)
            if success:
                sub_info = get_subscription_info(str(ctx.author.id))
                if sub_info:
                    end_date = sub_info["end_date"][:10]
                    await ctx.author.send(f"✅ Login berhasil! Subscription aktif hingga {end_date}")
                
        except asyncio.TimeoutError:
            await ctx.author.send("⏰ Waktu login habis. Silakan coba lagi dengan command `!login`.")
            
    except Exception as e:
        logger.error("Error in login command: %s", e)
        await send_ephemeral(ctx, "❌ Terjadi error saat login.")

# Command untuk cek status subscription
@bot.command()
async def mystatus(ctx: commands.Context):
    """Cek status subscription Anda"""
    try:
        user_id = str(ctx.author.id)
        
        if is_logged_in(user_id):
            sub_info = get_subscription_info(user_id)
            
            if sub_info:
                start_date = sub_info["start_date"][:10]
                end_date = sub_info["end_date"][:10]
                days_left = (datetime.fromisoformat(sub_info["end_date"]) - datetime.now()).days
                
                embed = discord.Embed(title="📊 Status Subscription", color=discord.Color.green())
                embed.add_field(name="Subscription ID", value=f"`{sub_info.get('subscription_id', 'N/A')}`", inline=False)
                embed.add_field(name="Package", value=sub_info.get("package_type", "N/A"), inline=True)
                embed.add_field(name="Status", value="✅ AKTIF", inline=True)
                embed.add_field(name="Mulai", value=start_date, inline=True)
                embed.add_field(name="Berakhir", value=end_date, inline=True)
                embed.add_field(name="Sisa Hari", value=f"{days_left} hari", inline=True)
                
                await ctx.send(embed=embed)
            else:
                await send_ephemeral(ctx, "❌ Tidak ada info subscription ditemukan.")
        else:
            embed = discord.Embed(title="📊 Status Subscription", color=discord.Color.red())
            embed.add_field(name="Status", value="❌ BELUM LOGIN", inline=False)
            embed.add_field(name="Action", value="Gunakan `!login` untuk login dengan subscription ID", inline=True)
            
            await ctx.send(embed=embed)
            
    except Exception as e:
        logger.error("Error in mystatus command: %s", e)
        await send_ephemeral(ctx, "❌ Terjadi error saat memeriksa status.")

# Command untuk melihat packages available
@bot.command()
async def packages(ctx: commands.Context):
    """Lihat paket subscription yang tersedia"""
    try:
        embed = discord.Embed(title="📦 Paket Subscription", color=discord.Color.blue())
        
        for package_id, package in PACKAGES.items():
            embed.add_field(
                name=f"{package['name']} - Rp {package['price']:,}",
                value=f"{package['days']} hari akses\nID: `{package_id}`",
                inline=False
            )
            
        embed.set_footer(text="Hubungi admin untuk membeli package")
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error("Error in packages command: %s", e)
        await send_ephemeral(ctx, "❌ Terjadi error.")

# Command untuk logout
@bot.command()
async def logout(ctx: commands.Context):
    """Logout dari sistem"""
    try:
        success = await logout_user(ctx)
        if success:
            await send_ephemeral(ctx, "✅ Anda telah logout dari sistem.")
    except Exception as e:
        logger.error("Error in logout command: %s", e)
        await send_ephemeral(ctx, "❌ Terjadi error saat logout.")

# Command !menu dengan subscription check
@bot.command()
@commands.has_permissions(administrator=True)
async def menu(ctx: commands.Context):
    """Display the control panel menu"""
    try:
        # Cek apakah user sudah login
        if not is_logged_in(str(ctx.author.id)):
            await send_ephemeral(ctx, "❌ Anda harus login terlebih dahulu dengan `!login`")
            return
            
        config = load_config()
        embed = discord.Embed(
            title="AutoPoster Control Panel",
            description="Gunakan tombol di bawah buat setup & kontrol autopost.",
            color=discord.Color.blurple()
        )
        view = MenuView(config)
        message = await ctx.send(embed=embed, view=view)
        view.set_menu_message(message)
    except Exception as e:
        logger.error("Error in menu command: %s", e, exc_info=True)
        await send_ephemeral(ctx, f"Terjadi error saat menampilkan menu: {str(e)}")

# Command untuk list setups
@bot.command()
@commands.has_permissions(administrator=True)
async def list_setups(ctx: commands.Context):
    try:
        user_id = str(ctx.author.id)
        config = load_config()

        if user_id not in config["accounts"] or not config["accounts"][user_id].get("setups"):
            await send_ephemeral(ctx, "Anda belum memiliki setup apapun.")
            return

        setups = config["accounts"][user_id]["setups"]
        embed = discord.Embed(title="Daftar Setup Anda", color=discord.Color.blue())

        for name, data in setups.items():
            status = "🟢 AKTIF" if data.get("running", False) else "🔴 NON-AKTIF"
            channel = data.get("channel", "Belum diatur")
            embed.add_field(
                name=name,
                value=f"{status}\nChannel: {channel}\nInterval: {data.get('interval', 1)} menit",
                inline=False
            )

        await ctx.send(embed=embed)

    except Exception as e:
        logger.error("Error in list_setups command: %s", e)
        await send_ephemeral(ctx, f"Terjadi error saat mengambil daftar setup: {str(e)}")

# Command untuk delete setup
@bot.command()
@commands.has_permissions(administrator=True)
async def delete_setup(ctx: commands.Context, setup_name: str):
    try:
        user_id = str(ctx.author.id)
        config = load_config()

        if user_id not in config["accounts"] or setup_name not in config["accounts"][user_id].get("setups", {}):
            await send_ephemeral(ctx, f"Setup '{setup_name}' tidak ditemukan.")
            return

        del config["accounts"][user_id]["setups"][setup_name]
        save_config(config)

        await send_ephemeral(ctx, f"Setup '{setup_name}' telah dihapus.")

    except Exception as e:
        logger.error("Error in delete_setup command: %s", e)
        await send_ephemeral(ctx, f"Terjadi error saat menghapus setup: {str(e)}")

# Command untuk start semua setups
@bot.command()
@commands.has_permissions(administrator=True)
async def start_all(ctx: commands.Context):
    try:
        user_id = str(ctx.author.id)
        config = load_config()

        if user_id not in config["accounts"] or not config["accounts"][user_id].get("setups"):
            await send_ephemeral(ctx, "Anda belum memiliki setup apapun.")
            return

        token = config["accounts"][user_id].get("token")
        if not token or not await validate_token(token):
            await send_ephemeral(ctx, "Token tidak valid. Silakan set token terlebih dahulu.")
            return

        for setup_name, setup_data in config["accounts"][user_id]["setups"].items():
            setup_data["running"] = True

        save_config(config)
        await send_ephemeral(ctx, "Semua setup telah diaktifkan.")

    except Exception as e:
        logger.error("Error in start_all command: %s", e)
        await send_ephemeral(ctx, f"Terjadi error saat mengaktifkan setup: {str(e)}")

# Command untuk stop semua setups
@bot.command()
@commands.has_permissions(administrator=True)
async def stop_all(ctx: commands.Context):
    try:
        user_id = str(ctx.author.id)
        config = load_config()

        if user_id not in config["accounts"] or not config["accounts"][user_id].get("setups"):
            await send_ephemeral(ctx, "Anda belum memiliki setup apapun.")
            return

        for setup_name, setup_data in config["accounts"][user_id]["setups"].items():
            setup_data["running"] = False

        save_config(config)
        await send_ephemeral(ctx, "Semua setup telah dihentikan.")

    except Exception as e:
        logger.error("Error in stop_all command: %s", e)
        await send_ephemeral(ctx, f"Terjadi error saat menghentikan setup: {str(e)}")

# Bot Events
@bot.event
async def on_ready():
    try:
        logger.info("%s sudah online!", bot.user)
        # Mulai manager startup
        if not startup_manager.is_running():
            startup_manager.start()
    except Exception as e:
        logger.error("Error in on_ready: %s", e)

@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CommandNotFound):
        return
    logger.error("Command error: %s", error)
    await send_ephemeral(ctx, "Terjadi error saat menjalankan command")

# Run the Bot
if __name__ == "__main__":
    try:
        TOKEN = os.getenv("DISCORD_BOT_TOKEN")
        if not TOKEN:
            raise ValueError("Token tidak ditemukan. Pastikan DISCORD_BOT_TOKEN di-set di file .env.")
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot dihentikan oleh user")
    except discord.LoginError:
        logger.error("Token bot tidak valid")
    except Exception as e:
        logger.error("Error starting bot: %s", e)