<!-- markdownlint-disable -->
<div align="center">

# ⚡ ANGLERFISH · Claude Fable 5

**แดชบอร์ด quant terminal สไตล์ Binance (ธีมสว่าง) + บอต autotrade ที่ขับด้วย AI**
_Relationship-Graph Mispricing Simulation · หน้าเว็บไฟล์เดียว + บอตเทรด Python_

### 👉 ดูตัวอย่างสด (Live Demo): https://boom-vitt.github.io/anglerfish-fable5/

</div>

---

## นี่คืออะไร?

โปรเจกต์นี้มี **2 ส่วน**:

1. **แดชบอร์ด** (`index.html`) — หน้าเว็บไฟล์เดียว ธีมสว่าง จำลองหน้าจอเทรดเดอร์มืออาชีพ มีกราฟ **TradingView สด**, อนิเมชัน และกราฟ **3 มิติ** เปิดดูได้ทันทีไม่ต้องติดตั้งอะไร
2. **บอตเทรดจริง** (`autotrade.py`) — บอต Python ที่ใช้ **Binance** (ตลาด) + **OpenRouter** (สมอง LLM) ตัดสินใจซื้อ/ขายอัตโนมัติ · ค่าเริ่มต้นปลอดภัย (จำลองก่อน ไม่ยิงออเดอร์จริง)

### มีโมดูลอะไรบ้างในแดชบอร์ด

| โมดูล | รายละเอียด |
|---|---|
| 💰 **Total P&L** | ตัวเลขกำไรแบบป้ายไฟจุด (dot-matrix) นับเลขวิ่งขึ้น |
| 📈 **Live Market** | กราฟ **TradingView ของจริง** (BINANCE:BTCUSDT) เรียลไทม์ |
| 🔌 **Autotrade Console** | คู่มือใส่คีย์ API + ตัวสร้างไฟล์ `.env` + ราคา BTC สดจาก Binance |
| 🎲 **Probability Lattice** | กระดาน Galton (ลูกบอลตกผ่าน 8 ช่อง) กำไร/ขาดทุน |
| ⛰️ **Tail Probability Ridge** | ภูมิทัศน์ความน่าจะเป็น **3 มิติ กล้องหมุนได้** |
| 🕸️ **Relationship Graph** | กราฟความสัมพันธ์สัญญาณ (force-directed) เส้นทางวิ่งได้ |

---

## ส่วนที่ 1 — เปิดดูแดชบอร์ด (ง่ายสุด ๆ)

**วิธีที่ 1 — เปิดไฟล์ตรง ๆ** ✅ ดับเบิลคลิก `index.html` เปิดในเบราว์เซอร์ได้เลย (ต้องต่อเน็ตให้กราฟ TradingView ขึ้น)

**วิธีที่ 2 — เปิดผ่านเซิร์ฟเวอร์ในเครื่อง** (เนียนกว่า)
```bash
python3 -m http.server 8131
# แล้วเปิด http://localhost:8131
```

---

## ส่วนที่ 2 — บอตเทรดจริง `autotrade.py` 🤖

> บอตนี้จะดึงราคาจาก Binance → ให้ LLM (ผ่าน OpenRouter) ตัดสินใจ → ส่งออเดอร์
> **ค่าเริ่มต้น = โหมดจำลอง (DRY_RUN) + Testnet** จึงปลอดภัย ไม่แตะเงินจริงจนกว่าคุณจะสั่งเอง

### ติดตั้ง
```bash
pip install -r requirements.txt
```

### ตั้งค่าคีย์ API
```bash
cp .env.example .env      # แล้วเปิดไฟล์ .env ใส่คีย์ของคุณ
```
ต้องใส่ 3 คีย์:
| ตัวแปร | เอามาจากไหน |
|---|---|
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | Binance → API Management |
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys |

> 💡 **สร้างคีย์ Binance ในหน้าแดชบอร์ด (Autotrade Console) ได้ — มีปุ่มสร้างไฟล์ `.env` ให้คัดลอกเลย**

### 🔒 ตั้งค่าคีย์ Binance ให้ปลอดภัย (สำคัญมาก)
- เปิดสิทธิ์ **Spot Trading เท่านั้น**
- **ปิด Withdrawals** (ห้ามให้ถอนเงินได้)
- ตั้ง **IP allowlist** ให้เฉพาะ IP เครื่องคุณ
- อย่า commit `.env` ขึ้น GitHub (มี `.gitignore` กันไว้ให้แล้ว)

### รันบอต
```bash
python autotrade.py            # โหมดจำลอง + testnet (ปลอดภัย เริ่มที่นี่)
```
ตัวอย่างผลลัพธ์: `[DRY] would BUY 0.00023 BTC (~$15) — reason: ...`

### 🔴 เทรดด้วยเงินจริง (ทำเมื่อพร้อมจริง ๆ เท่านั้น)
1. แก้ `.env`: `DRY_RUN=false` และ `USE_TESTNET=false`
2. รันด้วยแฟลก `--live` แล้วพิมพ์ยืนยันตามที่ระบบถาม
```bash
python autotrade.py --live
```

### ตัวแปรใน `.env` (ย่อ)
| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `DRY_RUN` | `true` | จำลองเท่านั้น ไม่ยิงออเดอร์ |
| `USE_TESTNET` | `true` | ใช้ Binance testnet |
| `SYMBOL` | `BTC/USDT` | คู่เทรด |
| `MAX_ORDER_USDT` | `15` | เพดานเงินต่อ 1 ออเดอร์ |
| `MAX_DAILY_LOSS_USDT` | `50` | ขาดทุนถึงเท่านี้ต่อวัน บอตหยุด |
| `POLL_INTERVAL_SEC` | `300` | ทุกกี่วินาทีให้ตัดสินใจ 1 ครั้ง |
| `OPENROUTER_MODEL` | `anthropic/claude-3.5-sonnet` | โมเดล LLM (ใส่ slug อะไรก็ได้ของ OpenRouter) |

---

## 📁 โครงสร้างไฟล์
```
index.html          ← แดชบอร์ดทั้งหมดในไฟล์เดียว (HTML + CSS + JS)
autotrade.py        ← บอตเทรด Python (Binance + OpenRouter)
.env.example        ← เทมเพลตคีย์ API (คัดลอกเป็น .env)
requirements.txt    ← Python dependencies
README.md           ← ไฟล์นี้
```

## 🛠️ เทคโนโลยี
- **Vanilla JavaScript + Canvas 2D** — อนิเมชันและ 3D เขียนเองล้วน ไม่พึ่งไลบรารีหนัก
- **TradingView Widget** — กราฟราคาคริปโตเรียลไทม์
- **Python + ccxt + OpenRouter** — เอนจินเทรดจริงที่ขับด้วย LLM
- **ดีไซน์สไตล์ Binance (Light)** — เหลือง `#FCD535`, เขียว `#0ecb81` / แดง `#f6465d` บนพื้นสว่าง

## ⚠️ คำเตือน
> การเทรดคริปโตมี **ความเสี่ยงสูง อาจสูญเงินทั้งหมด** · โปรเจกต์นี้เป็นซอฟต์แวร์ทดลอง/สาธิต **ไม่ใช่คำแนะนำการลงทุน** · ผู้ใช้รับความเสี่ยงเองทั้งหมด · เริ่มด้วยโหมดจำลอง/Testnet และจำนวนเงินน้อย ๆ เสมอ

## 📝 หมายเหตุ
- 🌐 ต้อง **ต่ออินเทอร์เน็ต** เพื่อให้กราฟ TradingView + ราคาสดแสดงผล
- ♿ รองรับ **Reduced Motion** และ 📱 **มือถือ**

---
<div align="center">
<sub>⚡ ANGLERFISH-CORE · FABLE-FORK — งานจำลอง/ดีไซน์เพื่อการสาธิต · Built with Claude Code</sub>
</div>
