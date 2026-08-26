#!/usr/bin/env python3
"""
JWT Generator — Super Fast with Beautiful UI + Loading Animation
Reads accounts.json → Generates Tokens → Saves to token_cache.json
"""

import asyncio
import json
import os
import time
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict
import aiohttp

# ============================================================
# CONFIG
# ============================================================
JWT_API_URL = "https://ff-jwt-gen-api.lovable.app/api/public/token"
TOKEN_CACHE_FILE = "token_bd.json"
ACCOUNTS_FILE = "accounts-BD.json"
API_TIMEOUT = 10
TOKEN_EXPIRY_HOURS = 5
MAX_CONCURRENT = 30

# ============================================================
# BEAUTIFUL UI COLORS
# ============================================================
class C:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    DIM = '\033[90m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    BLINK = '\033[5m'
    RESET = '\033[0m'

# ============================================================
# BANNER
# ============================================================
def print_banner():
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════════════════════════════╗
║                                                                      ║
║   {C.YELLOW}██╗░░░░░░██╗████████╗     ██████╗░███████╗███╗░░██╗       {C.CYAN}║
║   {C.YELLOW}██║░░░░░░██║╚══██╔══╝    ██╔════╝░██╔════╝████╗░██║       {C.CYAN}║
║   {C.YELLOW}██║░░░░░░██║░░░██║░░░    ██║░░██╗░█████╗░░██╔██╗██║       {C.CYAN}║
║   {C.YELLOW}██║░░░░░░██║░░░██║░░░    ██║░░╚██╗██╔══╝░░██║╚████║       {C.CYAN}║
║   {C.YELLOW}███████╗██║░░░██║░░░    ╚██████╔╝███████╗██║░╚███║       {C.CYAN}║
║   {C.YELLOW}╚══════╝╚═╝░░░╚═╝░░░     ╚═════╝░╚══════╝╚═╝░░╚══╝       {C.CYAN}║
║                                                                      ║
║   {C.GREEN}⚡ SUPER FAST JWT GENERATOR ⚡{C.CYAN}                              ║
║   {C.DIM}Owner: @MEHEDIXAURA | Parallel: {MAX_CONCURRENT} concurrent{C.CYAN}      ║
╚══════════════════════════════════════════════════════════════════╝{C.RESET}
    """)

# ============================================================
# LOAD ACCOUNTS (SYNC)
# ============================================================
def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        print(f"{C.RED}❌ {ACCOUNTS_FILE} not found!{C.RESET}")
        return []
    
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            data = json.load(f)
            accounts = []
            if isinstance(data, list):
                for x in data:
                    if isinstance(x, dict):
                        u = str(x.get('uid', ''))
                        p = str(x.get('password', ''))
                        if u and p:
                            accounts.append({
                                "uid": u,
                                "password": p,
                                "name": str(x.get('name', '?'))[:25]
                            })
            return accounts
    except Exception as e:
        print(f"{C.RED}❌ Error: {e}{C.RESET}")
        return []

# ============================================================
# JWT API CALLER
# ============================================================
async def fetch_jwt(session, uid: str, password: str) -> Optional[Dict]:
    url = f"{JWT_API_URL}?uid={uid}&password={password}"
    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT, connect=5)
        async with session.get(url, timeout=timeout) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('success'):
                    token = data.get('token')
                    if token:
                        return {
                            'token': token,
                            'region': data.get('region', 'BD'),
                            'account_id': str(data.get('account_id', '')),
                            'uid': data.get('uid', uid)
                        }
    except:
        pass
    return None

# ============================================================
# SAVE TOKENS
# ============================================================
def save_tokens(tokens: Dict):
    expiry = (datetime.now() + timedelta(hours=TOKEN_EXPIRY_HOURS)).isoformat()
    for uid in tokens:
        tokens[uid]['expires_at'] = expiry
    
    with open(TOKEN_CACHE_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)
    
    print(f"\n{C.GREEN}✅ Saved {len(tokens)} tokens to {TOKEN_CACHE_FILE}{C.RESET}")
    print(f"{C.DIM}   📅 Expires at: {expiry}{C.RESET}")

# ============================================================
# GENERATE TOKENS — SUPER FAST PARALLEL
# ============================================================
async def generate_tokens():
    start_time = time.time()
    print_banner()
    
    print(f"\n{C.CYAN}📊 Loading accounts...{C.RESET}")
    accounts = load_accounts()
    if not accounts:
        print(f"{C.RED}❌ No accounts found.{C.RESET}")
        return
    
    total = len(accounts)
    print(f"{C.GREEN}✅ Loaded {total} accounts from {ACCOUNTS_FILE}{C.RESET}")
    print(f"\n{C.YELLOW}🚀 Generating {total} tokens with {MAX_CONCURRENT} concurrent requests...{C.RESET}")
    print(f"{C.DIM}{'─'*55}{C.RESET}")
    
    tokens = {}
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
    success_count = 0
    failed_count = 0
    
    async def process_account(session, acc, index):
        nonlocal success_count, failed_count
        uid = acc.get('uid')
        password = acc.get('password')
        name = acc.get('name', '?')
        
        async with semaphore:
            result = await fetch_jwt(session, uid, password)
            
            # Progress bar
            pct = int((index / total) * 100)
            bar_len = 25
            filled = int((pct / 100) * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            
            if result:
                tokens[uid] = result
                success_count += 1
                status = f"{C.GREEN}✅{C.RESET}"
                print(f"  {status} {C.DIM}[{index:3}/{total}]{C.RESET} {C.CYAN}{bar}{C.RESET} {C.YELLOW}{pct:3}%{C.RESET} {C.WHITE}{uid}{C.RESET} {C.DIM}- {name}{C.RESET}")
                return True
            else:
                failed_count += 1
                status = f"{C.RED}❌{C.RESET}"
                print(f"  {status} {C.DIM}[{index:3}/{total}]{C.RESET} {C.CYAN}{bar}{C.RESET} {C.YELLOW}{pct:3}%{C.RESET} {C.WHITE}{uid}{C.RESET} {C.DIM}- {name}{C.RESET}")
                return False
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for i, acc in enumerate(accounts, 1):
            tasks.append(process_account(session, acc, i))
        
        results = await asyncio.gather(*tasks)
        success_count = sum(results)
        failed_count = total - success_count
    
    elapsed = time.time() - start_time
    
    print(f"\n{C.BLUE}{'─'*55}{C.RESET}")
    print(f"{C.GREEN}✅ Success: {success_count}/{total}{C.RESET}")
    print(f"{C.RED}❌ Failed: {failed_count}/{total}{C.RESET}")
    print(f"{C.YELLOW}⏱️  Time: {elapsed:.2f}s{C.RESET}")
    
    if tokens:
        save_tokens(tokens)
    else:
        print(f"{C.RED}❌ No tokens generated!{C.RESET}")

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    try:
        asyncio.run(generate_tokens())
    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}⏹️ Stopped by user{C.RESET}")
    except Exception as e:
        print(f"\n{C.RED}❌ Error: {e}{C.RESET}")
