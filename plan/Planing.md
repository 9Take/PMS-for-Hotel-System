# Project Planning: HospitAI (Self-Hosted Hotel Management System)

## 1. Project Overview

ระบบจัดการ Pool Villa ขนาดเล็กแบบบูรณาการ โดยเน้นความปลอดภัย ความคุ้มค่า และการทำงานแบบ Self-Hosted ใช้ทรัพยากรที่มีอยู่จำกัดให้เกิดประสิทธิภาพสูงสุด

### Core Objective:

* เฟสแรก: สร้างระบบจัดการหลัก (POM: Property Operations Manager) ที่ครอบคลุมการตอบแชท, การจอง, ออกเอกสาร (Invoice/Receipt), และปฏิทินงาน
* เฟสสอง: เพิ่ม Intelligence Layer (LLM สำหรับคำถามเปิด) เมื่อระบบ core เสถียรแล้ว

---

## 2. Infrastructure & Hardware Architecture

### Network Layer: TP-Link ER605 + SG408E

* **Router:** TP-Link ER605 — จัดการ WAN/LAN, Firewall (Gateway วงใน 192.168.50.x, WAN .200 รับ DMZ จาก Huawei AIS)
* **Switch:** TP-Link SG408E — Managed Switch สำหรับ VLAN/QoS
* **DNS Filtering:** ใช้ Cloudflare DNS (1.1.1.2 / 1.1.1.3 - Malware blocking) ที่ ER605

### Node: Intel NUC 7i5BNH (16GB RAM, 4 Threads) - Core Server

* **Hypervisor:** Proxmox VE
* **Storage:** M.2 128GB (OS + App) + SATA 500GB (Backup + Data)
* **Virtualization Strategy:** ใช้ **LXC Container** + **Docker Compose** ภายใน

#### LXC Allocation Plan:

```
Intel NUC 16GB RAM
├── Proxmox Host OS:              ~2GB
│
├── LXC 1: Application Stack      12GB
│   └── Docker Compose:
│       ├── Supabase (PostgreSQL + Auth + API + Studio)  ~3-4GB
│       ├── Redis                                        ~256MB
│       ├── Chatwoot (Rails + Sidekiq + PostgreSQL)      ~2-3GB
│       ├── n8n (Workflow Automation)                     ~512MB idle
│       ├── FastAPI (Booking/Payment Logic)               ~256MB
│       ├── cloudflared (Cloudflare Tunnel sidecar)       ~50MB
│       └── Buffer/Shared                                ~2-4GB
│
└── LXC 2: Backup & Maintenance    2GB
    ├── pg_dump automated scripts (cron)
    ├── rsync to SATA HDD 500GB (incl. nightly pull of Omada DB from Pi)
    └── (Future: rsync to NAS)

Raspberry Pi 4 Model B — Network & Independent Edge (CasaOS)
├── Omada Controller (Docker, pinned tag) — manages TP-Link APs/switch
├── Uptime Kuma — monitors LXC1 + Omada + Pi, LINE alerts
├── Cloudflare DDNS updater (cron + CF API) — track AIS dynamic public IP for WireGuard endpoint domain
└── (Optional) Pi-hole / AdGuard Home — LAN DNS filtering
```

> **หมายเหตุ RAM:** Supabase full stack (~3-4GB) + Chatwoot (~2-3GB) + n8n (~512MB) + อื่นๆ รวม ~8-10GB active ภายใน LXC 12GB เพียงพอสำหรับ workload Pool Villa ขนาดเล็ก เหลือ buffer ~2-4GB

---

## 3. Software & Technology Stack

### 3.1 Core Stack

| Layer | Technology | หน้าที่ |
|---|---|---|
| **Database** | Supabase (Self-hosted) | PostgreSQL + Auto REST API + Auth + Admin UI |
| **Cache/Queue** | Redis | Session, Queue, n8n state |
| **Omnichannel Inbox** | Chatwoot (Self-hosted) | รวมแชท LINE + Messenger + Web ในที่เดียว |
| **Workflow Automation** | n8n (Self-hosted) | Booking flow, Notification, Chatbot logic |
| **Custom Logic** | FastAPI (Python) | Booking CRUD, Payment, PDF generation |
| **Monitoring** | Uptime Kuma | Service health + LINE alert เมื่อล่ม |
| **Tunnel** | Cloudflare Tunnel | รับ Webhook จากภายนอกโดยไม่เปิด port |
| **VPN** | WireGuard (on ER605) + Cloudflare DDNS (on Pi) | Admin remote access (inbound via AIS DMZ → ER605, port 51820) |

### 3.2 Supabase Self-Hosted — ทำไมถึงเลือก

| ฟีเจอร์ | ได้ฟรีจาก Supabase | ถ้าไม่ใช้ต้องเขียนเอง |
|---|---|---|
| REST/GraphQL API | ✅ Auto-generate จาก table | ต้องเขียน FastAPI endpoint ทุกตัว |
| Auth (LINE OAuth) | ✅ Built-in | ต้อง implement OAuth flow เอง |
| Admin Dashboard | ✅ Supabase Studio | ต้องสร้าง admin UI เอง |
| Row Level Security | ✅ Built-in | ต้องเขียน middleware เอง |
| Realtime | ✅ (ปิดได้ถ้าไม่ใช้) | ต้องทำ WebSocket เอง |

**RAM ที่ใช้ (Optimized):**
- ปิด service ที่ไม่ใช้ (Analytics/Logflare, Edge Runtime, Supavisor) → ลดได้ ~1GB
- เหลือ: PostgreSQL (~1-2GB) + GoTrue (~50MB) + PostgREST (~50MB) + Studio (~200MB) + Kong (~100MB)
- **รวมประมาณ ~2-3GB** (optimized) ถึง **~4GB** (full stack)

### 3.3 Chatbot Strategy — Hybrid Approach (ละเอียด)

> ไม่ใช้ LLM ในเฟสแรก — ใช้ rule-based ดึงข้อมูลจาก DB ตรงๆ

#### Layer 1: Rule-Based (n8n + Database Query) — เฟส 1

ใช้ n8n IF/Switch node จัดการคำถาม FAQ โดยไม่ต้องใช้ LLM:

```
ลูกค้าทัก LINE
    │
    ▼
Chatwoot รับข้อความ → Trigger n8n Webhook
    │
    ▼
n8n: ตรวจจับ keyword/intent (IF/Switch Node)
    │
    ├── "ราคา" / "เท่าไหร่" / "price"
    │   └── Query DB → ดึงราคาห้องทั้งหมด → ตอบเป็น Flex Message
    │
    ├── "ห้องว่าง" / "จอง" / "available"
    │   └── Query DB → เช็ก bookings table → แสดงปฏิทินว่าง
    │
    ├── "โปรโมชั่น" / "ลด" / "promo"
    │   └── Query DB → ดึง active promotions → ตอบพร้อมรูป
    │
    ├── "เช็คอิน" / "เช็คเอาท์" / "check-in"
    │   └── ตอบจาก static data (เวลา check-in/out, กฎของที่พัก)
    │
    ├── "สลิป" / "โอนเงิน" / "ชำระ"
    │   └── ตรวจจับรูปภาพ → ส่งไป SlipOK API → แจ้งแอดมิน
    │
    ├── "จะจอง" / "สนใจ"
    │   └── เริ่ม Booking Flow → ถามวันที่ → ถามจำนวนคน → สรุปยอด
    │
    └── ไม่ตรง keyword ใดเลย
        └── ส่งต่อให้แอดมินใน Chatwoot (Human handoff)
```

**ข้อดี:**
- ✅ ไม่ hallucinate — ข้อมูลมาจาก DB ตรงๆ
- ✅ เร็วมาก — ไม่ต้องรอ API call ไป LLM
- ✅ ค่าใช้จ่าย ฿0
- ✅ ควบคุม response ได้ 100%

#### Layer 2: LLM-Assisted (อนาคต — เฟส 4)

เมื่อระบบ core เสถียรแล้ว เพิ่ม LLM สำหรับ:
- คำถามเปิดที่ rule-based ตอบไม่ได้ (เช่น "แนะนำร้านอาหารใกล้ๆ")
- ใช้ **RAG** (Retrieval-Augmented Generation) โดยใส่ข้อมูลที่เราควบคุมเข้า context
- Model: Claude Haiku หรือ GPT-4o-mini (ราคาถูก, เร็ว)
- ประมาณ ~฿100-300/เดือน (pay-per-use)

#### Layer 3: Human Handoff

- คำถามที่ bot ตอบไม่ได้ → ส่งต่อ agent ใน Chatwoot ทันที
- แอดมินเห็น context ทั้งหมด (ข้อความก่อนหน้า + intent ที่ bot ตรวจจับ)
- แอดมินตอบใน Chatwoot → ส่งกลับลูกค้าผ่าน LINE/Messenger อัตโนมัติ

---

## 4. Operational Workflows (Human-in-the-Loop)

### 4.1 Booking & Payment Sequence

1. **Customer Interaction:** ลูกค้าทัก LINE → Chatwoot → n8n เช็กห้องว่าง (Query Supabase) → สรุปยอด
2. **Hold Stage:** ลูกค้าตกลง → n8n สร้าง booking ผ่าน FastAPI (Status: `HOLD`) ล็อก 30 นาที
3. **Payment:** ลูกค้าส่งสลิปโอนเงิน → n8n ส่งรูปไป **SlipOK API** ตรวจอัตโนมัติ
4. **Auto-Verify + Admin Confirm:**
   * SlipOK ตรวจ: ชื่อบัญชี, จำนวนเงิน, เวลา, ธนาคาร
   * ผลตรวจ + สลิป ส่งเข้า **LINE Group: Admin** พร้อมปุ่ม **[APPROVE] / [REJECT]**
   * แอดมินกดปุ่มยืนยัน (หรือปฏิเสธถ้าสลิปมีปัญหา)
5. **Post-Approval:** Status → `CONFIRMED` → FastAPI สร้าง PDF (template-based, WeasyPrint) → ส่งให้ลูกค้าผ่าน Chatwoot อัตโนมัติ

### 4.2 Calendar System

* **Web Dashboard:** แสดงผลตารางการเข้าพักแบบ Gantt Chart สำหรับแอดมิน (อาจใช้ Supabase Studio หรือ custom dashboard)
* **Daily Briefing:** ทุกเช้า 08:00 น. → n8n query bookings → สรุปงาน (เช็กอิน/เช็กเอาต์/ยอดจอง) → ส่ง LINE Group แอดมิน

### 4.3 Slip Verification (SlipOK)

| แพ็กเกจ | ราคา/เดือน | จำนวนสลิป | ค่าสลิปเกิน |
|---|---|---|---|
| **OK Basic** | ฟรี | 100 สลิป | ฿1.0/สลิป |
| **OK Start** | ฿210 | 500 สลิป | ฿0.42/สลิป |
| **OK SME** | ฿360 | 1,000 สลิป | ฿0.36/สลิป |

> Pool Villa ขนาดเล็ก → **OK Basic (ฟรี)** น่าจะเพียงพอ (100 สลิป/เดือน)

---

## 5. Database Schema (Draft — Supabase/PostgreSQL)

### Core Tables:

* `rooms`: id, room_number, type, price_per_night, max_guests, amenities, status, images
* `guests`: id, name, line_id, phone, email, notes, created_at
* `bookings`: id, guest_id, room_id, check_in, check_out, num_guests, total_price, status (hold/confirmed/cancelled/completed), created_at
* `transactions`: id, booking_id, amount, slip_url, slipok_result (jsonb), verified_by_admin (bool), admin_notes, verified_at
* `documents`: id, booking_id, file_path, type (receipt/confirmation/invoice), created_at
* `promotions`: id, name, description, discount_type, discount_value, start_date, end_date, is_active

### NAS Migration Strategy (อนาคต):

เพื่อให้ย้าย Database ไป NAS ได้สะดวก ออกแบบดังนี้:

1. **Docker Named Volumes:** ใช้ named volume สำหรับ PostgreSQL data แทน bind mount
   ```yaml
   volumes:
     supabase-db-data:
       driver: local
   ```

2. **Automated Backup:** pg_dump ทุกวัน → เก็บใน SATA HDD 500GB
   ```bash
   # cron: 0 2 * * * (ทุกวัน 02:00)
   pg_dump -U postgres -F c -f /backup/db_$(date +%Y%m%d).dump
   ```

3. **เมื่อมี NAS:** เปลี่ยน volume driver เป็น NFS mount หรือใช้ rsync sync ไป NAS
   ```yaml
   volumes:
     supabase-db-data:
       driver: local
       driver_opts:
         type: nfs
         o: addr=NAS_IP,rw
         device: ":/volume1/supabase-data"
   ```

4. **ย้ายทั้งระบบไป NAS:**
   - Stop containers → rsync volume data ไป NAS → Update docker-compose → Start
   - หรือ pg_dump → restore บน NAS instance ใหม่
   - Downtime: ~10-30 นาที (ขึ้นกับขนาดข้อมูล)

---

## 6. Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                    INTERNET                          │
│  ┌──────┐  ┌───────────┐  ┌─────┐                  │
│  │ LINE │  │ Messenger │  │ Web │                   │
│  └──┬───┘  └─────┬─────┘  └──┬──┘                  │
└─────┼────────────┼───────────┼──────────────────────┘
      │            │           │
      ▼            ▼           ▼
┌─────────────────────────────────────┐
│      Cloudflare Tunnel              │
│      (No port opening needed)       │
└──────────────┬──────────────────────┘
               │
┌──────────────┼──────────────────────────────────────┐
│  TP-Link ER605 + SG408E (Network Layer)             │
│  ├── Firewall / WireGuard VPN (Admin Remote, :51820)│
│  └── VLAN / QoS                                     │
└──────────────┼──────────────────────────────────────┘
               │
┌──────────────┼──────────────────────────────────────┐
│  Intel NUC 7i5BNH — Proxmox VE                     │
│                                                      │
│  ┌─── LXC 1: App Stack (Docker Compose) ─────────┐ │
│  │                                                 │ │
│  │  ┌──────────┐    ┌─────────┐    ┌───────────┐ │ │
│  │  │ Chatwoot │───▶│   n8n   │───▶│  FastAPI   │ │ │
│  │  │(Inbox)   │    │(Workflow│    │(Booking/   │ │ │
│  │  └──────────┘    │ Engine) │    │ Payment)   │ │ │
│  │                  └────┬────┘    └─────┬──────┘ │ │
│  │                       │               │        │ │
│  │                       ▼               ▼        │ │
│  │               ┌──────────────────────────┐     │ │
│  │               │  Supabase (Self-hosted)  │     │ │
│  │               │  ├── PostgreSQL          │     │ │
│  │               │  ├── PostgREST (API)     │     │ │
│  │               │  ├── GoTrue (Auth)       │     │ │
│  │               │  └── Studio (Admin UI)   │     │ │
│  │               └──────────────────────────┘     │ │
│  │                                                 │ │
│  │  ┌───────┐  ┌────────────┐                     │ │
│  │  │ Redis │  │ Uptime Kuma│──▶ LINE Alert       │ │
│  │  └───────┘  └────────────┘                     │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  ┌─── LXC 2: Backup ────────────────────────────┐  │
│  │  pg_dump → SATA HDD 500GB                     │  │
│  │  (Future: rsync → NAS)                        │  │
│  └───────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘

External APIs (Pay-per-use):
  ├── SlipOK (Slip Verification) — ฟรี 100 สลิป/เดือน
  └── Claude Haiku / GPT-4o-mini — เฟสอนาคต เฉพาะคำถามเปิด
```

---

## 7. Implementation Phases

### Phase 1: Foundation (สัปดาห์ 1-2)

* [ ] ติดตั้ง Proxmox + สร้าง LXC Container
* [ ] ติดตั้ง Docker + Docker Compose ใน LXC 1
* [ ] Deploy Supabase (self-hosted, optimized — ปิด Analytics/Edge Runtime)
* [ ] Deploy Redis
* [ ] Setup Cloudflare Tunnel ชี้ domain → NUC
* [ ] Deploy Uptime Kuma + ตั้ง LINE notification
* [ ] Setup automated backup (pg_dump → HDD 500GB, cron ทุกวัน)

### Phase 2: Core Booking System (สัปดาห์ 3-5)

* [ ] Deploy Chatwoot + เชื่อม LINE OA (Messaging API)
* [ ] สร้าง Database schema ใน Supabase
* [ ] พัฒนา FastAPI: Booking CRUD, Room availability, Guest management
* [ ] สร้าง PDF template (ใบจอง/ใบเสร็จ) ด้วย WeasyPrint
* [ ] Deploy n8n + สร้าง workflow:
  * Booking flow (ถามวันที่ → เช็กห้องว่าง → สรุปยอด → สร้าง booking)
  * Notification flow (แจ้งแอดมินเมื่อมี booking ใหม่)
* [ ] เชื่อม SlipOK สำหรับตรวจสลิปอัตโนมัติ

### Phase 3: Dashboard + Automation (สัปดาห์ 6-7)

* [ ] สร้าง Admin Dashboard (Calendar/Gantt view, Booking management)
* [ ] n8n: Daily briefing สรุปงานส่ง LINE Group ทุกเช้า
* [ ] n8n: Rule-based chatbot สำหรับ FAQ (ราคา, ห้องว่าง, โปรโมชั่น)
* [ ] n8n: Human handoff flow (ส่งต่อแอดมินเมื่อ bot ตอบไม่ได้)

### Phase 4: Intelligence Layer (อนาคต — เมื่อระบบเสถียร)

* [ ] เพิ่ม LLM (Haiku/GPT-4o-mini) สำหรับคำถามเปิดผ่าน n8n
* [ ] CRM features: ประวัติลูกค้า, โปรโมชั่น, analytics
* [ ] เพิ่ม Messenger channel ใน Chatwoot
* [ ] NAS migration (ย้าย DB + backup ไป NAS)

---

## 8. Monthly Cost Estimate

| รายการ | ค่าใช้จ่าย |
|---|---|
| Hardware (NUC + Network) | ซื้อแล้ว ฿0 |
| Cloudflare Tunnel | ฟรี |
| Domain | ~฿400/ปี (~฿33/เดือน) |
| Software (Supabase, Chatwoot, n8n, etc.) | ฟรี (Self-hosted, Open-source) |
| SlipOK (Slip Verification) | ฟรี (100 สลิป/เดือน) |
| LLM API (อนาคต) | ~฿100-300/เดือน |
| **รวม/เดือน (เฟส 1-3)** | **~฿33** |
| **รวม/เดือน (เฟส 4+)** | **~฿150-350** |

---

## 9. Security Notes

* **No Public Port Opening:** ใช้ Cloudflare Tunnel แทนการ Forward Port
* **VPN Only for Admin:** แผงควบคุมระบบทั้งหมดต้องเข้าผ่าน WireGuard VPN (รันบน ER605, port 51820) เท่านั้น โดย Cloudflare DDNS บน Pi คอยอัปเดต public IP ของ AIS ให้ endpoint domain ชี้ถูกตลอด
* **Data Privacy:** ข้อมูลลูกค้าจัดเก็บใน Local Supabase/PostgreSQL ไม่มีการส่งออกไปภายนอก
* **Supabase RLS:** ใช้ Row Level Security ควบคุมการเข้าถึงข้อมูลระดับ row
* **Backup:** Automated daily backup + SATA HDD แยกจาก OS disk
* **Monitoring:** Uptime Kuma แจ้งเตือนผ่าน LINE ทันทีเมื่อ service ล่ม

---

*End of Planning Document*