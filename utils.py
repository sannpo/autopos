import logging
import aiohttp
import asyncio
from typing import Optional
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class UnicodeFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = record.msg.replace('❌', '[ERROR]')
            record.msg = record.msg.replace('✅', '[SUCCESS]')
            record.msg = record.msg.replace('⚠️', '[WARNING]')
        return True

def setup_logger():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("bot.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    logger.addFilter(UnicodeFilter())
    return logger

async def validate_token(token: str) -> bool:
    """
    Validate if a token is working
    
    Args:
        token: Discord user token to validate
        
    Returns:
        bool: True if token is valid, False otherwise
    """
    headers = {"Authorization": token}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://discord.com/api/v9/users/@me",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status == 200
    except Exception:
        return False