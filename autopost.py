import aiohttp
import asyncio
import random
import logging
from typing import Dict, List, Any
from datetime import datetime
from config import load_config, save_config
from utils import validate_token

logger = logging.getLogger(__name__)

API_BASE = "https://discord.com/api/v9"

async def send_message(token: str, channel_id: str, content: str, max_retries: int = 3) -> bool:
    """
    Send a message to a Discord channel with retry logic
    
    Args:
        token: User token for authentication
        channel_id: ID of the channel to send message to
        content: Message content
        max_retries: Number of retry attempts on failure
        
    Returns:
        bool: True if successful, False otherwise
    """
    # First validate the token
    if not await validate_token(token):
        logger.error("Token tidak valid untuk channel %s", channel_id)
        return False
    
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    payload = {"content": content}
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{API_BASE}/channels/{channel_id}/messages", 
                    headers=headers, 
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info("Pesan terkirim ke %s", channel_id)
                        return True
                    elif resp.status == 401:  # Unauthorized
                        logger.error("Token tidak valid untuk channel %s", channel_id)
                        return False
                    elif resp.status == 429:  # Rate limited
                        retry_after = float(resp.headers.get('Retry-After', 5))
                        logger.warning("Rate limited, retrying after %s", retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        err = await resp.text()
                        logger.error("Gagal kirim ke %s: %s %s", channel_id, resp.status, err)
                        if attempt == max_retries - 1:  # Last attempt
                            return False
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
        except asyncio.TimeoutError:
            logger.warning("Timeout ketika mengirim ke %s, percobaan %s/%s", 
                          channel_id, attempt + 1, max_retries)
            if attempt == max_retries - 1:
                return False
            await asyncio.sleep(2 ** attempt)
        except aiohttp.ClientError as e:
            logger.error("Error koneksi ke %s: %s", channel_id, str(e))
            if attempt == max_retries - 1:
                return False
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error("Error tidak terduga: %s", str(e))
            if attempt == max_retries - 1:
                return False
            await asyncio.sleep(2 ** attempt)
    
    return False

