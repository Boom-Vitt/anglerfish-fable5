<!-- markdownlint-disable -->
# Changelog

รูปแบบอิงจาก [Keep a Changelog](https://keepachangelog.com/) · เวอร์ชันตาม [SemVer](https://semver.org/lang/th/)

## [1.0.0] — 2026-07-04

รุ่นแรกที่เผยแพร่ (first public release) ของ **ANGLERFISH · Claude Fable 5** 🎉

### Dashboard (`index.html`) — ไฟล์เดียว self-contained
- แดชบอร์ด quant terminal สไตล์ Binance **ธีมสว่าง (light mode)**
- **Total P&L** แบบ dot-matrix นับเลขวิ่งขึ้น
- **Live Market** — กราฟ TradingView (`BINANCE:BTCUSDT`) เรียลไทม์
- **Probability Lattice** — Galton board อนิเมชัน (ลูกบอลตกผ่าน 8 gates)
- **Tail Probability Ridge** — landscape **3 มิติ กล้องหมุน** (perspective projection เขียนเอง)
- **Relationship Graph** — force-directed network + median path เคลื่อนไหว
- **Autotrade Console** — ราคา Binance สด (public API) + ตัวสร้างไฟล์ `.env` (คีย์ไม่ถูกเก็บในหน้าเว็บ)
- รองรับ **มือถือ** + `prefers-reduced-motion`
- UI ภาษาไทย (technical terms คงเป็นภาษาอังกฤษ)

### Autotrade bot (`autotrade.py`)
- บอตเทรด Binance spot ขับเคลื่อนด้วย LLM ผ่าน **OpenRouter**
- **Safety-first:** `DRY_RUN` + testnet เป็นค่าเริ่มต้น · เทรดเงินจริงต้อง `--live` + พิมพ์ยืนยัน + flag mainnet
- Per-order cap, daily-loss halt, secret redaction
- Indicators (SMA / RSI / % change) เขียนเองด้วย Python ล้วน (ไม่พึ่ง pandas / numpy)

### Notes / ข้อจำกัดของรุ่นนี้
- `index.html` เป็น **built artifact** (self-contained) — ซอร์สโมดูลแบบแยกไฟล์อยู่ใน `build/` ซึ่ง **ไม่รวม** ในรีโป
- ต้องต่ออินเทอร์เน็ตสำหรับ TradingView + ราคาสด
- เส้นทาง **live trading + OpenRouter ต้องใช้คีย์ของผู้ใช้เอง** และ **ยังไม่ได้ทดสอบกับ API จริง** ในรุ่นนี้ (โค้ดครบและจัดการ error อย่างปลอดภัย แต่ผู้ใช้ต้องยืนยันเองด้วยคีย์ของตน)

[1.0.0]: https://github.com/Boom-Vitt/anglerfish-fable5/releases/tag/v1.0.0
