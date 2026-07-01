Server 
Intel NUC 7i5BNH mini pc 16 GB / M.2 128 GB + SATA 500 GB — Proxmox VE
==================================================================
Network
TP-Link ER605 (Router/VPN/Firewall)
TP-Link SG408E (Managed Switch)
==================================================================
OS: Proxmox VE
==================================================================

LXC Container 1: Application Stack (12GB RAM)

OS: Ubuntu 24.04 LTS

Core Stack: Docker Compose จัดการ service ทั้งหมด:
  - Supabase (Self-hosted): PostgreSQL + PostgREST + GoTrue + Studio
  - Redis: Cache & Queue
  - Chatwoot: Omnichannel Inbox (LINE + Messenger + Web)
  - n8n: Workflow Automation (Booking flow, Chatbot, Notifications)
  - FastAPI: Custom business logic (Booking CRUD, Payment, PDF generation)
  - nginx: Static frontend (ama-bangsaen-poolvilla.html) on port 80

===================================================================

LXC Container 2: Backup & Maintenance (2GB RAM)

Core Stack:
  - pg_dump automated backup (cron daily → SATA HDD 500GB)
  - rsync scripts (pulls Omada DB tarball from Pi nightly)
  - Future: rsync/NFS sync to NAS

Managed via plain SSH + crontab (no GUI layer — no CasaOS here).

===================================================================

Auxiliary Node: Raspberry Pi 4 Model B — Network & Independent Edge

OS: Raspberry Pi OS + CasaOS (Docker UI)
Bridged on management VLAN (L2 reachability to TP-Link APs)

Rule of thumb for what lives here: services that must stay alive
when LXC1 is down (monitoring, DNS, VPN-back-in, AP management).

Core Stack:
  - Omada Controller (Docker, mbentley/omada-controller, pinned tag)
      ports: 8088 (HTTP UI), 8043 (HTTPS UI), 8843 (captive portal),
             29810/udp (discovery), 29811-29816 (adopt/upgrade/manage)
      persistent volumes: data/, work/, logs/
      nightly tar of data/db → pulled by LXC2 rsync to SATA HDD
  - Uptime Kuma: monitors LXC1 services + Omada + Pi itself.
      Sends LINE alert when anything goes down. Lives here so it
      survives LXC1 outages (the whole point of monitoring).
  - Pi-hole / AdGuard Home (optional): LAN-wide DNS filtering.
  - cloudflared (Cloudflare Tunnel): fronts public traffic to LXC1
      (192.168.50.4:80). No port forwarding needed on ER605.
      Lives on Pi so tunnel survives LXC1 restarts independently.
  - Tailscale: mesh VPN back-door for admin access if Cloudflare
      Tunnel or LXC1 is unreachable.
  - Managed via CasaOS web UI.

===================================================================

External APIs:
  - Cloudflare Tunnel: Secure ingress via cloudflared on Pi
      → LXC1 192.168.50.4:80 (no port forwarding on ER605).
  - SlipOK: Slip verification (ฟรี 100 สลิป/เดือน)
  - LLM API (Future): Claude Haiku / GPT-4o-mini (เฉพาะคำถามเปิด)

===================================================================
