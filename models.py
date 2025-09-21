import discord
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from config import load_config, save_config
from utils import validate_token
from exceptions import ValidationError

# Setup logger
logger = logging.getLogger(__name__)


async def refresh_menu_message(message: discord.Message):
    """Refresh menu message dengan config terbaru"""
    try:
        if message is None:
            logger.error("Cannot refresh menu: message is None")
            return
            
        new_config = load_config()
        embed = discord.Embed(
            title="AutoPoster Control Panel",
            description="Gunakan tombol di bawah buat setup & kontrol autopost.",
            color=discord.Color.blurple()
        )
        
        # Buat view baru dengan config terbaru dan referensi message
        new_view = MenuView(new_config, message)
        await message.edit(embed=embed, view=new_view)
    except Exception as e:
        logger.error("Error refreshing menu message: %s", e)


class TokenModal(discord.ui.Modal):
    def __init__(self, user_id: str, menu_message: discord.Message):
        super().__init__(title="Set Token User")
        self.user_id = user_id
        self.menu_message = menu_message
        
        config = load_config()
        current_token = config["accounts"].get(user_id, {}).get("token", "")
        
        self.add_item(discord.ui.InputText(
            label="Token User",
            value=current_token,
            placeholder="mfa.xxxxx",
            min_length=50,
            max_length=200
        ))

    async def callback(self, interaction: discord.Interaction):
        try:
            token = self.children[0].value.strip()
            if not token:
                raise ValidationError("Token tidak boleh kosong")
                
            if not await validate_token(token):
                raise ValidationError("Token tidak valid. Silakan periksa kembali.")
                
            # Simpan token di level user
            config = load_config()
            if self.user_id not in config["accounts"]:
                config["accounts"][self.user_id] = {"setups": {}}
                
            config["accounts"][self.user_id]["token"] = token
            save_config(config)
            
            await interaction.response.send_message(
                "Token berhasil disimpan! Sekarang Anda bisa membuat setup.",
                ephemeral=True
            )
            
            # Refresh menu utama
            await refresh_menu_message(self.menu_message)
            
        except ValidationError as e:
            await interaction.response.send_message(
                f"Error validasi: {str(e)}", 
                ephemeral=True
            )
        except Exception as e:
            logger.error("Error dalam TokenModal callback: %s", str(e))
            await interaction.response.send_message(
                "Terjadi error tidak terduga saat menyimpan token", 
                ephemeral=True
            )


class CreateSetupModal(discord.ui.Modal):
    def __init__(self, user_id: str, menu_message: discord.Message):
        super().__init__(title="Buat Setup Baru")
        self.user_id = user_id
        self.menu_message = menu_message
        
        self.add_item(discord.ui.InputText(
            label="Nama Setup",
            placeholder="Masukkan nama setup",
            required=True
        ))

    async def callback(self, interaction: discord.Interaction):
        try:
            setup_name = self.children[0].value.strip()
            if not setup_name:
                raise ValidationError("Nama setup tidak boleh kosong")
                
            config = load_config()
            
            # Pastikan user sudah memiliki token
            if self.user_id not in config["accounts"] or "token" not in config["accounts"][self.user_id]:
                raise ValidationError("Token belum diatur. Silakan set token terlebih dahulu.")
                
            # Pastikan setup name belum ada
            if setup_name in config["accounts"][self.user_id].get("setups", {}):
                raise ValidationError(f"Setup dengan nama '{setup_name}' sudah ada")
                
            # Buat setup baru
            if "setups" not in config["accounts"][self.user_id]:
                config["accounts"][self.user_id]["setups"] = {}
                
            config["accounts"][self.user_id]["setups"][setup_name] = {
                "channel": "",  # string tunggal
                "message": "example",
                "interval": 1,
                "random_interval": 5,
                "running": False,
                "last_updated": datetime.now().isoformat()
            }

            
            save_config(config)
            
            await interaction.response.send_message(
                f"Setup '{setup_name}' berhasil dibuat! Silakan edit untuk mengatur konfigurasi.",
                ephemeral=True
            )
            
            # Refresh menu utama
            await refresh_menu_message(self.menu_message)
            
        except ValidationError as e:
            await interaction.response.send_message(
                f"Error validasi: {str(e)}", 
                ephemeral=True
            )
        except Exception as e:
            logger.error("Error dalam CreateSetupModal callback: %s", str(e))
            await interaction.response.send_message(
                "Terjadi error tidak terduga saat membuat setup", 
                ephemeral=True
            )


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, user_id: str, setup_name: str, menu_message: discord.Message):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.setup_name = setup_name
        self.menu_message = menu_message
    
    @discord.ui.button(label="Ya, Hapus", style=discord.ButtonStyle.danger)
    async def confirm_delete(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            config = load_config()
            
            # Pastikan setup masih ada
            if (self.user_id not in config["accounts"] or 
                self.setup_name not in config["accounts"][self.user_id].get("setups", {})):
                await interaction.response.send_message(
                    f"Setup '{self.setup_name}' tidak ditemukan.",
                    ephemeral=True
                )
                return
                
            # Hapus setup
            del config["accounts"][self.user_id]["setups"][self.setup_name]
            save_config(config)
            
            await interaction.response.send_message(
                f"Setup '{self.setup_name}' telah dihapus.",
                ephemeral=True
            )
            
            # Refresh menu utama
            await refresh_menu_message(self.menu_message)
            
            # Update message untuk menghapus view
            await interaction.edit_original_response(content=f"Setup '{self.setup_name}' telah dihapus.", view=None)
            
        except Exception as e:
            logger.error("Error in confirm_delete: %s", e)
            await interaction.response.send_message(
                "Terjadi error tidak terduga saat menghapus setup",
                ephemeral=True
            )
    
    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Penghapusan setup dibatalkan.",
            ephemeral=True
        )
        # Update message untuk menghapus view
        await interaction.edit_original_response(content="Penghapusan setup dibatalkan.", view=None)


class SetupModal(discord.ui.Modal):
    def __init__(self, user_id: str, setup_name: str, setup_data: Dict[str, Any], menu_message: discord.Message):
        super().__init__(title=f"Edit Setup: {setup_name}")
        self.user_id = user_id
        self.setup_name = setup_name
        self.setup_data = setup_data
        self.menu_message = menu_message

        # Field channel tunggal
        channel_value = setup_data.get("channel", "")
        self.add_item(discord.ui.InputText(
            label="ID Channel",
            value=channel_value,
            placeholder="123456789012345678",
            min_length=1,
            max_length=30
        ))

        # Field message
        message_value = setup_data.get("message", "")
        self.add_item(discord.ui.InputText(
            label="Pesan",
            value=message_value,
            style=discord.InputTextStyle.long,
            min_length=1,
            max_length=2000
        ))

        # Field interval
        interval_value = str(setup_data.get("interval", 1))
        self.add_item(discord.ui.InputText(
            label="Interval (menit)",
            value=interval_value,
            placeholder="1",
            min_length=1,
            max_length=10
        ))

        # Field random interval
        random_value = str(setup_data.get("random_interval", 0))
        self.add_item(discord.ui.InputText(
            label="Random Interval (menit)",
            value=random_value,
            placeholder="5",
            max_length=10,
            required=False
        ))

    async def callback(self, interaction: discord.Interaction):
        try:
            config = load_config()

            channel = self.children[0].value.strip()
            if not channel:
                raise ValidationError("Channel tidak boleh kosong")

            message = self.children[1].value.strip()
            if not message:
                raise ValidationError("Pesan tidak boleh kosong")

            try:
                interval = float(self.children[2].value.strip())
                if interval <= 0:
                    raise ValidationError("Interval harus lebih besar dari 0")
            except ValueError:
                raise ValidationError("Interval harus berupa angka")

            random_interval = 0
            if self.children[3].value.strip():
                try:
                    random_interval = float(self.children[3].value.strip())
                    if random_interval < 0:
                        raise ValidationError("Random interval tidak boleh negatif")
                except ValueError:
                    raise ValidationError("Random interval harus berupa angka")

            config["accounts"][self.user_id]["setups"][self.setup_name] = {
                "channel": channel,
                "message": message,
                "interval": interval,
                "random_interval": random_interval,
                "running": self.setup_data.get("running", False),
                "last_updated": datetime.now().isoformat()
            }
            save_config(config)

            embed = discord.Embed(
                title="Setup Berhasil Diperbarui",
                color=discord.Color.green()
            )
            embed.add_field(name="Nama Setup", value=self.setup_name, inline=False)
            embed.add_field(name="Channel", value=channel, inline=False)
            embed.add_field(name="Pesan", value=message[:100] + "..." if len(message) > 100 else message, inline=False)
            embed.add_field(name="Interval", value=f"{interval} menit", inline=True)
            embed.add_field(name="Random Interval", value=f"{random_interval} menit", inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)
            await refresh_menu_message(self.menu_message)

        except ValidationError as e:
            await interaction.response.send_message(f"Error validasi: {str(e)}", ephemeral=True)
        except Exception as e:
            logger.error("Error dalam SetupModal callback: %s", str(e))
            await interaction.response.send_message("Terjadi error tidak terduga saat menyimpan setup", ephemeral=True)


class SetupSelectView(discord.ui.View):
    def __init__(self, user_id: str, action: str, menu_message: discord.Message):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.action = action
        self.menu_message = menu_message
        
        config = load_config()
        setups = config["accounts"].get(user_id, {}).get("setups", {})
        
        # Add select dropdown
        self.select = discord.ui.Select(
            placeholder="Pilih setup",
            options=[
                discord.SelectOption(label=name, value=name)
                for name in setups.keys()
            ]
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
    
    async def select_callback(self, interaction: discord.Interaction):
        selected_setup = self.select.values[0]
        config = load_config()
        
        # Pastikan setup masih ada
        if selected_setup not in config["accounts"][self.user_id]["setups"]:
            await interaction.response.send_message(
                f"Setup '{selected_setup}' tidak ditemukan.",
                ephemeral=True
            )
            return
            
        setup_data = config["accounts"][self.user_id]["setups"][selected_setup]
        
        if self.action == "edit":
            await interaction.response.send_modal(
                SetupModal(
                    user_id=self.user_id, 
                    setup_name=selected_setup, 
                    setup_data=setup_data,
                    menu_message=self.menu_message
                )
            )
        elif self.action == "start":
            config["accounts"][self.user_id]["setups"][selected_setup]["running"] = True
            save_config(config)
            await interaction.response.send_message(
                f"Setup '{selected_setup}' telah diaktifkan.",
                ephemeral=True
            )
            # Refresh menu utama
            await refresh_menu_message(self.menu_message)
        elif self.action == "stop":
            config["accounts"][self.user_id]["setups"][selected_setup]["running"] = False
            save_config(config)
            await interaction.response.send_message(
                f"Setup '{selected_setup}' telah dihentikan.",
                ephemeral=True
            )
            # Refresh menu utama
            await refresh_menu_message(self.menu_message)
        elif self.action == "status":
            status = "🟢 AKTIF" if setup_data.get("running", False) else "🔴 NON-AKTIF"
            token_valid = await validate_token(config["accounts"][self.user_id]["token"])
            
            embed = discord.Embed(
                title=f"Status Setup: {selected_setup}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Status", value=status, inline=True)
            embed.add_field(name="Token Valid", value="✅" if token_valid else "❌", inline=True)
            embed.add_field(name="Channel", value=setup_data.get("channel", "Belum diatur"), inline=True)
            embed.add_field(name="Interval", value=f"{setup_data.get('interval', 1)} menit", inline=True)
            embed.add_field(name="Random Interval", value=f"{setup_data.get('random_interval', 0)} menit", inline=True)
            
            if "last_updated" in setup_data:
                last_updated = datetime.fromisoformat(setup_data["last_updated"]).strftime("%Y-%m-%d %H:%M:%S")
                embed.add_field(name="Terakhir Diupdate", value=last_updated, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif self.action == "delete":
            # Konfirmasi penghapusan
            confirm_view = ConfirmDeleteView(self.user_id, selected_setup, self.menu_message)
            await interaction.response.send_message(
                f"Apakah Anda yakin ingin menghapus setup '{selected_setup}'?",
                view=confirm_view,
                ephemeral=True
            )


class MenuView(discord.ui.View):
    def __init__(self, config, menu_message: discord.Message = None):
        super().__init__(timeout=None)
        self.config = config
        self.menu_message = menu_message
    def set_menu_message(self, message: discord.Message):
        """Set the menu message after it's been sent"""
        self.menu_message = message
    @discord.ui.button(label="Set Token", style=discord.ButtonStyle.secondary)
    async def set_token(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Tombol untuk mengatur token"""
        try:
            user_id = str(interaction.user.id)
            await interaction.response.send_modal(TokenModal(user_id=user_id, menu_message=self.menu_message))
        except Exception as e:
            logger.error("Error in set_token button: %s", e)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Terjadi error saat membuka modal token", 
                    ephemeral=True
                )

    @discord.ui.button(label="Buat Setup", style=discord.ButtonStyle.primary)
    async def create_setup(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            user_id = str(interaction.user.id)
            
            # Pastikan token sudah diatur
            if user_id not in self.config["accounts"] or "token" not in self.config["accounts"][user_id]:
                await interaction.response.send_message(
                    "Silakan set token terlebih dahulu dengan menekan tombol 'Set Token'", 
                    ephemeral=True
                )
                return
                
            await interaction.response.send_modal(CreateSetupModal(user_id=user_id, menu_message=self.menu_message))
                
        except Exception as e:
            logger.error("Error in create_setup button: %s", e)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Terjadi error saat membuka modal setup", 
                    ephemeral=True
                )

    @discord.ui.button(label="Edit Setup", style=discord.ButtonStyle.primary)
    async def edit_setup(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            user_id = str(interaction.user.id)
            
            # Pastikan token sudah diatur dan ada setups
            if (user_id not in self.config["accounts"] or 
                "token" not in self.config["accounts"][user_id] or
                not self.config["accounts"][user_id].get("setups")):
                await interaction.response.send_message(
                    "Silakan buat setup terlebih dahulu dengan menekan tombol 'Buat Setup'", 
                    ephemeral=True
                )
                return
                
            view = SetupSelectView(user_id=user_id, action="edit", menu_message=self.menu_message)
            await interaction.response.send_message("Pilih setup untuk diedit:", view=view, ephemeral=True)
                
        except Exception as e:
            logger.error("Error in edit_setup button: %s", e)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Terjadi error saat membuka pilihan edit", 
                    ephemeral=True
                )

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success)
    async def start(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            user_id = str(interaction.user.id)
            
            # Pastikan token sudah diatur dan ada setups
            if (user_id not in self.config["accounts"] or 
                "token" not in self.config["accounts"][user_id] or
                not self.config["accounts"][user_id].get("setups")):
                await interaction.response.send_message(
                    "Silakan buat setup terlebih dahulu dengan menekan tombol 'Buat Setup'", 
                    ephemeral=True
                )
                return
                
            view = SetupSelectView(user_id=user_id, action="start", menu_message=self.menu_message)
            await interaction.response.send_message("Pilih setup untuk di-start:", view=view, ephemeral=True)
                
        except Exception as e:
            logger.error("Error in start button: %s", e)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Terjadi error saat memulai autopost", 
                    ephemeral=True
                )

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def stop(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            user_id = str(interaction.user.id)
            
            # Pastikan token sudah diatur dan ada setups
            if (user_id not in self.config["accounts"] or 
                "token" not in self.config["accounts"][user_id] or
                not self.config["accounts"][user_id].get("setups")):
                await interaction.response.send_message(
                    "Silakan buat setup terlebih dahulu dengan menekan tombol 'Buat Setup'", 
                    ephemeral=True
                )
                return
                
            view = SetupSelectView(user_id=user_id, action="stop", menu_message=self.menu_message)
            await interaction.response.send_message("Pilih setup untuk di-stop:", view=view, ephemeral=True)
                
        except Exception as e:
            logger.error("Error in stop button: %s", e)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Terjadi error saat menghentikan autopost", 
                    ephemeral=True
                )

    @discord.ui.button(label="Status", style=discord.ButtonStyle.secondary)
    async def status(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            user_id = str(interaction.user.id)
            
            # Pastikan token sudah diatur dan ada setups
            if (user_id not in self.config["accounts"] or 
                "token" not in self.config["accounts"][user_id] or
                not self.config["accounts"][user_id].get("setups")):
                await interaction.response.send_message(
                    "Silakan buat setup terlebih dahulu dengan menekan tombol 'Buat Setup'", 
                    ephemeral=True
                )
                return
                
            view = SetupSelectView(user_id=user_id, action="status", menu_message=self.menu_message)
            await interaction.response.send_message("Pilih setup untuk dilihat status:", view=view, ephemeral=True)
                
        except Exception as e:
            logger.error("Error in status button: %s", e)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Terjadi error saat memeriksa status", 
                    ephemeral=True
                )