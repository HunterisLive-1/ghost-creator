"""YouTube Studio Scraper using language-independent analytics card indexes."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from playwright.async_api import async_playwright

def parse_studio_card_value(text: str) -> float:
    text = text.strip()
    
    # Check for multiplier terms in different languages
    # e.g., "1.2 हज़ार" (Hindi), "1.2K" (English), "1.2M", "1.2 लाख" (Lakh)
    multiplier = 1.0
    if "हज़ार" in text or "K" in text.upper():
        multiplier = 1000.0
    elif "लाख" in text or "L" in text.upper():
        multiplier = 100000.0
    elif "M" in text.upper():
        multiplier = 1000000.0
        
    # Extract the first float/int value
    # Matches: "+6", "1.2", "1,194", "9.5", etc.
    match = re.search(r"([+-]?\s*\d+[\.,]?\d*)", text)
    if match:
        num_str = match.group(1).replace(" ", "").replace(",", "")
        try:
            return float(num_str) * multiplier
        except ValueError:
            return 0.0
    return 0.0

async def scrape_youtube_studio(profile_path: str, channel_id: str | None = None) -> dict:
    if not os.path.exists(profile_path):
        return {"ok": False, "error": f"Profile path '{profile_path}' does not exist."}
        
    async with async_playwright() as pw:
        # Use Chrome to load persistent login session
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            channel="chrome",
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        
        page = browser.pages[0] if browser.pages else await browser.new_page()
        
        try:
            print(f"[Scraper] Opening YouTube Studio: {profile_path}")
            await page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=45000)
            
            # Wait a few seconds for potential redirects
            await page.wait_for_timeout(4000)
            
            current_url = page.url
            if "accounts.google.com" in current_url:
                await browser.close()
                return {"ok": False, "error": "Not logged in. Please sign in to YouTube Studio in this profile first."}
                
            if not channel_id:
                # Extract channel ID from redirected URL if possible
                match = re.search(r"/channel/([^/]+)", current_url)
                if match:
                    channel_id = match.group(1)
                
            if channel_id:
                analytics_url = f"https://studio.youtube.com/channel/{channel_id}/analytics/tab-overview/period-default"
                print(f"[Scraper] Navigating directly to analytics page: {analytics_url}")
                await page.goto(analytics_url, wait_until="domcontentloaded", timeout=30000)
            else:
                print("[Scraper] Channel ID not found in URL, navigating to fallback analytics url")
                await page.goto("https://studio.youtube.com/channel/analytics", wait_until="domcontentloaded", timeout=30000)
                
            # Wait for the analytics card selectors to load (language independent!)
            await page.wait_for_selector("ytcp-key-metric-card", timeout=35000)
            
            # Wait a brief moment to ensure animations are completed
            await page.wait_for_timeout(2000)
            
            cards_locator = page.locator("ytcp-key-metric-card")
            count = await cards_locator.count()
            
            views = None
            subs = None
            earnings = None
            
            for i in range(count):
                card = cards_locator.nth(i)
                card_text = await card.inner_text()
                print(f"[Scraper] Card {i} Raw text: {repr(card_text)}")
                
                # Split text into lines
                lines = [l.strip() for l in card_text.split("\n") if l.strip()]
                if not lines:
                    continue
                    
                # Find the first line that has numeric values
                val = 0.0
                for line in lines:
                    if re.search(r"\d", line):
                        val = parse_studio_card_value(line)
                        break
                        
                # Card Order on YouTube Studio overview analytics tab is:
                # Card 0: Views
                # Card 1: Watch Time
                # Card 2: Subscribers
                # Card 3: Revenue (monetized only)
                if i == 0:
                    views = int(val)
                elif i == 2:
                    subs = int(val)
                elif i == 3:
                    earnings = val
                    
            await browser.close()
            
            # Fallbacks in case card counts don't match expected values
            if views is None:
                views = 0
            if subs is None:
                subs = 0
            if earnings is None:
                earnings = 0.0
                
            return {
                "ok": True,
                "views": views,
                "subs": subs,
                "earnings": earnings
            }
            
        except Exception as exc:
            await browser.close()
            return {"ok": False, "error": str(exc)}
