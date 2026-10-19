# VARUNA AI — Production-Grade Multi-Tenant AI Assistant Platform

> **"One Intelligence. Infinite Possibilities."**  
> A commercially viable, secure, and horizontally scalable AI SaaS platform designed for high performance, deterministic cost controls, and enterprise-grade multi-tenancy.

---

## 1. System Architecture

VARUNA AI follows a clean hexagonal architecture separating core business logic, persistence, and external adapters:

```
[ Frontend: Next.js 15 + React 19 + TypeScript + Tailwind CSS ]
                         │
                         ▼ (REST + Server-Sent Events SSE)
[ Backend: Python 3.12+ / FastAPI / Pydantic v2 ]
    ├── RBAC & Multi-Tenant Scoping (Row-level tenant isolation)
    ├── Two-Phase Token & Credit Economy Engine (Reservation & Atomic Settlement)
    ├── India-First Payment Gateway (Razorpay Orders & Cryptographic HMAC Verification)
    ├── Secure File Processor (Magic Bytes, PDF Optimizer, CSV/Excel Analytics)
    ├── Sandboxed Agent Execution Engine (AST Math, Web Research, Code Isolation)
    └── Provider-Independent AI Gateway (OpenAI, Ollama, Simulator)
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
[ PostgreSQL / SQLite ]         [ Redis (Rate Limiting) ]
```

---

## 2. Key Commercial & Security Features

- **Multi-Tenant Organization RBAC:** Every tenant data record is strictly bound to `organization_id`. Cross-tenant IDOR attacks are prevented and proven by automated tests.
- **Deterministic Token & Credit Unit:** Prepaid internal credits ($1 \text{ Credit} = ₹0.10$). Pre-request credit reservation prevents balance overdrafts; atomic settlement deducts exact tokens used.
- **India-First Razorpay Integration:** Server-side order creation in paise, cryptographic HMAC-SHA256 signature verification, raw payload webhook validation, and idempotency protection against duplicate event delivery.
- **Magic Bytes File Integrity:** Uploaded files are verified by inspecting magic byte signatures rather than relying on file extensions. PDFs are compressed with content stream optimization and exact savings reported.
- **Safe Agent Tool Sandboxing:** Safe AST calculator (no `eval`), sandboxed code runner blocking system calls and network sockets, and verified web research citations.
- **Platform Owner Dashboard:** Real-time visibility into gross margins, provider costs in USD, revenue in INR, active model registry with dynamic pricing, and an instant emergency AI kill-switch.

---

## 3. Local Development Setup

### Prerequisites
- Node.js v20+ and npm v10+
- Python 3.12+ (or 3.14+)
- Git

### Backend Setup
```bash
# 1. Navigate to backend directory
cd backend

# 2. Activate virtual environment
# Windows:
..\.venv\Scripts\activate
# Linux/macOS:
source ../.venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run database migrations and start server
uvicorn app.main:app --reload --port 8000
```
Backend API docs available at: `http://localhost:8000/docs`  
Health check at: `http://localhost:8000/health`

### Frontend Setup
```bash
# 1. Navigate to frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Start development server
npm run dev
```
Frontend application accessible at: `http://localhost:3000`

---

## 4. Production Deployment with Docker Compose

```bash
# 1. Copy environment template and configure secrets
cp .env.example .env

# 2. Build and launch all multi-container services
docker compose up -d --build

# 3. Verify health
docker compose ps
curl http://localhost:8000/health
```

---

## 5. Automated Test Suite

Run the full automated test suite verifying auth, tenant isolation, credit economics, HMAC payments, and file security:
```bash
# From workspace root:
set PYTHONPATH=backend
.venv\Scripts\python.exe -m pytest backend/tests/test_backend.py -v
```

---

## 6. Seed Credentials for Local Testing

- **Platform Admin:** `admin@varuna.ai` / `AdminPass123!`
- **Default Plan:** Varuna Free (100 welcome credits included on sign-up)
