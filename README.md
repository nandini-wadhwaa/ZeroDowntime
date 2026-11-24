# ZeroDowntime

### Blue-Green Deployment & Automated Rollback System

ZeroDowntime is a DevOps project designed to demonstrate application deployment with minimal service disruption using Blue-Green deployment, Docker containerization, Nginx reverse proxy and automated health monitoring.

The system provides an interactive dashboard for managing application versions, switching live traffic, simulating failures and performing automated rollbacks.

## Problem Statement

Traditional application deployments can cause service interruptions, failed releases and difficulties in restoring previous stable versions. ZeroDowntime addresses these challenges by maintaining two application environments and switching traffic only after successful health verification.

## Key Features

- Blue-Green deployment architecture
- Docker-based application containerization
- Nginx reverse proxy and traffic switching
- Automated application health monitoring
- Automatic rollback on consecutive health check failures
- Manual rollback functionality
- Failure simulation and recovery
- Interactive deployment dashboard
- Persistent deployment history
- Deployment duration tracking
- Live request monitoring
- Concurrent deployment protection
- Duplicate deployment prevention

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend and deployment automation |
| Flask | Dashboard and REST APIs |
| Docker | Application containerization |
| Docker Compose | Multi-container orchestration |
| Nginx | Reverse proxy and traffic routing |
| HTML, CSS, JavaScript | Dashboard interface |
| JSON | Deployment history storage |
| Git and GitHub | Version control |

## System Architecture

```text
                 Client Requests
                        |
                        v
                Nginx Reverse Proxy
                    Port 8080
                   /         \
                  /           \
          Blue Environment   Green Environment
             Version 1.0       Version 2.0
              Port 5001         Port 5002

                        ^
                        |
              Deployment Dashboard
                    Port 5050
                        |
            Health Monitoring & Rollback
```

## How It Works

1. Blue and Green application environments run independently in Docker containers.
2. Nginx directs incoming traffic to the currently active environment.
3. When a deployment is initiated, the target environment undergoes health verification.
4. If the health check succeeds, Nginx switches traffic to the target environment.
5. If the health check fails, the existing environment continues serving requests.
6. A background monitoring thread periodically checks the active environment.
7. After three consecutive health check failures, the system attempts to roll back to the previous healthy environment.
8. Deployment events and execution durations are recorded in the deployment history.

## Installation and Setup

### Prerequisites

- Docker Desktop
- Docker Compose
- Python 3
- Git

### Clone the repository

```bash
git clone https://github.com/nandini-wadhwaa/ZeroDowntime.git
cd ZeroDowntime
```

### Configure application health

Create a `.env` file in the project root:

```env
BLUE_HEALTHY=true
GREEN_HEALTHY=true
```

### Start Docker containers

```bash
docker compose up -d --build
```

### Set up the dashboard

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask
python dashboard/app.py
```

## Application URLs

| Service | URL |
|---|---|
| Deployment Dashboard | http://localhost:5050 |
| Live Application | http://localhost:8080 |
| Blue Environment | http://localhost:5001 |
| Green Environment | http://localhost:5002 |

## Dashboard Controls

| Control | Function |
|---|---|
| Deploy Version 2 | Verify Green and switch live traffic |
| Rollback | Restore the previous healthy environment |
| Simulate Green Failure | Recreate Green in an unhealthy state |
| Restore Green | Restore Green to a healthy state |
| Send Test Request | Verify live application response |
| Refresh Status | Update deployment information |

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/state` | GET | Current deployment status |
| `/api/history` | GET | Deployment history |
| `/api/deploy` | POST | Deploy Green environment |
| `/api/rollback` | POST | Perform manual rollback |
| `/api/failure` | POST | Simulate Green failure |
| `/api/restore` | POST | Restore Green environment |
| `/api/test-request` | POST | Test live application |

## Testing

The project includes testing scenarios for:

- Successful application deployment
- Rejection of unhealthy deployments
- Manual rollback
- Automatic rollback
- Application failure and recovery
- Concurrent deployment protection
- Continuous HTTP requests during traffic switching

To monitor application availability during deployment:

```bash
while true; do
  printf "%s " "$(date +%H:%M:%S)"
  curl --max-time 2 -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8080/
  sleep 0.2
done
```

## Screenshots

Project screenshots demonstrate the deployment dashboard, application versions, deployment history, automated rollback and availability testing.

## Limitations

- Currently designed for a local Docker environment.
- Automatic rollback depends on the dashboard monitoring process.
- Unexpected application failures may cause temporary service interruptions before rollback.
- Production-grade authentication and distributed infrastructure are not implemented.

## Future Scope

- CI/CD integration using GitHub Actions
- Cloud deployment using AWS
- Prometheus and Grafana monitoring
- Canary deployment support
- Kubernetes-based orchestration
- Role-based access control

## Conclusion

ZeroDowntime demonstrates practical DevOps concepts such as containerization, reverse proxy configuration, deployment automation, health monitoring and fault recovery. It illustrates how Blue-Green deployment can improve application availability and reduce deployment-related service interruptions.

## Developer

**Nandini**

B.Tech Computer Science and Engineering

Indira Gandhi Delhi Technical University for Women (IGDTUW)