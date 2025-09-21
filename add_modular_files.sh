# simpan script lalu jalankan
curl -sS -o add_modular_files.sh "data:" && cat > add_modular_files.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
BRANCH="refactor/modularize"
git checkout -b "$BRANCH"

# create files
mkdir -p cogs

cat > config.py <<'PY'
# config.py
import json
from pathlib import Path
from typing import Dict, Any

CONFIG_PATH = Path("config.json")

def _default_config() -> Dict[str, Any]:
    return {"accounts": {}, "admins": {}}

def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return _default_config()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return _default_config()

def save_config(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def is_admin(user_id: str) -> bool:
    cfg = load_config()
    adm = cfg.get("admins", {}).get(user_id)
    if not adm:
        return False
    # `is_admin` flag indicates admin permission; `authenticated` indicates logged-in admin session
    return bool(adm.get("is_admin", False)) and bool(adm.get("authenticated", False))

def add_admin(user_id: str, password: str) -> bool:
    cfg = load_config()
    if user_id in cfg.get("admins", {}):
        return False
    cfg.setdefault("admins", {})[user_id] = {
        "is_admin": True,
        "password": password,
        "authenticated": False
    }
    save_config(cfg)
    return True

def verify_admin_password(user_id: str, password: str) -> bool:
    cfg = load_config()
    adm = cfg.get("admins", {}).get(user_id)
    if not adm:
        return False
    return adm.get("password") == password

def set_admin_authenticated(user_id: str, value: bool) -> None:
    cfg = load_config()
    if user_id not in cfg.get("admins", {}):
        return
    cfg["admins"][user_id]["authenticated"] = bool(value)
    save_config(cfg)
PY

cat > admin_auth.py <<'PY'
# admin_auth.py
from config import verify_admin_password, set_admin_authenticated, load_config
import logging
logger = logging.getLogger("autopos.admin_auth")

async def admin_login(ctx, password: str) -> bool:
    """
    Verify given password and mark admin session as authenticated.
    Returns True if success, False otherwise.
    """
    try:
        user_id = str(ctx.author.id)
        if verify_admin_password(user_id, password):
            set_admin_authenticated(user_id, True)
            try:
                await ctx.author.send("✅ Admin authenticated.")
            except Exception:
                pass
            return True
        else:
            try:
                await ctx.author.send("❌ Password salah.")
            except Exception:
                pass
            return False
    except Exception as e:
        logger.exception("admin_login error: %s", e)
        return False

async def admin_logout(ctx) -> bool:
    try:
        user_id = str(ctx.author.id)
        set_admin_authenticated(user_id, False)
        try:
            await ctx.author.send("✅ Admin logged out.")
        except Exception:
            pass
        return True
    except Exception as e:
        logger.exception("admin_logout error: %s", e)
        return False
PY

cat > tasks_manager.py <<'PY'
# tasks_manager.py
import asyncio
import random
import logging
from discord.ext import tasks
from config import load_config, save_config
from utils import validate_token
from autopost import send_message  # keep using autopost.send_message as in your repo

logger = logging.getLogger("autopos.tasks")
running_tasks = {}
_BOT = None

def set_bot(bot):
    global _BOT
    _BOT = bot

async def run_setup_continuously(user_id: str, setup_name: str, setup_data: dict, token: str):
    """Loop posting for a single setup. Safe to be created with asyncio.create_task."""
    task_id = f"{user_id}_{setup_name}"
    try:
        while True:
            cfg = load_config()
            user_cfg = cfg.get("accounts", {}).get(user_id, {})
            current_setup = user_cfg.get("setups", {}).get(setup_name, {})

            if not current_setup.get("running", False):
                logger.info("Stopping setup %s for user %s (running flag false)", setup_name, user_id)
                break

            # validate token each cycle
            if not await validate_token(token):
                logger.error("Token invalid for user %s. Disabling setup %s.", user_id, setup_name)
                if user_id in cfg["accounts"] and setup_name in cfg["accounts"][user_id].get("setups", {}):
                    cfg["accounts"][user_id]["setups"][setup_name]["running"] = False
                    save_config(cfg)
                break

            message = current_setup.get("message", "")
            base_interval = int(current_setup.get("interval", 1) * 60)
            random_interval = int(current_setup.get("random_interval", 0) * 60)
            channel_id = current_setup.get("channel")

            if not channel_id:
                logger.error("No channel configured for %s:%s", user_id, setup_name)
                break

            logger.info("Posting for user %s setup %s -> channel %s", user_id, setup_name, channel_id)
            try:
                success = await send_message(token, str(channel_id).strip(), message)
                if not success:
                    logger.error("send_message returned False for %s %s", user_id, setup_name)
            except Exception as e:
                logger.exception("Exception sending message for %s:%s -> %s", user_id, setup_name, e)

            wait = base_interval + random.randint(0, random_interval)
            logger.info("Waiting %s seconds for next cycle of %s:%s", wait, user_id, setup_name)
            await asyncio.sleep(wait)

    except asyncio.CancelledError:
        logger.info("Task cancelled %s", task_id)
        raise
    except Exception as e:
        logger.exception("Unexpected error in run_setup_continuously %s: %s", task_id, e)
        # backoff to avoid busy-loop on crashes
        await asyncio.sleep(60)
    finally:
        running_tasks.pop(task_id, None)


# startup loop that runs once at bot start to spawn tasks for active setups
@tasks.loop(seconds=2)
async def _startup_manager():
    # stop self immediately (we only want to run its body once on start)
    _startup_manager.stop()
    cfg = load_config()
    for user_id, udata in cfg.get("accounts", {}).items():
        if "setups" not in udata:
            continue
        token = udata.get("token")
        if not token:
            logger.info("User %s has no token, skipping", user_id)
            continue
        for setup_name, setup_data in udata.get("setups", {}).items():
            if not setup_data.get("running", False):
                continue
            task_id = f"{user_id}_{setup_name}"
            if task_id in running_tasks:
                continue
            # create and store task
            running_tasks[task_id] = asyncio.create_task(run_setup_continuously(user_id, setup_name, setup_data, token))
            logger.info("Started task %s", task_id)

def start_startup_manager(bot):
    """
    Call this from main.on_ready: set bot and start the manager.
    Example: from tasks_manager import set_bot, start_startup_manager
             set_bot(bot)
             start_startup_manager()
    """
    set_bot(bot)
    if not _startup_manager.is_running():
        _startup_manager.start()
PY

cat > cogs/__init__.py <<'PY'
# cogs/__init__.py
# package marker for cogs
PY

cat > cogs/admin_cog.py <<'PY'
# cogs/admin_cog.py
from discord.ext import commands
import discord
import logging
from subscription import PACKAGES, create_subscription
from config import is_admin, add_admin, load_config
from utils import send_ephemeral
from admin_auth import admin_login, admin_logout
import asyncio

logger = logging.getLogger("autopos.cogs.admin")

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="quick_sub")
    @commands.check(lambda ctx: is_admin(str(ctx.author.id)))
    async def quick_sub(self, ctx, package_type: str, user_id: str):
        try:
            if package_type not in PACKAGES:
                await ctx.send(f"❌ Package tidak valid. Pilihan: {', '.join(PACKAGES.keys())}")
                return
            package = PACKAGES[package_type]
            sub_id = create_subscription(user_id, package_type, package["days"])
            await ctx.send(f"✅ Subscription created!\nID: `{sub_id}`\nFor: <@{user_id}>\nPackage: {package['name']}")
        except Exception as e:
            logger.exception("quick_sub error: %s", e)
            await ctx.send("❌ Error saat membuat subscription.")

    @commands.command(name="generate_sub")
    @commands.has_permissions(administrator=True)
    async def generate_sub(self, ctx, package_type: str, user_id: str = None):
        # keep behavior similar to original main; send DM to admin and user
        try:
            if package_type not in PACKAGES:
                await send_ephemeral(ctx, f"❌ Package tidak valid. Pilihan: {', '.join(PACKAGES.keys())}")
                return
            target_user_id = user_id or str(ctx.author.id)
            package = PACKAGES[package_type]
            sub_id = create_subscription(target_user_id, package_type, package["days"])
            # admin embed
            embed_admin = discord.Embed(title="✅ Subscription Created", color=discord.Color.green())
            embed_admin.add_field(name="Subscription ID", value=f"`{sub_id}`", inline=False)
            embed_admin.add_field(name="Package", value=package["name"], inline=True)
            embed_admin.add_field(name="Duration", value=f"{package['days']} hari", inline=True)
            embed_admin.add_field(name="Price", value=f"Rp {package['price']:,}", inline=True)
            embed_admin.add_field(name="For User ID", value=target_user_id, inline=False)
            await ctx.author.send(embed=embed_admin)
            # try DM user
            if user_id and user_id != str(ctx.author.id):
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    embed_user = discord.Embed(title="🎉 Subscription Baru", color=discord.Color.blue())
                    embed_user.add_field(name="Subscription ID", value=f"`{sub_id}`", inline=False)
                    embed_user.add_field(name="Package", value=package["name"], inline=True)
                    embed_user.add_field(name="Duration", value=f"{package['days']} hari", inline=True)
                    embed_user.add_field(name="Status", value="✅ AKTIF", inline=True)
                    embed_user.add_field(name="Cara Login", value="Gunakan `!login` dan ikuti instruksi", inline=False)
                    await user.send(embed=embed_user)
                    await send_ephemeral(ctx, f"✅ Subscription ID telah dikirim ke admin dan user <@{user_id}>")
                except (discord.NotFound, discord.Forbidden):
                    await send_ephemeral(ctx, f"✅ Subscription ID dibuat untuk user {user_id}, tetapi tidak bisa mengirim DM ke user tersebut.")
                except ValueError:
                    await send_ephemeral(ctx, f"❌ User ID tidak valid: {user_id}")
            else:
                await send_ephemeral(ctx, "✅ Subscription ID telah dikirim via DM (hanya ke admin).")
        except Exception as e:
            logger.exception("generate_sub error: %s", e)
            await send_ephemeral(ctx, f"❌ Error: {str(e)}")

    @commands.command(name="admin_login")
    async def admin_login_cmd(self, ctx, *, password: str = None):
        try:
            if not password:
                try:
                    await ctx.author.send("🔐 **Admin Login**\nSilakan kirim password admin di DM ini:")
                    await ctx.send("📩 Silakan cek DM untuk memasukkan password admin.")
                except discord.Forbidden:
                    await ctx.send("❌ Tidak bisa mengirim DM. Pastikan DM terbuka.")
                    return

                def check(m):
                    return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)

                try:
                    msg = await self.bot.wait_for('message', timeout=60.0, check=check)
                    password = msg.content.strip()
                except asyncio.TimeoutError:
                    await ctx.author.send("⏰ Waktu login habis.")
                    return

            success = await admin_login(ctx, password)
            if success:
                await send_ephemeral(ctx, "✅ Admin login berhasil.")
            else:
                await send_ephemeral(ctx, "❌ Admin login gagal.")
        except Exception as e:
            logger.exception("admin_login_cmd error: %s", e)
            await send_ephemeral(ctx, "❌ Terjadi error saat login admin.")

    @commands.command(name="admin_logout")
    async def admin_logout_cmd(self, ctx):
        try:
            await admin_logout(ctx)
            await send_ephemeral(ctx, "✅ Admin logged out.")
        except Exception as e:
            logger.exception("admin_logout_cmd error: %s", e)
            await send_ephemeral(ctx, "❌ Terjadi error saat logout admin.")

    @commands.command(name="create_admin")
    @commands.is_owner()
    async def create_admin_cmd(self, ctx, user_id: str, *, password: str):
        try:
            if add_admin(user_id, password):
                await ctx.author.send(f"✅ Admin {user_id} berhasil dibuat!")
            else:
                await ctx.author.send(f"❌ Admin {user_id} sudah ada atau error.")
        except Exception as e:
            logger.exception("create_admin error: %s", e)
            await ctx.author.send("❌ Terjadi error saat membuat admin.")

    @commands.command(name="admin_status")
    async def admin_status(self, ctx):
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
            logger.exception("admin_status error: %s", e)
            await ctx.author.send("❌ Terjadi error saat memeriksa status admin.")


def setup(bot):
    bot.add_cog(AdminCog(bot))
PY

cat > cogs/user_cog.py <<'PY'
# cogs/user_cog.py
from discord.ext import commands
import discord
import asyncio
import logging
from auth import login_with_subscription, logout_user, is_logged_in, get_subscription_info
from utils import send_ephemeral
from models import MenuView
from config import load_config
import datetime

logger = logging.getLogger("autopos.cogs.user")

class UserCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="login")
    async def login_cmd(self, ctx):
        try:
            if is_logged_in(str(ctx.author.id)):
                await send_ephemeral(ctx, "ℹ️ Anda sudah login. Gunakan `!logout` untuk logout terlebih dahulu.")
                return

            try:
                await ctx.author.send("🔐 **Login System**\nSilakan kirim token Discord Anda dan Subscription ID dengan format:\n`token|subscription_id`\n\nContoh: `mfa.xxxxx|ABC12345`\n\n⚠️ **PERINGATAN:** Jangan bagikan token Anda kepada siapapun!")
                await send_ephemeral(ctx, "📩 Silakan cek DM untuk melanjutkan login.")
            except discord.Forbidden:
                await send_ephemeral(ctx, "❌ Saya tidak bisa mengirim DM kepada Anda. Pastikan DM Anda terbuka.")
                return

            def check(m):
                return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)

            try:
                msg = await self.bot.wait_for('message', timeout=120.0, check=check)
                content = msg.content.strip()
                if '|' not in content:
                    await ctx.author.send("❌ Format salah. Gunakan format: `token|subscription_id`")
                    return
                token, subscription_id = content.split('|', 1)
                token = token.strip()
                subscription_id = subscription_id.strip()
                success = await login_with_subscription(ctx, token, subscription_id)
                if success:
                    sub_info = get_subscription_info(str(ctx.author.id))
                    if sub_info:
                        end_date = sub_info["end_date"][:10]
                        await ctx.author.send(f"✅ Login berhasil! Subscription aktif hingga {end_date}")
            except asyncio.TimeoutError:
                await ctx.author.send("⏰ Waktu login habis. Silakan coba lagi dengan command `!login`.")
        except Exception as e:
            logger.exception("login command error: %s", e)
            await send_ephemeral(ctx, "❌ Terjadi error saat login.")

    @commands.command(name="logout")
    async def logout_cmd(self, ctx):
        try:
            success = await logout_user(ctx)
            if success:
                await send_ephemeral(ctx, "✅ Anda telah logout dari sistem.")
        except Exception as e:
            logger.exception("logout error: %s", e)
            await send_ephemeral(ctx, "❌ Terjadi error saat logout.")

    @commands.command(name="mystatus")
    async def mystatus_cmd(self, ctx):
        try:
            user_id = str(ctx.author.id)
            if is_logged_in(user_id):
                sub_info = get_subscription_info(user_id)
                if sub_info:
                    start_date = sub_info["start_date"][:10]
                    end_date = sub_info["end_date"][:10]
                    from datetime import datetime
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
            logger.exception("mystatus error: %s", e)
            await send_ephemeral(ctx, "❌ Terjadi error saat memeriksa status.")

    @commands.command(name="packages")
    async def packages_cmd(self, ctx):
        try:
            from subscription import PACKAGES
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
            logger.exception("packages error: %s", e)
            await send_ephemeral(ctx, "❌ Terjadi error saat mengambil daftar paket.")

    @commands.command(name="menu")
    @commands.has_permissions(administrator=True)
    async def menu_cmd(self, ctx):
        try:
            if not is_logged_in(str(ctx.author.id)):
                await send_ephemeral(ctx, "❌ Anda harus login terlebih dahulu dengan `!login`")
                return
            cfg = load_config()
            embed = discord.Embed(
                title="AutoPoster Control Panel",
                description="Gunakan tombol di bawah buat setup & kontrol autopost.",
                color=discord.Color.blurple()
            )
            view = MenuView(cfg)
            message = await ctx.send(embed=embed, view=view)
            # if MenuView needs to know message, it can set it in its own code
        except Exception as e:
            logger.exception("menu error: %s", e)
            await send_ephemeral(ctx, f"Terjadi error saat menampilkan menu: {str(e)}")

def setup(bot):
    bot.add_cog(UserCog(bot))
PY

cat > cogs/setup_cog.py <<'PY'
# cogs/setup_cog.py
from discord.ext import commands
import discord
import logging
from config import load_config, save_config
from utils import send_ephemeral
from tasks_manager import running_tasks
import asyncio

logger = logging.getLogger("autopos.cogs.setup")

class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="list_setups")
    @commands.has_permissions(administrator=True)
    async def list_setups(self, ctx):
        try:
            user_id = str(ctx.author.id)
            cfg = load_config()
            if user_id not in cfg.get("accounts", {}) or not cfg["accounts"][user_id].get("setups"):
                await send_ephemeral(ctx, "Anda belum memiliki setup apapun.")
                return
            setups = cfg["accounts"][user_id]["setups"]
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
            logger.exception("list_setups error: %s", e)
            await send_ephemeral(ctx, f"Terjadi error saat mengambil daftar setup: {str(e)}")

    @commands.command(name="delete_setup")
    @commands.has_permissions(administrator=True)
    async def delete_setup(self, ctx, setup_name: str):
        try:
            user_id = str(ctx.author.id)
            cfg = load_config()
            if user_id not in cfg["accounts"] or setup_name not in cfg["accounts"][user_id].get("setups", {}):
                await send_ephemeral(ctx, f"Setup '{setup_name}' tidak ditemukan.")
                return
            # cancel running task if exists
            task_id = f"{user_id}_{setup_name}"
            task = running_tasks.get(task_id)
            if task:
                task.cancel()
            del cfg["accounts"][user_id]["setups"][setup_name]
            save_config(cfg)
            await send_ephemeral(ctx, f"Setup '{setup_name}' telah dihapus.")
        except Exception as e:
            logger.exception("delete_setup error: %s", e)
            await send_ephemeral(ctx, f"Terjadi error saat menghapus setup: {str(e)}")

    @commands.command(name="start_all")
    @commands.has_permissions(administrator=True)
    async def start_all(self, ctx):
        try:
            user_id = str(ctx.author.id)
            cfg = load_config()
            if user_id not in cfg["accounts"] or not cfg["accounts"][user_id].get("setups"):
                await send_ephemeral(ctx, "Anda belum memiliki setup apapun.")
                return
            token = cfg["accounts"][user_id].get("token")
            from utils import validate_token
            if not token or not await validate_token(token):
                await send_ephemeral(ctx, "Token tidak valid. Silakan set token terlebih dahulu.")
                return
            for setup_name, setup_data in cfg["accounts"][user_id]["setups"].items():
                setup_data["running"] = True
            save_config(cfg)
            await send_ephemeral(ctx, "Semua setup telah diaktifkan.")
        except Exception as e:
            logger.exception("start_all error: %s", e)
            await send_ephemeral(ctx, f"Terjadi error saat mengaktifkan setup: {str(e)}")

    @commands.command(name="stop_all")
    @commands.has_permissions(administrator=True)
    async def stop_all(self, ctx):
        try:
            user_id = str(ctx.author.id)
            cfg = load_config()
            if user_id not in cfg["accounts"] or not cfg["accounts"][user_id].get("setups"):
                await send_ephemeral(ctx, "Anda belum memiliki setup apapun.")
                return
            for setup_name, setup_data in cfg["accounts"][user_id]["setups"].items():
                setup_data["running"] = False
                # cancel running task if exists
                task_id = f"{user_id}_{setup_name}"
                task = running_tasks.get(task_id)
                if task:
                    task.cancel()
            save_config(cfg)
            await send_ephemeral(ctx, "Semua setup telah dihentikan.")
        except Exception as e:
            logger.exception("stop_all error: %s", e)
            await send_ephemeral(ctx, f"Terjadi error saat menghentikan setup: {str(e)}")

def setup(bot):
    bot.add_cog(SetupCog(bot))
PY

cat > models.py <<'PY'
# models.py
import discord
from discord.ui import View, Button, Select, Modal, InputText

class MenuView(View):
    def __init__(self, config_data: dict = None):
        super().__init__(timeout=None)
        self.config_data = config_data or {}

        # example buttons; wire callbacks in your repo if needed
        self.add_item(Button(label="Create Setup", style=discord.ButtonStyle.primary, custom_id="create_setup"))
        self.add_item(Button(label="List Setups", style=discord.ButtonStyle.secondary, custom_id="list_setups"))

    @discord.ui.button(label="Placeholder", style=discord.ButtonStyle.gray, custom_id="placeholder_btn")
    async def placeholder(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Button clicked (implement callback).", ephemeral=True)

class TokenModal(Modal):
    def __init__(self):
        super().__init__(title="Enter Token & Sub ID")
        self.add_item(InputText(label="Token", placeholder="mfa.xxxxx...", style=discord.InputTextStyle.short))
        self.add_item(InputText(label="Subscription ID", placeholder="ABC123", style=discord.InputTextStyle.short))

    async def callback(self, interaction: discord.Interaction):
        # implement handling in auth module or where appropriate
        await interaction.response.send_message("Received token (implement handler)", ephemeral=True)

class AdminPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Dashboard", custom_id="admin_dashboard"))
        self.add_item(Button(label="Manage Subs", custom_id="admin_manage_subs"))
        self.add_item(Button(label="Manage Users", custom_id="admin_manage_users"))

    @discord.ui.button(label="Dashboard (placeholder)", style=discord.ButtonStyle.primary, custom_id="admin_dashboard_btn")
    async def dashboard(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Admin dashboard (implement).", ephemeral=True)
PY

# add & commit
git add config.py admin_auth.py tasks_manager.py models.py cogs
git commit -m "refactor(modular): add cogs, tasks manager, admin auth, config & models"
echo "Created branch '$BRANCH' with new files. Review, then push: git push -u origin $BRANCH"
SH
chmod +x add_modular_files.sh
echo "Script 'add_modular_files.sh' created. Run './add_modular_files.sh' to add files and commit on branch refactor/modularize."
