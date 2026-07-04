#!/usr/bin/env python3
"""
ANGLERFISH · Claude Fable 5 — Autotrade Engine
================================================================================
บอทเทรด Binance Spot อัตโนมัติ โดยใช้ LLM (ผ่าน OpenRouter) เป็น "สมอง" ตัดสินใจ
An automated Binance Spot trading bot using an LLM (via OpenRouter) as its
decision-making brain.

ปรัชญาการออกแบบ / Design philosophy:
  ปลอดภัยไว้ก่อนเสมอ (safety-first). ค่าเริ่มต้นทุกอย่างต้อง "ปลอดภัยที่สุด"
  Every default must be the SAFEST possible default. Placing a real order
  must require multiple deliberate, hard-to-fumble steps — never a single
  flag, never an accident, never a silent LLM decision.

คำเตือน / DISCLAIMER:
  ซอฟต์แวร์นี้เป็นการทดลอง (experimental) การเทรดคริปโตมีความเสี่ยงสูงมาก
  คุณอาจสูญเสียเงินทั้งหมดได้ นี่ไม่ใช่คำแนะนำการลงทุนทางการเงิน
  คุณเป็นผู้รับผิดชอบผลลัพธ์ทั้งหมดแต่เพียงผู้เดียว
  This software is experimental. Crypto trading is HIGH RISK — you can lose
  all of your money. This is NOT financial advice. You are solely
  responsible for any outcome from running this software.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# python-dotenv และ requests / ccxt ถูก import "แบบขี้เกียจ" (lazy) ที่ท้ายไฟล์นี้
# ก็ต่อเมื่อผ่านขั้นตอนตรวจสอบ config พื้นฐานแล้วเท่านั้น เพื่อให้ path ที่ไม่มี
# .env เลย สามารถออกจากโปรแกรมได้อย่างสะอาด โดยไม่ต้องพึ่ง dependency หนักๆ
#
# We import dotenv eagerly (it's tiny and needed to even read config), but we
# defer importing ccxt/requests until after config validation — that keeps
# the zero-.env smoke-test path fast and failure-free even if those heavier
# packages are missing.
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs) -> bool:  # type: ignore
        """Fallback no-op if python-dotenv isn't installed yet.

        เผื่อกรณี python-dotenv ยังไม่ได้ติดตั้ง — ให้ยัง import ไฟล์นี้ได้
        และไปเจอ error message ที่เป็นมิตรตอนตรวจ config แทนที่จะ crash ตรงนี้
        """
        return False


# ==============================================================================
# ค่าคงที่ / Constants
# ==============================================================================

BANNER = r"""
  ⚡ ANGLERFISH · Claude Fable 5 — Autotrade Engine ⚡
  --------------------------------------------------
  LLM-driven Binance Spot trading bot (safety-first)
"""

DISCLAIMER_TH = """
[คำเตือน] ซอฟต์แวร์นี้เป็นการทดลอง (experimental) ใช้ตามความเสี่ยงของคุณเอง
  - การเทรดคริปโตมีความเสี่ยงสูงมาก คุณอาจสูญเสียเงินลงทุนทั้งหมดได้
  - นี่ไม่ใช่คำแนะนำทางการเงินหรือการลงทุนใดๆ ทั้งสิ้น
  - คุณเป็นผู้รับผิดชอบแต่เพียงผู้เดียวต่อผลลัพธ์ทุกประการที่เกิดจากการใช้บอทนี้
""".strip("\n")

DISCLAIMER_EN = """
[DISCLAIMER] This is EXPERIMENTAL software. Use entirely at your own risk.
  - Crypto trading is extremely high-risk. You can lose all invested funds.
  - Nothing here is financial or investment advice of any kind.
  - You are SOLELY responsible for any and all outcomes from using this bot.
""".strip("\n")

TRUE_STRINGS = {"true", "1", "yes", "y", "on"}
FALSE_STRINGS = {"false", "0", "no", "n", "off"}

REQUIRED_KEYS = ("BINANCE_API_KEY", "BINANCE_API_SECRET", "OPENROUTER_API_KEY")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

LIVE_CONFIRM_PHRASE = "I UNDERSTAND"


# ==============================================================================
# ยูทิลิตี้ทั่วไป / Small utilities
# ==============================================================================

def now_str() -> str:
    """คืนค่าเวลาปัจจุบันแบบ UTC ในรูปแบบอ่านง่ายสำหรับ log."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log(msg: str, level: str = "INFO") -> None:
    """Log แบบมี timestamp — ทุกบรรทัด log ของบอทควรผ่านฟังก์ชันนี้เสมอ
    (ยกเว้น banner/disclaimer ตอนเริ่มโปรแกรม)."""
    print(f"[{now_str()}] [{level}] {msg}", flush=True)


def redact(value: Optional[str]) -> str:
    """ปกปิดค่าที่เป็นความลับ (API key/secret) ก่อนพิมพ์ออก log ใดๆ
    Redact a secret value before it's ever logged/printed anywhere.
    ไม่ควรมีที่ใดในโค้ดนี้ที่ print(key) ตรงๆ — ต้องผ่านฟังก์ชันนี้เสมอ."""
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def parse_bool(raw: Optional[str], default: bool) -> bool:
    """แปลง string จาก .env เป็น bool อย่างทนทาน (robust).
    รองรับ true/1/yes/on และ false/0/no/off (case-insensitive, มี/ไม่มีช่องว่าง)."""
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in TRUE_STRINGS:
        return True
    if normalized in FALSE_STRINGS:
        return False
    log(f"ค่า boolean แปลกๆ '{raw}' ใช้ default={default} แทน / "
        f"Unrecognized boolean '{raw}', falling back to default={default}",
        level="WARN")
    return default


def parse_float_env(raw: Optional[str], default: float, name: str) -> float:
    """แปลง string เป็น float อย่างทนทาน พร้อม fallback ที่ log ชัดเจน."""
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError:
        log(f"ค่า {name}='{raw}' ไม่ใช่ตัวเลข ใช้ default={default} แทน / "
            f"{name}='{raw}' is not a valid number, using default={default}",
            level="WARN")
        return default


def parse_int_env(raw: Optional[str], default: int, name: str) -> int:
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        log(f"ค่า {name}='{raw}' ไม่ใช่จำนวนเต็ม ใช้ default={default} แทน / "
            f"{name}='{raw}' is not a valid integer, using default={default}",
            level="WARN")
        return default


# ==============================================================================
# Config
# ==============================================================================

@dataclass
class Config:
    binance_api_key: str
    binance_api_secret: str
    openrouter_api_key: str
    openrouter_model: str
    symbol: str
    timeframe: str
    dry_run: bool
    use_testnet: bool
    max_order_usdt: float
    max_daily_loss_usdt: float
    poll_interval_sec: int
    candle_lookback: int

    def missing_required(self) -> list[str]:
        """คืนรายชื่อ key ที่จำเป็นแต่ยังว่างอยู่ (ใช้ string เปล่าล้วนๆ ตรวจสอบ
        ไม่มีการ raise ใดๆ ในฟังก์ชันนี้ — ต้อง fail-safe เสมอ)."""
        missing = []
        if not self.binance_api_key.strip():
            missing.append("BINANCE_API_KEY")
        if not self.binance_api_secret.strip():
            missing.append("BINANCE_API_SECRET")
        if not self.openrouter_api_key.strip():
            missing.append("OPENROUTER_API_KEY")
        return missing


def load_config() -> Config:
    """โหลด config จาก .env (ถ้ามี) + environment variables.
    load_dotenv() ปลอดภัยแม้ไม่มีไฟล์ .env เลย (จะเป็น no-op เฉยๆ)."""
    load_dotenv()  # no-op ถ้าไม่มีไฟล์ .env — ไม่ throw

    return Config(
        binance_api_key=os.getenv("BINANCE_API_KEY", ""),
        binance_api_secret=os.getenv("BINANCE_API_SECRET", ""),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet"),
        symbol=os.getenv("SYMBOL", "BTC/USDT"),
        timeframe=os.getenv("TIMEFRAME", "1h"),
        dry_run=parse_bool(os.getenv("DRY_RUN"), default=True),
        use_testnet=parse_bool(os.getenv("USE_TESTNET"), default=True),
        max_order_usdt=parse_float_env(os.getenv("MAX_ORDER_USDT"), 15.0, "MAX_ORDER_USDT"),
        max_daily_loss_usdt=parse_float_env(
            os.getenv("MAX_DAILY_LOSS_USDT"), 50.0, "MAX_DAILY_LOSS_USDT"),
        poll_interval_sec=parse_int_env(
            os.getenv("POLL_INTERVAL_SEC"), 300, "POLL_INTERVAL_SEC"),
        candle_lookback=parse_int_env(
            os.getenv("CANDLE_LOOKBACK"), 60, "CANDLE_LOOKBACK"),
    )


def print_missing_keys_help(missing: list[str]) -> None:
    """ข้อความที่เป็นมิตรเมื่อยังไม่ได้ตั้งค่า .env — ต้องไม่มี stack trace
    ใดๆ ทั้งสิ้น และต้อง exit(0) อย่างสะอาด (นี่คือ smoke-test path)."""
    print()
    print("=" * 78)
    print("[TH] ยังไม่ได้ตั้งค่าไฟล์ .env หรือค่าที่จำเป็นยังไม่ครบ")
    print("     กรุณาทำตามขั้นตอนนี้:")
    print("       1) คัดลอกไฟล์ตัวอย่าง:  cp .env.example .env")
    print("       2) เปิดไฟล์ .env แล้วกรอกค่าที่จำเป็นให้ครบ")
    print(f"     ค่าที่ยังขาด/ว่างอยู่: {', '.join(missing)}")
    print()
    print("[EN] The .env file is missing or required values are not set.")
    print("     Please follow these steps:")
    print("       1) Copy the example file:  cp .env.example .env")
    print("       2) Open .env and fill in the required values")
    print(f"     Missing/empty keys: {', '.join(missing)}")
    print("=" * 78)
    print()


# ==============================================================================
# การกำหนดโหมดการทำงาน (Execution Mode Gate) — หัวใจของความปลอดภัย
# ==============================================================================
#
# กฎเหล็ก: มีจุดเดียวในทั้งโปรแกรมที่ตัดสินว่า "จะส่งคำสั่งจริงได้ไหม" คือ
# ฟังก์ชันนี้ ที่อื่นในโค้ดห้าม re-derive เงื่อนไขนี้ขึ้นมาใหม่เด็ดขาด เพื่อไม่ให้
# มีทางหลุด (bypass) ใดๆ หลงเหลืออยู่
#
# Golden rule: there is exactly ONE place in this entire program that decides
# whether a real order may be placed — this function. Nowhere else may
# re-derive this condition; that's how bypasses sneak in.
#
# เงื่อนไขทั้งหมดต้องเป็นจริงพร้อมกัน (conjunction) ถึงจะเทรดจริงได้:
# ALL of the following must be true simultaneously for live trading:
#   1) DRY_RUN=false (ใน .env)
#   2) รันด้วย flag --live
#   3) ผู้ใช้พิมพ์ยืนยัน "I UNDERSTAND" ตอนเริ่มโปรแกรม (interactive)
#   4) ถ้า USE_TESTNET=false (mainnet) → ต้องมี env I_UNDERSTAND_REAL_MONEY=YES ด้วย
#
# หมายเหตุการออกแบบ: เราบังคับให้ต้องพิมพ์ยืนยันแม้แต่ตอนเทรดบน testnet
# (ไม่ใช่แค่ mainnet) เพื่อให้ gate เดียวกันนี้ใช้ได้สม่ำเสมอทุกกรณี ลดโอกาส
# ที่ "จะเผลอ" กดอะไรผิดจนออกคำสั่งจริงโดยไม่ตั้งใจ
# Design note: we require the typed confirmation even for testnet execution
# (not just mainnet) so the same gate applies uniformly everywhere, reducing
# the chance of accidentally triggering real order placement through
# inconsistent gating logic.
# ==============================================================================

@dataclass
class ExecutionMode:
    live_authorized: bool  # True เฉพาะเมื่อผ่านทุกเงื่อนไข = อนุญาตส่งคำสั่งจริง
    reasons_blocked: list[str] = field(default_factory=list)
    label: str = ""  # ป้ายกำกับสำหรับแสดงผล เช่น "DRY-RUN" / "LIVE MAINNET"


def resolve_execution_mode(cfg: Config, cli_live: bool) -> ExecutionMode:
    """คำนวณโหมดการทำงานเพียงครั้งเดียวตอนเริ่มโปรแกรม แล้วส่งต่อ object
    เดียวกันนี้ไปใช้ทั่วทั้งโปรแกรม ห้ามคำนวณซ้ำที่จุดอื่น.

    Computed exactly once at startup; the resulting object is threaded
    through the rest of the program. Never recomputed at the order site.
    """
    reasons: list[str] = []

    if cfg.dry_run:
        reasons.append("DRY_RUN=true (ตั้งค่าไว้ / configured) — ต้องตั้งเป็น false ก่อน")
    if not cli_live:
        reasons.append("ไม่ได้รัน --live flag / --live flag was not passed")

    # ถ้ายังไม่ผ่านสองเงื่อนไขแรก ก็ไม่ต้องไปถามยืนยันแบบ interactive ให้เสียเวลา
    # If the first two gates already fail, skip the interactive prompt entirely.
    typed_ok = False
    if not reasons:
        typed_ok = _prompt_live_confirmation(cfg)
        if not typed_ok:
            reasons.append(
                f"ไม่ได้พิมพ์ยืนยัน '{LIVE_CONFIRM_PHRASE}' ถูกต้อง / "
                f"did not type the exact confirmation phrase '{LIVE_CONFIRM_PHRASE}'"
            )

    mainnet_ack = True
    if not cfg.use_testnet:
        mainnet_ack = parse_bool(os.getenv("I_UNDERSTAND_REAL_MONEY"), default=False)
        if not mainnet_ack:
            reasons.append(
                "USE_TESTNET=false (mainnet) แต่ไม่ได้ตั้ง env "
                "I_UNDERSTAND_REAL_MONEY=YES / "
                "USE_TESTNET=false (mainnet) but env I_UNDERSTAND_REAL_MONEY=YES "
                "was not set"
            )

    live_authorized = len(reasons) == 0

    if live_authorized:
        label = "LIVE MAINNET — REAL MONEY" if not cfg.use_testnet else "LIVE TESTNET"
    else:
        label = "DRY-RUN"

    return ExecutionMode(live_authorized=live_authorized, reasons_blocked=reasons, label=label)


def _prompt_live_confirmation(cfg: Config) -> bool:
    """ถามยืนยันแบบพิมพ์ข้อความตอนเริ่มโปรแกรม (ครั้งเดียว ไม่ใช่ทุก cycle).
    ถ้า input ไม่ใช่ TTY (เช่นรันใน CI/pipe) หรือเจอ EOF จะถือว่าปฏิเสธ
    และ fallback เป็น dry-run โดยอัตโนมัติ — ไม่มีทาง "เผลอผ่าน" ได้.

    Interactive typed confirmation, prompted once at startup (not per cycle).
    If stdin is not a TTY or EOF is hit, this is treated as a refusal and the
    bot falls back to dry-run automatically — there is no way to "accidentally
    pass" this gate.
    """
    target = "TESTNET (เงินทดสอบ / sandbox funds)" if cfg.use_testnet else \
             "MAINNET — เงินจริง 100% / REAL MONEY, 100%"
    print()
    print("!" * 78)
    print(f"[TH] คุณกำลังจะเปิดใช้งานการเทรดจริงบน: {target}")
    print(f"     คู่เหรียญ: {cfg.symbol}  |  วงเงินสูงสุดต่อคำสั่ง: {cfg.max_order_usdt} USDT")
    print(f"     ขาดทุนสูงสุดต่อวันก่อนหยุดอัตโนมัติ: {cfg.max_daily_loss_usdt} USDT")
    print("     นี่คือซอฟต์แวร์ทดลอง คุณอาจสูญเสียเงินได้ คุณรับผิดชอบเองทั้งหมด")
    print(f"[EN] You are about to enable LIVE trading on: {target}")
    print(f"     Symbol: {cfg.symbol}  |  Max per-order notional: {cfg.max_order_usdt} USDT")
    print(f"     Max daily loss before auto-halt: {cfg.max_daily_loss_usdt} USDT")
    print("     This is experimental software. You may lose money. You are")
    print("     solely responsible for all outcomes.")
    print("!" * 78)
    print(f"พิมพ์ / Type exactly: {LIVE_CONFIRM_PHRASE}")
    try:
        if not sys.stdin.isatty():
            log("stdin ไม่ใช่ interactive terminal — ปฏิเสธการยืนยันอัตโนมัติ / "
                "stdin is not an interactive TTY — auto-refusing confirmation",
                level="WARN")
            return False
        typed = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        log("ไม่ได้รับการยืนยัน (EOF/Ctrl+C) — ปฏิเสธ / "
            "No confirmation received (EOF/Ctrl+C) — refusing", level="WARN")
        return False
    return typed == LIVE_CONFIRM_PHRASE


# ==============================================================================
# Indicators — SMA / RSI ล้วนๆ ด้วย Python (ไม่ใช้ pandas/numpy)
# ==============================================================================

def sma(values: list[float], period: int) -> Optional[float]:
    """Simple Moving Average ของ `period` ค่าล่าสุด คืน None ถ้าข้อมูลไม่พอ."""
    if len(values) < period or period <= 0:
        return None
    window = values[-period:]
    return sum(window) / period


def rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Relative Strength Index มาตรฐาน (Wilder's smoothing แบบง่าย).
    คืน None ถ้าข้อมูลไม่พอ (ต้องการอย่างน้อย period+1 แท่ง)."""
    if len(closes) < period + 1:
        return None

    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    # ใช้ค่าเฉลี่ยของ `period` ค่าล่าสุดของ gains/losses (แบบง่าย ไม่ recursive
    # ทุก tick — เพียงพอสำหรับ feature ให้ LLM ใช้ประกอบการตัดสินใจ)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def pct_change(old: float, new: float) -> Optional[float]:
    if old == 0:
        return None
    return ((new - old) / old) * 100.0


# ==============================================================================
# Market features — สรุปข้อมูลตลาดให้ LLM อ่านง่าย
# ==============================================================================

def build_market_features(ohlcv: list[list[float]], ticker: dict[str, Any]) -> dict[str, Any]:
    """สรุปฟีเจอร์ตลาดแบบเบาๆ จาก OHLCV + ticker เพื่อป้อนให้ LLM
    ohlcv แต่ละแถวคือ [timestamp, open, high, low, close, volume] (มาตรฐาน ccxt)."""
    closes = [candle[4] for candle in ohlcv]
    highs = [candle[2] for candle in ohlcv]
    lows = [candle[3] for candle in ohlcv]

    last_price = float(ticker.get("last") or closes[-1] if closes else 0.0)
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    rsi14 = rsi(closes, 14)

    change_1 = pct_change(closes[-2], closes[-1]) if len(closes) >= 2 else None
    lookback_n = min(24, len(closes))
    change_n = pct_change(closes[-lookback_n], closes[-1]) if lookback_n >= 2 else None

    return {
        "last_price": round(last_price, 8) if last_price else None,
        "sma20": round(sma20, 8) if sma20 is not None else None,
        "sma50": round(sma50, 8) if sma50 is not None else None,
        "rsi14": round(rsi14, 2) if rsi14 is not None else None,
        "pct_change_last_candle": round(change_1, 3) if change_1 is not None else None,
        f"pct_change_last_{lookback_n}_candles": round(change_n, 3) if change_n is not None else None,
        "recent_high": round(max(highs), 8) if highs else None,
        "recent_low": round(min(lows), 8) if lows else None,
        "candles_used": len(closes),
    }


# ==============================================================================
# OpenRouter — เรียก LLM เพื่อให้ตัดสินใจ
# ==============================================================================

SYSTEM_PROMPT = """You are ANGLERFISH, a disciplined crypto tail-sniper strategist.
You analyze short-term market microstructure and reply with a single trading
decision. You are extremely risk-averse by default: when signals are mixed,
weak, or unclear, you choose HOLD. You never chase pumps, never revenge-trade,
and never suggest position sizes beyond what is given as the maximum.

You MUST reply with ONLY a single compact JSON object and nothing else — no
markdown, no code fences, no explanation outside the JSON. The JSON schema is
exactly:
{"action": "BUY" | "SELL" | "HOLD", "confidence": <number 0..1>, \
"size_usdt": <number>, "reason": "<short string, one sentence>"}
"""


def call_openrouter(cfg: Config, features: dict[str, Any]) -> str:
    """เรียก OpenRouter chat completions API คืนค่า raw text จาก LLM.
    Raises บนความผิดพลาดของ network/HTTP — ผู้เรียกต้อง try/except ครอบไว้เสมอ."""
    import requests  # lazy import — ดู comment ด้านบนของไฟล์

    user_content = (
        "Market snapshot (JSON), decide the single best action for this cycle.\n"
        f"Symbol: {cfg.symbol}\n"
        f"Timeframe: {cfg.timeframe}\n"
        f"Max allowed size_usdt for any BUY/SELL: {cfg.max_order_usdt}\n"
        f"Features: {json.dumps(features, sort_keys=True)}\n"
        "Reply with ONLY the JSON object described in your instructions."
    )

    payload = {
        "model": cfg.openrouter_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {cfg.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


@dataclass
class Decision:
    action: str  # "BUY" | "SELL" | "HOLD"
    confidence: float
    size_usdt: float
    reason: str


def parse_decision(raw_text: str, max_order_usdt: float) -> Decision:
    """แปลง response ของ LLM เป็น Decision object อย่างทนทาน (robust parsing).
    ถ้า parse ไม่สำเร็จหรือ field ไม่ถูกต้อง → คืนค่า HOLD เสมอ (fail-safe).
    ไม่มีทางที่ parse error จะกลายเป็น BUY/SELL โดยไม่ตั้งใจ."""
    fallback = Decision(action="HOLD", confidence=0.0, size_usdt=0.0,
                         reason="parse_failed_or_invalid_fallback_to_hold")
    if not raw_text or not raw_text.strip():
        return fallback

    text = raw_text.strip()
    # ตัด code fence ออกถ้า LLM ใส่มา (```json ... ``` หรือ ``` ... ```)
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # หา JSON object ตัวแรกในข้อความ (เผื่อ LLM พูดอะไรแทรกมาก่อน/หลัง)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        log(f"ไม่พบ JSON ใน LLM response — HOLD / No JSON found in LLM response "
            f"— defaulting to HOLD. Raw: {text[:200]!r}", level="WARN")
        return fallback

    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        log(f"JSON แปลงไม่ได้ — HOLD / JSON decode failed — defaulting to HOLD: "
            f"{exc}. Raw: {text[:200]!r}", level="WARN")
        return fallback

    action = str(obj.get("action", "HOLD")).strip().upper()
    if action not in ("BUY", "SELL", "HOLD"):
        log(f"action แปลกๆ '{action}' — HOLD / Unrecognized action '{action}' "
            f"— defaulting to HOLD", level="WARN")
        return fallback

    try:
        confidence = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    try:
        size_usdt = float(obj.get("size_usdt", 0.0))
    except (TypeError, ValueError):
        size_usdt = 0.0
    # กฎเหล็ก: ไม่ว่า LLM จะขออะไรมา ห้ามเกิน MAX_ORDER_USDT เด็ดขาด (clamp)
    # Iron rule: no matter what the LLM requests, clamp to MAX_ORDER_USDT.
    size_usdt = max(0.0, min(size_usdt, max_order_usdt))

    reason = str(obj.get("reason", "")).strip()[:280] or "no_reason_given"

    return Decision(action=action, confidence=confidence, size_usdt=size_usdt, reason=reason)


# ==============================================================================
# Position / PnL tracking — เรียบง่ายโดยตั้งใจ (ไม่ใช่ ledger เต็มรูปแบบ)
# ==============================================================================

@dataclass
class PositionTracker:
    """ติดตามโพซิชันและ realized PnL แบบง่ายสำหรับ session/วันนี้เท่านั้น
    (ไม่ persist ข้ามการรันโปรแกรม — ตั้งใจให้เรียบง่าย ไม่ใช่ ledger ธุรกิจจริง)."""
    qty: float = 0.0
    avg_cost: float = 0.0
    session_realized_pnl: float = 0.0
    trades_executed: int = 0

    def apply_buy(self, qty: float, price: float) -> None:
        total_cost = self.avg_cost * self.qty + price * qty
        self.qty += qty
        self.avg_cost = total_cost / self.qty if self.qty > 0 else 0.0
        self.trades_executed += 1

    def apply_sell(self, qty: float, price: float) -> float:
        """คำนวณ realized PnL ของการขายนี้ แล้วบวกเข้า session total คืนค่า
        PnL เฉพาะของ trade นี้."""
        qty_to_sell = min(qty, self.qty)
        realized = (price - self.avg_cost) * qty_to_sell
        self.qty -= qty_to_sell
        if self.qty <= 0:
            self.qty = 0.0
            self.avg_cost = 0.0
        self.session_realized_pnl += realized
        self.trades_executed += 1
        return realized

    def halted_by_loss(self, max_daily_loss_usdt: float) -> bool:
        return self.session_realized_pnl < -abs(max_daily_loss_usdt)


# ==============================================================================
# Exchange helpers (ccxt)
# ==============================================================================

def init_exchange(cfg: Config):
    """สร้าง ccxt binance exchange instance พร้อมตั้งค่า sandbox ถ้า USE_TESTNET.
    lazy-import ccxt ตรงนี้เพื่อให้ path ไม่มี .env ไม่ต้องพึ่งพา ccxt เลย."""
    import ccxt  # lazy import

    exchange = ccxt.binance({
        "apiKey": cfg.binance_api_key,
        "secret": cfg.binance_api_secret,
        "enableRateLimit": True,
    })
    if cfg.use_testnet:
        exchange.set_sandbox_mode(True)
        log("ตั้งค่า Binance sandbox mode (testnet) เรียบร้อย / "
            "Binance sandbox mode (testnet) enabled")
    return exchange


def compute_capped_amount(exchange, symbol: str, price: float, size_usdt: float) -> tuple[float, bool]:
    """แปลง size_usdt → จำนวนเหรียญ (amount) โดยเคารพ precision และ min-notional
    ของตลาด คืน (amount, is_valid). ถ้า amount ต่ำกว่า min-notional/min-amount
    ของตลาด → is_valid=False (ผู้เรียกควรถือเป็น HOLD แทน).

    Converts a USDT notional into a coin amount, respecting the market's
    precision and min-notional/min-amount limits. Returns (amount, is_valid);
    if the resulting order would be below the market's minimums, is_valid is
    False and the caller should treat this as a HOLD instead of attempting
    an order that the exchange would reject anyway.
    """
    if price <= 0 or size_usdt <= 0:
        return 0.0, False

    raw_amount = size_usdt / price

    try:
        market = exchange.market(symbol)
    except Exception as exc:  # noqa: BLE001 - ตลาดโหลดไม่ได้ ถือว่า invalid ปลอดภัยไว้ก่อน
        log(f"โหลดข้อมูลตลาด {symbol} ไม่ได้ / Failed to load market {symbol}: {exc}",
            level="WARN")
        return 0.0, False

    # ccxt คืนค่า precision เป็น string เสมอ — ต้อง float() ก่อนใช้คำนวณต่อ
    # ccxt's amount_to_precision always returns a string — must be float()'d.
    # หมายเหตุ: ccxt อาจ raise InvalidOrder ถ้า amount เล็กกว่า precision ขั้นต่ำ
    # ของตลาด (เช่น amount ต่ำกว่า step size) — ต้องจับไว้และถือเป็น invalid
    # แทนที่จะปล่อยให้ exception หลุดขึ้นไปทำให้รอบนี้ crash
    # Note: ccxt may raise InvalidOrder if the amount is smaller than the
    # market's minimum precision/step size — caught here and treated as
    # invalid rather than letting the exception crash this cycle.
    try:
        precise_amount_str = exchange.amount_to_precision(symbol, raw_amount)
        amount = float(precise_amount_str)
    except Exception as exc:  # noqa: BLE001 - ปัดเป็น invalid แทน crash เสมอ
        log(f"amount_to_precision ล้มเหลวสำหรับ {symbol} (amount={raw_amount}) — ถือเป็น "
            f"invalid / amount_to_precision failed for {symbol} (amount={raw_amount}) "
            f"— treating as invalid: {exc}", level="WARN")
        return 0.0, False

    limits = market.get("limits") or {}
    min_amount = (limits.get("amount") or {}).get("min")
    min_cost = (limits.get("cost") or {}).get("min")

    if min_amount is not None and amount < float(min_amount):
        return amount, False
    if min_cost is not None and (amount * price) < float(min_cost):
        return amount, False
    if amount <= 0:
        return amount, False

    return amount, True


# ==============================================================================
# ลูปหลักของบอท / Main bot loop
# ==============================================================================

def run_cycle(cfg: Config, mode: ExecutionMode, exchange, tracker: PositionTracker) -> None:
    """รันหนึ่งรอบการตัดสินใจ: ดึงข้อมูล → เรียก LLM → ประเมินความเสี่ยง → ทำ.
    ทุกอย่างในนี้ห่อด้วย try/except ที่ชั้นบน (main loop) เพื่อไม่ให้หนึ่งรอบ
    ที่ล้มเหลว ทำให้บอททั้งตัว crash."""
    ohlcv = exchange.fetch_ohlcv(cfg.symbol, cfg.timeframe, limit=cfg.candle_lookback)
    ticker = exchange.fetch_ticker(cfg.symbol)

    if not ohlcv:
        log("ไม่มีข้อมูล OHLCV กลับมา — ข้ามรอบนี้ / No OHLCV data returned — skipping cycle",
            level="WARN")
        return

    features = build_market_features(ohlcv, ticker)
    log(f"Market features: {json.dumps(features, sort_keys=True)}")

    try:
        raw_response = call_openrouter(cfg, features)
    except Exception as exc:  # noqa: BLE001 - network/HTTP ใดๆ ต้องไม่ทำให้บอทล้ม
        log(f"เรียก OpenRouter ไม่สำเร็จ — ถือเป็น HOLD / OpenRouter call failed "
            f"— treating as HOLD: {exc}", level="ERROR")
        raw_response = ""

    decision = parse_decision(raw_response, cfg.max_order_usdt)
    log(f"LLM decision: action={decision.action} confidence={decision.confidence:.2f} "
        f"size_usdt={decision.size_usdt:.2f} reason={decision.reason!r}")

    if decision.action == "HOLD":
        log("HOLD — ไม่ทำอะไรในรอบนี้ / HOLD — no action this cycle")
        return

    last_price = features.get("last_price")
    if not last_price or last_price <= 0:
        log("ไม่มีราคาล่าสุดที่ใช้ได้ — ข้ามรอบนี้ / No valid last price available — skipping",
            level="WARN")
        return

    amount, is_valid = compute_capped_amount(exchange, cfg.symbol, last_price, decision.size_usdt)
    if not is_valid or amount <= 0:
        log(f"ขนาดคำสั่งต่ำกว่าขั้นต่ำของตลาดหลัง apply cap — ถือเป็น HOLD / "
            f"Order size below market minimums after capping — treating as HOLD "
            f"(requested size_usdt={decision.size_usdt:.2f})", level="WARN")
        return

    approx_notional = amount * last_price

    if not mode.live_authorized:
        action_th = "ซื้อ" if decision.action == "BUY" else "ขาย"
        log(f"[DRY] จะ{action_th} {amount} {cfg.symbol.split('/')[0]} "
            f"(~${approx_notional:.2f}) — เหตุผล: {decision.reason} / "
            f"[DRY] would {decision.action} {amount} {cfg.symbol.split('/')[0]} "
            f"(~${approx_notional:.2f}) — reason: {decision.reason}")
        return

    # ตรวจ daily-loss halt ก่อนส่งคำสั่งจริงทุกครั้ง (ไม่ใช่แค่ตอนเริ่มโปรแกรม)
    # Check the daily-loss halt before every real order, not just at startup.
    if tracker.halted_by_loss(cfg.max_daily_loss_usdt):
        log(f"หยุดเทรด — ขาดทุนสะสม {tracker.session_realized_pnl:.2f} USDT เกินขีดจำกัด "
            f"/ Trading halted — cumulative loss {tracker.session_realized_pnl:.2f} USDT "
            f"exceeds limit", level="ERROR")
        raise DailyLossHalt(tracker.session_realized_pnl)

    place_live_order(cfg, exchange, tracker, decision.action, amount, last_price, approx_notional)


class DailyLossHalt(Exception):
    """โยนขึ้นเมื่อขาดทุนสะสมเกิน MAX_DAILY_LOSS_USDT — ทำให้ main loop หยุดทันที."""
    def __init__(self, realized_pnl: float):
        self.realized_pnl = realized_pnl
        super().__init__(f"Daily loss limit exceeded: {realized_pnl:.2f} USDT")


def place_live_order(cfg: Config, exchange, tracker: PositionTracker,
                      action: str, amount: float, price: float, approx_notional: float) -> None:
    """ส่งคำสั่ง market order จริงผ่าน ccxt แล้วอัปเดต position/PnL tracker
    เรียกได้เฉพาะเมื่อ mode.live_authorized == True เท่านั้น (ตรวจแล้วก่อนเรียก)."""
    side = "buy" if action == "BUY" else "sell"
    log(f"กำลังส่งคำสั่งจริง / Placing LIVE order: {side.upper()} {amount} {cfg.symbol} "
        f"(~${approx_notional:.2f})")
    try:
        order = exchange.create_order(cfg.symbol, "market", side, amount)
    except Exception as exc:  # noqa: BLE001 - ความล้มเหลวของ exchange ต้องไม่ทำให้บอทล้ม
        log(f"ส่งคำสั่งไม่สำเร็จ / Order placement failed: {exc}", level="ERROR")
        return

    filled = order.get("filled") or amount
    avg_price = order.get("average") or order.get("price") or price
    log(f"คำสั่งสำเร็จ / Order filled: id={order.get('id')} filled={filled} "
        f"avg_price={avg_price}")

    if action == "BUY":
        tracker.apply_buy(float(filled), float(avg_price))
    else:
        realized = tracker.apply_sell(float(filled), float(avg_price))
        log(f"Realized PnL ของ trade นี้ / this trade's realized PnL: {realized:.4f} USDT "
            f"| Session total: {tracker.session_realized_pnl:.4f} USDT")


def print_session_summary(tracker: PositionTracker) -> None:
    print()
    print("-" * 78)
    print("สรุป Session / Session summary")
    print(f"  Trades executed : {tracker.trades_executed}")
    print(f"  Open position   : {tracker.qty} @ avg_cost={tracker.avg_cost}")
    print(f"  Realized PnL    : {tracker.session_realized_pnl:.4f} USDT")
    print("-" * 78)
    print()


def main_loop(cfg: Config, mode: ExecutionMode) -> None:
    exchange = init_exchange(cfg)
    tracker = PositionTracker()

    log(f"เริ่มลูปหลัก / Starting main loop — symbol={cfg.symbol} "
        f"timeframe={cfg.timeframe} poll_interval={cfg.poll_interval_sec}s "
        f"mode={mode.label}")

    try:
        while True:
            try:
                run_cycle(cfg, mode, exchange, tracker)
            except DailyLossHalt as halt:
                log(f"บอทหยุดทำงานเนื่องจากขาดทุนเกินขีดจำกัดรายวัน / Bot halted due to "
                    f"daily loss limit: {halt.realized_pnl:.2f} USDT", level="ERROR")
                print_session_summary(tracker)
                sys.exit(1)
            except Exception as exc:  # noqa: BLE001 - กันไม่ให้หนึ่งรอบที่พังทำให้บอทตาย
                log(f"รอบนี้ล้มเหลวโดยไม่คาดคิด — ไปต่อรอบถัดไป / Unexpected failure "
                    f"this cycle — continuing to next cycle: {exc}", level="ERROR")

            log(f"พักรอ {cfg.poll_interval_sec} วินาที.../ Sleeping {cfg.poll_interval_sec}s...")
            time.sleep(cfg.poll_interval_sec)
    except KeyboardInterrupt:
        print()
        log("ได้รับ Ctrl+C — กำลังปิดโปรแกรมอย่างปลอดภัย / Received Ctrl+C — shutting "
            "down gracefully")
        print_session_summary(tracker)


# ==============================================================================
# CLI / entrypoint
# ==============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autotrade.py",
        description="ANGLERFISH · Claude Fable 5 — LLM-driven Binance Spot autotrade "
                     "bot (safety-first, dry-run by default).",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="ขอเปิดใช้งานการเทรดจริง (ยังต้องผ่านเงื่อนไขอื่นอีกด้วย) / "
             "Request live trading (still requires the other safety conditions).",
    )
    parser.add_argument(
        "--symbol", type=str, default=None,
        help="Override SYMBOL from .env, e.g. ETH/USDT",
    )
    dry_run_group = parser.add_mutually_exclusive_group()
    dry_run_group.add_argument(
        "--dry-run", dest="dry_run", action="store_true", default=None,
        help="บังคับ dry-run แม้ .env ตั้ง DRY_RUN=false / Force dry-run even if "
             ".env sets DRY_RUN=false.",
    )
    dry_run_group.add_argument(
        "--no-dry-run", dest="dry_run", action="store_false", default=None,
        help="ปิด dry-run ตาม .env (ยังต้องมี --live ด้วยจึงจะเทรดจริงได้) / "
             "Disable dry-run per CLI (still requires --live to actually trade "
             "live).",
    )
    return parser


def main() -> None:
    print(BANNER)
    print(DISCLAIMER_TH)
    print()
    print(DISCLAIMER_EN)
    print()

    parser = build_arg_parser()
    args = parser.parse_args()

    cfg = load_config()

    # CLI overrides ทับค่าจาก .env (แต่ไม่ทับ safety gate อื่นๆ)
    if args.symbol:
        cfg.symbol = args.symbol
    if args.dry_run is not None:
        cfg.dry_run = args.dry_run

    missing = cfg.missing_required()
    if missing:
        print_missing_keys_help(missing)
        sys.exit(0)  # exit สะอาด ไม่มี stack trace — สำคัญมากสำหรับ smoke test

    log(f"Config loaded — symbol={cfg.symbol} timeframe={cfg.timeframe} "
        f"dry_run={cfg.dry_run} use_testnet={cfg.use_testnet} "
        f"max_order_usdt={cfg.max_order_usdt} max_daily_loss_usdt={cfg.max_daily_loss_usdt}")
    log(f"BINANCE_API_KEY={redact(cfg.binance_api_key)} "
        f"OPENROUTER_API_KEY={redact(cfg.openrouter_api_key)}")

    mode = resolve_execution_mode(cfg, cli_live=args.live)

    print()
    print("=" * 78)
    print(f"MODE: {mode.label}")
    if not mode.live_authorized:
        print("เหตุผลที่ไม่เปิดเทรดจริง / Why live trading is NOT enabled:")
        for reason in mode.reasons_blocked:
            print(f"  - {reason}")
        print("→ บอทจะรันในโหมด DRY-RUN (ปลอดภัย ไม่ส่งคำสั่งจริง) / "
              "→ The bot will run in DRY-RUN mode (safe, no real orders placed).")
    else:
        print("*** คำสั่งจริงจะถูกส่งไปยัง exchange ในโหมดนี้ ***")
        print("*** REAL ORDERS WILL BE PLACED against the exchange in this mode ***")
    print("=" * 78)
    print()

    try:
        main_loop(cfg, mode)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - เซฟตี้เน็ตสุดท้าย ไม่ให้ crash แบบมี stack trace เปล่าประโยชน์
        log(f"เกิดข้อผิดพลาดที่ไม่คาดคิดในระดับบนสุด / Unexpected top-level error: {exc}",
            level="ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
