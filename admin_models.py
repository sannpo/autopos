import discord
from discord.ui import View, Button, Select
from config import load_config, save_config
from subscription import create_subscription, PACKAGES, get_subscription_info, load_subscriptions
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class AdminPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📊 Dashboard", style=discord.ButtonStyle.primary, custom_id="admin_dashboard")
    async def dashboard(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        
        config = load_config()
        subscriptions = load_subscriptions()
        
        embed = discord.Embed(title="📊 Admin Dashboard", color=discord.Color.blue())
        
        # Stats
        active_subs = sum(1 for sub in subscriptions.values() if sub.get("active", False))
        total_users = len(config.get("accounts", {}))
        total_admins = len(config.get("admins", {}))
        
        embed.add_field(name="📈 Statistics", value=f"""
        • Active Subscriptions: **{active_subs}**
        • Total Users: **{total_users}**
        • Total Admins: **{total_admins}**
        • Available Packages: **{len(PACKAGES)}**
        """, inline=False)
        
        # Recent activity
        recent_subs = list(subscriptions.values())[-5:] if subscriptions else []
        if recent_subs:
            sub_info = ""
            for sub in recent_subs[-5:]:
                sub_info += f"• {sub.get('package_type', 'N/A')} - <@{sub.get('discord_user_id', 'N/A')}>\n"
            embed.add_field(name="🆕 Recent Subscriptions", value=sub_info, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🎫 Manage Subs", style=discord.ButtonStyle.secondary, custom_id="admin_manage_subs")
    async def manage_subs(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Pilih aksi subscription management:",
            view=SubscriptionManagementView(),
            ephemeral=True
        )

    @discord.ui.button(label="👥 Manage Users", style=discord.ButtonStyle.secondary, custom_id="admin_manage_users")
    async def manage_users(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Pilih aksi user management:",
            view=UserManagementView(),
            ephemeral=True
        )

    @discord.ui.button(label="⚙️ System", style=discord.ButtonStyle.secondary, custom_id="admin_system")
    async def system_tools(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Pilih tool system:",
            view=SystemToolsView(),
            ephemeral=True
        )
    @discord.ui.button(label="✏️ Update Subscription", style=discord.ButtonStyle.success, custom_id="update_sub")
    async def update_sub(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(UpdateSubscriptionModal())

    @discord.ui.button(label="🗑️ Delete Subscription", style=discord.ButtonStyle.danger, custom_id="delete_sub")
    async def delete_sub(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(DeleteSubscriptionModal())
    @discord.ui.button(label="⛔ Ban User", style=discord.ButtonStyle.danger, custom_id="ban_user")
    async def ban_user(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(BanUserModal())

    @discord.ui.button(label="🔄 Reset Token", style=discord.ButtonStyle.secondary, custom_id="reset_token")
    async def reset_user_token(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(ResetUserModal())
    @discord.ui.button(label="📣 Broadcast DM", style=discord.ButtonStyle.primary, custom_id="broadcast_dm")
    async def broadcast_dm(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(BroadcastModal())
class BroadcastModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Broadcast DM ke Semua User")
        self.add_item(discord.ui.InputText(label="Pesan", style=discord.InputTextStyle.paragraph, required=True))

    async def callback(self, interaction: discord.Interaction):
        message = self.children[0].value.strip()
        config = load_config()
        users = config.get("accounts", {})

        success = 0
        fail = 0
        for user_id in users:
            try:
                user = await interaction.client.fetch_user(int(user_id))
                await user.send(message)
                success += 1
            except Exception:
                fail += 1

        await interaction.response.send_message(f"✅ Broadcast selesai. Berhasil: {success}, Gagal: {fail}", ephemeral=True)

class DeleteSubscriptionModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Delete Subscription")
        self.add_item(discord.ui.InputText(label="Subscription ID", placeholder="ABC12345", required=True))

    async def callback(self, interaction: discord.Interaction):
        sub_id = self.children[0].value.strip()
        subscriptions = load_subscriptions()

        if sub_id not in subscriptions:
            await interaction.response.send_message(f"❌ Subscription `{sub_id}` tidak ditemukan.", ephemeral=True)
            return
        
        subscriptions.pop(sub_id)
        save_config(subscriptions)
        await interaction.response.send_message(f"✅ Subscription `{sub_id}` berhasil dihapus.", ephemeral=True)

class ResetUserModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Reset User Token")
        self.add_item(discord.ui.InputText(label="User ID", placeholder="123456789012345678", required=True))

    async def callback(self, interaction: discord.Interaction):
        user_id = self.children[0].value.strip()
        config = load_config()

        if user_id not in config.get("accounts", {}):
            await interaction.response.send_message(f"❌ User `{user_id}` tidak ditemukan.", ephemeral=True)
            return
        
        if "token" in config["accounts"][user_id]:
            config["accounts"][user_id].pop("token")
        
        save_config(config)
        await interaction.response.send_message(f"✅ Token user `{user_id}` berhasil direset.", ephemeral=True)

class BanUserModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Ban User")
        self.add_item(discord.ui.InputText(label="User ID", placeholder="123456789012345678", required=True))

    async def callback(self, interaction: discord.Interaction):
        user_id = self.children[0].value.strip()
        config = load_config()

        if user_id not in config.get("accounts", {}):
            await interaction.response.send_message(f"❌ User `{user_id}` tidak ditemukan.", ephemeral=True)
            return
        
        config["accounts"].pop(user_id)
        save_config(config)
        await interaction.response.send_message(f"✅ User `{user_id}` berhasil diban.", ephemeral=True)

class UpdateSubscriptionModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Update Subscription")
        self.add_item(discord.ui.InputText(label="Subscription ID", placeholder="ABC12345", required=True))
        self.add_item(discord.ui.InputText(label="New Package ID", placeholder="premium", required=True))

    async def callback(self, interaction: discord.Interaction):
        sub_id = self.children[0].value.strip()
        new_package = self.children[1].value.strip()

        subscriptions = load_subscriptions()
        if sub_id not in subscriptions:
            await interaction.response.send_message(f"❌ Subscription `{sub_id}` tidak ditemukan.", ephemeral=True)
            return
        
        if new_package not in PACKAGES:
            await interaction.response.send_message(f"❌ Package `{new_package}` tidak valid.", ephemeral=True)
            return
        
        subscriptions[sub_id]["package_type"] = new_package
        subscriptions[sub_id]["days"] = PACKAGES[new_package]["days"]
        save_config(subscriptions)  # pastiin fungsi save_subscriptions ada
        await interaction.response.send_message(f"✅ Subscription `{sub_id}` diupdate ke package `{new_package}`.", ephemeral=True)


class SubscriptionManagementView(View):
    def __init__(self):
        super().__init__(timeout=30)
        
        # Add package selection
        options = [
            discord.SelectOption(label=package["name"], value=package_id, 
                               description=f"Rp {package['price']:,} - {package['days']} hari")
            for package_id, package in PACKAGES.items()
        ]
        
        self.select = Select(placeholder="Pilih package...", options=options)
        self.select.callback = self.package_selected
        self.add_item(self.select)
    
    async def package_selected(self, interaction: discord.Interaction):
        package_id = self.select.values[0]
        await interaction.response.send_modal(CreateSubscriptionModal(package_id))

class CreateSubscriptionModal(discord.ui.Modal):
    def __init__(self, package_id: str):
        super().__init__(title=f"Buat Subscription {package_id}")
        self.package_id = package_id
        
        self.add_item(discord.ui.InputText(
            label="User ID",
            placeholder="123456789012345678",
            required=True
        ))
    
    async def callback(self, interaction: discord.Interaction):
        user_id = self.children[0].value.strip()
        package = PACKAGES[self.package_id]
        
        try:
            sub_id = create_subscription(user_id, self.package_id, package["days"])
            
            # Embed untuk admin
            embed_admin = discord.Embed(title="✅ Subscription Created", color=discord.Color.green())
            embed_admin.add_field(name="Subscription ID", value=f"`{sub_id}`", inline=False)
            embed_admin.add_field(name="Package", value=package["name"], inline=True)
            embed_admin.add_field(name="Duration", value=f"{package['days']} hari", inline=True)
            embed_admin.add_field(name="For User", value=f"<@{user_id}>", inline=False)
            
            await interaction.response.send_message(embed=embed_admin, ephemeral=True)

            # Embed untuk user target
            embed_user = discord.Embed(title="🎉 Subscription Baru", color=discord.Color.blue())
            embed_user.add_field(name="Subscription ID", value=f"`{sub_id}`", inline=False)
            embed_user.add_field(name="Package", value=package["name"], inline=True)
            embed_user.add_field(name="Duration", value=f"{package['days']} hari", inline=True)
            embed_user.add_field(name="Status", value="✅ AKTIF", inline=True)
            embed_user.add_field(name="Cara Login", value="Gunakan `!login` lalu ikuti instruksi", inline=False)
            embed_user.set_footer(text="Simpan Subscription ID Anda dengan aman!")

            # Coba kirim DM ke user
            try:
                user = await interaction.client.fetch_user(int(user_id))
                await user.send(embed=embed_user)
            except discord.Forbidden:
                await interaction.followup.send(f"⚠️ Tidak bisa kirim DM ke <@{user_id}> (DM terkunci).", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Gagal kirim ke user: {e}", ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

class UserManagementView(View):
    def __init__(self):
        super().__init__(timeout=30)
    
    @discord.ui.button(label="📋 List Users", style=discord.ButtonStyle.primary)
    async def list_users(self, button: discord.ui.Button, interaction: discord.Interaction):
        config = load_config()
        users = config.get("accounts", {})
        
        if not users:
            await interaction.response.send_message("❌ Tidak ada users terdaftar.", ephemeral=True)
            return
        
        embed = discord.Embed(title="👥 Registered Users", color=discord.Color.blue())
        
        for user_id, user_data in list(users.items())[:10]:  # Limit to 10 users
            setups_count = len(user_data.get("setups", {}))
            active_setups = sum(1 for s in user_data.get("setups", {}).values() if s.get("running", False))
            
            embed.add_field(
                name=f"User <@{user_id}>",
                value=f"Setups: {setups_count} | Active: {active_setups}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🔍 Find User", style=discord.ButtonStyle.secondary)
    async def find_user(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(FindUserModal())

class FindUserModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Cari User")
        
        self.add_item(discord.ui.InputText(
            label="User ID",
            placeholder="123456789012345678",
            required=True
        ))
    
    async def callback(self, interaction: discord.Interaction):
        user_id = self.children[0].value.strip()
        config = load_config()
        subscriptions = load_subscriptions()
        
        user_data = config.get("accounts", {}).get(user_id)
        
        if not user_data:
            await interaction.response.send_message("❌ User tidak ditemukan.", ephemeral=True)
            return
        
        embed = discord.Embed(title=f"👤 User Info - <@{user_id}>", color=discord.Color.blue())
        
        # User info
        setups_count = len(user_data.get("setups", {}))
        active_setups = sum(1 for s in user_data.get("setups", {}).values() if s.get("running", False))
        has_token = "token" in user_data
        
        embed.add_field(name="Setups", value=f"Total: {setups_count}\nActive: {active_setups}", inline=True)
        embed.add_field(name="Token", value="✅ Set" if has_token else "❌ Not Set", inline=True)
        
        # Subscription info
        user_subs = []
        for sub_id, sub_data in subscriptions.items():
            if sub_data.get("discord_user_id") == user_id:
                user_subs.append(f"`{sub_id}` - {sub_data.get('package_type')}")
        
        if user_subs:
            embed.add_field(name="Subscriptions", value="\n".join(user_subs), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class SystemToolsView(View):
    def __init__(self):
        super().__init__(timeout=30)
    
    @discord.ui.button(label="🔄 Reload Config", style=discord.ButtonStyle.primary)
    async def reload_config(self, button: discord.ui.Button, interaction: discord.Interaction):
        config = load_config()
        await interaction.response.send_message(
            f"✅ Config reloaded!\nAccounts: {len(config.get('accounts', {}))}\nAdmins: {len(config.get('admins', {}))}",
            ephemeral=True
        )
    
    @discord.ui.button(label="📊 Stats", style=discord.ButtonStyle.secondary)
    async def show_stats(self, button: discord.ui.Button, interaction: discord.Interaction):
        config = load_config()
        subscriptions = load_subscriptions()
        
        active_subs = sum(1 for sub in subscriptions.values() if sub.get("active", False))
        total_messages = sum(len(user_data.get("setups", {})) for user_data in config.get("accounts", {}).values())
        
        embed = discord.Embed(title="📈 System Statistics", color=discord.Color.green())
        embed.add_field(name="Users", value=str(len(config.get("accounts", {}))), inline=True)
        embed.add_field(name="Active Subs", value=str(active_subs), inline=True)
        embed.add_field(name="Total Setups", value=str(total_messages), inline=True)
        embed.add_field(name="Packages", value=str(len(PACKAGES)), inline=True)
        embed.add_field(name="Admins", value=str(len(config.get("admins", {}))), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)