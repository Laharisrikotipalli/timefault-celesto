# 🛒 E-Commerce API (FastAPI • PostgreSQL • Redis • Docker)

A modular, production-ready **E-Commerce Backend API** built using **FastAPI**, **PostgreSQL**, **Redis**, **Docker**, and a background **Worker** service.  
This project implements core e-commerce features including product management, cart operations, pricing rules, reservation flow, and checkout workflows.

---
## 🚀 Features

### 🔹 Core Features
- Product creation & listing  
- Cart creation & item addition  
- Pricing rules engine (Base price → Discount → Tax)  
- Reservation & checkout workflow  
- PostgreSQL as primary database  
- Redis as cache + task queue  
- Worker service for asynchronous tasks

### 🔹 DevOps & Deployment
- Fully containerized using Docker  
- docker-compose.yml for multi-service orchestration  
- Database migrations (Alembic)  
- Environment-based configuration

---

### System Architecture


text
Client → FastAPI API → PostgreSQL
                   ↘ Redis Cache / Queue → Worker → PostgreSQL

<p align="center">
  <img src="assets/architecture.png" width="650" alt="Architecture Diagram">
</p>


### 🧩 Components
#### API Service
- Handles all HTTP requests.
#### PostgreSQL
- Primary persistent storage.
#### Redis
- Caching + Task Queue for background jobs.
#### Worker Service
- Executes pricing & reservation jobs asynchronously.
#### Docker Compose
- Orchestrates API, DB, Redis, and Worker containers.

### Tech Stack
| Layer            | Technology              |
| ---------------- | ----------------------- |
| Backend API      | FastAPI (Python)        |
| Worker Service   | Celery                |
| Database         | PostgreSQL              |
| Cache / Queue    | Redis                   |
| Containerization | Docker + Docker Compose |
| API Docs         | Swagger(OpenAPI)        |
| API Testing      | cURL/Powershell                  |

###  Project Structure
```
ecom-api/
│── app/
│   ├── main.py
│   ├── db.py
│   ├── schemas.py
│   ├── api/
│   │   └── v1/
│   │       ├── router.py
│   │       └── routers/
│   │           ├── products.py
│   │           ├── cart.py
│   │           └── checkout.py
│   ├── services/
│   │   ├── pricing.py
│   │   └── reservations.py
│   ├── celery_app.py
│   └── tasks.py
│
│── migrations/
│   └── 0001_create_schema.sql
│── assets/
│    └── architecture.png
│    └── schema.png
│── docker-compose.yml
│── Dockerfile
│── requirements.txt
│── README.md
```
### ⚙️ Environment Variables
 Create a .env file:
```
DATABASE_URL=postgresql://pguser:pgpassword@db:5432/ecom
REDIS_URL=redis://redis:6379/0
SECRET_KEY=your-secret-key
```
### 🐳 Running the Project (Docker)
1️⃣Start Database & Redis
```
docker compose up -d
```
2️⃣Run FastAPI
```
uvicorn app.main:app --reload
```
3️⃣ Run Worker
```
celery -A app.celery_app worker -l info
```
### API Access
#### Swagger UI
```
http://localhost:8000/docs
```
### API Testing (Examples)
🔸Add Item to Cart
```   
curl -X POST http://127.0.0.1:8000/api/v1/cart/add \
-H "Content-Type: application/json" \
-d '{"user_id":1,"variant_id":4,"quantity":2}'
```
🔸Checkout
  ```
curl -X POST http://127.0.0.1:8000/api/v1/checkout/ \
-H "Content-Type: application/json" \
-d '{"cart_id":1,"user_id":1}'
```
#### Reservation Logic 

Stock is reserved, not immediately deducted.

Each cart item has a reserved_until timestamp.

Checkout validates:

Reservation still valid

Reserved quantity ≥ requested quantity

Expired reservations are released by the Celery worker.

This prevents overselling under concurrency.

### Database Migrations
```
docker-compose exec web alembic upgrade head
```
### Install Requirements(without Docker)
```
pip install -r requirements.txt
 ```

