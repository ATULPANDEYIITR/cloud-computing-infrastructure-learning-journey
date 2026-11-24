# Docker Multi-Service Application: Containerization, Networking and Persistent Storage

## 1. Project Architecture

This project implements a containerized task management application consisting of three independent services:

- Frontend: Node.js HTTP server and browser-based interface.
- Backend: Python HTTP API.
- Database: PostgreSQL relational database.

Docker Compose coordinates the services, manages startup dependencies, creates isolated networks, executes health checks and provisions persistent storage.

The architecture separates application responsibilities while maintaining controlled communication between containers.

### Service architecture

    Browser
       |
       | HTTP :3000
       v
    Frontend Container
       |
       | HTTP :3000 -> :8000
       v
    Backend Container
       |
       | PostgreSQL :5432
       v
    Database Container
       |
       v
    Named Persistent Volume
       |
       v
    PostgreSQL Data Directory

### Service responsibilities

| Service | Technology | Internal Port | Responsibility |
|---|---|---:|---|
| Frontend | Node.js 22 | 3000 | Browser interface and API proxy |
| Backend | Python 3.13 | 8000 | Business logic and HTTP endpoints |
| Database | PostgreSQL 17 | 5432 | Persistent relational storage |

The frontend is the only service published to the host. The backend and database remain accessible through Docker networks rather than direct host port publication.

## 2. Containerization Fundamentals

Containerization packages an application and its runtime dependencies into an executable image.

A container is a running instance of an image.

The distinction is important:

| Concept | Meaning |
|---|---|
| Dockerfile | Instructions for building an image |
| Image | Immutable application package |
| Container | Running image instance |
| Registry | Image distribution and storage |
| Docker Engine | Builds and runs containers |
| Docker Compose | Defines and manages multi-container applications |
| Volume | Persistent data storage |
| Network | Communication between containers |

Containers share the host operating system kernel. They do not require an independent guest operating system like traditional virtual machines.

### Image layers

Docker builds images using reusable layers.

A typical backend image follows this sequence:

1. Select a Python base image.
2. Set the application working directory.
3. Copy dependency definitions.
4. Install Python dependencies.
5. Copy application source.
6. Configure the runtime user.
7. Expose the application port.
8. Define the startup command.

Copying dependency definitions before application source allows Docker to reuse the dependency installation layer when application code changes without modifying dependencies.

### Build context

The build context is the collection of files available to a Docker build.

The project uses `.dockerignore` to exclude:

- Git metadata.
- Python cache files.
- Virtual environments.
- Local environment files.
- Unnecessary dependency directories.

Reducing the build context improves build performance and reduces the possibility of accidentally copying sensitive files into an image.

## 3. Multi-Service Application Design

The application uses independent containers rather than combining the frontend, backend and database into one image.

This separation provides several operational benefits:

- Independent image builds.
- Independent service restarts.
- Separate resource allocation.
- Independent health monitoring.
- Controlled network access.
- Easier service replacement.
- Better fault isolation.

### Frontend service

The Node.js frontend provides a browser interface for task creation and retrieval.

Its responsibilities include:

- Serving the HTML application.
- Validating basic browser input.
- Forwarding API requests.
- Handling upstream failures.
- Applying request-size restrictions.
- Exposing health and readiness endpoints.

The frontend uses the backend's Docker service name rather than a fixed IP address.

Docker's internal DNS resolves service names to the corresponding container addresses.

### Backend service

The Python backend implements task management endpoints.

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Process health |
| `/api/tasks` | GET | Retrieve tasks |
| `/api/tasks` | POST | Create a task |
| `/api/tasks/{id}` | PATCH | Update task status |

The backend separates HTTP handling, input validation and database operations.

Database queries use parameterized statements to prevent SQL injection through user-controlled values.

Each database operation uses a transaction-managed connection.

The API also implements:

- Request-size validation.
- Task title validation.
- Description length restrictions.
- Explicit HTTP status codes.
- Database failure handling.
- Structured operational logging.
- Graceful shutdown.

### Database service

PostgreSQL stores application records.

The database is not exposed directly to the host in the Compose architecture.

Only the backend receives access through the internal backend network.

The database uses a named Docker volume so that its data is not tied to the lifecycle of an individual database container.

## 4. Docker Compose and Service Orchestration

Docker Compose defines the application infrastructure declaratively.

The generated `compose.yaml` contains three services:

- `db`
- `backend`
- `frontend`

It also defines two networks and one named volume.

### Service dependency management

The intended startup sequence is:

    Database
       |
       | Healthcheck succeeds
       v
    Backend
       |
       | Healthcheck succeeds
       v
    Frontend

The configuration uses:

- `depends_on`
- `condition: service_healthy`
- Service health checks
- Restart policies

A dependency relationship alone does not establish application readiness.

A database container can exist while PostgreSQL is still initializing. The health condition ensures that the backend waits for the database's health check before starting.

Similarly, the frontend waits for the backend.

Health checks should test actual service functionality rather than merely checking whether a container process exists.

### Restart policies

| Policy | Behavior |
|---|---|
| `no` | Do not automatically restart |
| `always` | Restart regardless of exit reason |
| `unless-stopped` | Restart unless explicitly stopped |
| `on-failure` | Restart after unsuccessful termination |

Restart policies help recover from certain failures. They do not replace application-level error handling or monitoring.

## 5. Docker Networking

Docker networks provide communication boundaries between containers.

The application defines two bridge networks.

### Backend network

The backend network connects:

- Database.
- Backend API.

It is configured as an internal network.

The frontend does not belong to this network.

This reduces unnecessary network exposure.

### Frontend network

The frontend network connects:

- Frontend.
- Backend.

The frontend communicates with the backend through the service name `backend`.

The backend participates in both networks, allowing it to act as the controlled communication point between the frontend and database.

### Network relationship

    Frontend Network
       |
       +---- Frontend
       |
       +---- Backend
                  |
                  |
    Backend Network
                  |
                  +---- Database

### Service discovery

Container IP addresses can change when containers are recreated.

Therefore, applications should use Docker service names rather than hardcoded container IP addresses.

For example:

- `http://backend:8000`
- `db:5432`

These names remain associated with the services even when their underlying container addresses change.

### Port mapping

Docker port publication follows this general pattern:

`HOST_PORT:CONTAINER_PORT`

The frontend publishes port 3000.

The backend and database do not publish host ports in the supplied Compose architecture.

A container's `EXPOSE` instruction documents its intended application port. It does not independently publish that port to the host.

## 6. Persistent Storage and Data Management

Containers are replaceable runtime instances.

Data stored only in a container's writable filesystem can disappear when the container is removed.

This makes persistent storage essential for databases.

### Named volumes

The Compose configuration defines:

`postgres_data`

The volume is mounted at:

`/var/lib/postgresql/data`

This is the PostgreSQL data directory for the selected PostgreSQL image configuration.

The named volume exists independently of the database container.

### Storage comparison

| Storage mechanism | Lifetime | Typical purpose |
|---|---|---|
| Container writable layer | Container lifetime | Temporary runtime changes |
| Named volume | Independent of container | Database persistence |
| Bind mount | Host filesystem dependent | Development files and configuration |
| tmpfs | Memory lifetime | Temporary sensitive data |

### Persistence workflow

1. Docker creates the named volume.
2. PostgreSQL initializes its data directory.
3. Database records are written to the mounted volume.
4. The container stops or is recreated.
5. The replacement container mounts the same volume.
6. PostgreSQL recovers its existing database state.

Named volumes do not constitute backups.

Production environments require independent backup, restoration, retention and disaster-recovery procedures.

Removing containers and removing volumes are different operations.

A deployment should never remove production database volumes as part of routine application replacement.

## 7. Health Checks and Application Readiness

Container health checks determine whether a service is functioning according to a defined test.

The Compose configuration includes health checks for all three services.

### Database health

The database uses `pg_isready`.

This checks whether PostgreSQL is accepting connections.

### Backend health

The backend exposes `/health`.

The endpoint returns service information and a healthy status.

### Frontend health

The frontend exposes `/health`.

It also provides `/ready`, which checks backend availability.

### Health versus readiness

These concepts are related but distinct.

| Concept | Meaning |
|---|---|
| Process running | Application process exists |
| Container running | Container is executing |
| Healthy | Configured health check succeeds |
| Ready | Service can perform its intended work |
| Available | Service can receive and successfully handle requests |

A frontend can be healthy while its backend dependency is unavailable.

For this reason, a production monitoring system should track both local health and dependency readiness.

A health check should also avoid creating expensive database operations on every monitoring interval.

## 8. Python Implementation

The Python implementation represents the backend application and its operational lifecycle.

### Main components

| Component | Responsibility |
|---|---|
| `Task` | Immutable-style task data representation |
| `TaskRepository` | PostgreSQL operations |
| `validate_task()` | Request validation |
| `APIHandler` | HTTP request processing |
| `scaffold_project()` | Infrastructure file generation |
| `main()` | Application startup and shutdown |

The repository layer uses UUID identifiers and PostgreSQL transactions.

Database connections use a configurable connection timeout.

The application retries initial database connections with bounded exponential backoff.

### Error handling

The API distinguishes:

- Invalid input.
- Missing routes.
- Missing task records.
- Database connectivity failures.
- Unexpected server errors.

The backend does not return raw database exception messages to clients.

Operational details remain in server logs.

### Security considerations

The implementation includes:

- Non-root container execution.
- Parameterized SQL statements.
- Request-size restrictions.
- Input validation.
- Configurable database credentials.
- Restricted service exposure.

The scaffold's default database username and password are development defaults. Production deployment requires a strong secret and appropriate secret-management controls.

## 9. JavaScript Implementation

The JavaScript implementation provides an event-driven frontend service.

Node.js handles multiple HTTP connections through its asynchronous execution model.

The implementation uses:

- `http.createServer()`
- `Map`
- `URL`
- `fetch()`
- `AbortController`
- `Promise`-based request handling
- Event listeners
- Graceful shutdown signals

### API proxy mechanism

The browser communicates with the frontend.

The frontend forwards API requests to the backend.

This design avoids requiring browsers to connect directly to the backend container network.

The frontend acts as a controlled application gateway.

### Request processing

The proxy:

1. Validates the request method.
2. Restricts request body size.
3. Parses JSON input.
4. Constructs an internal backend destination.
5. Applies an upstream timeout.
6. Returns the backend response.
7. Handles failures without exposing internal implementation details.

The browser interface uses `textContent` when displaying user-controlled values.

This reduces the risk of HTML injection through task titles and descriptions.

The example uses inline JavaScript and a permissive inline-script CSP directive for a self-contained demonstration. A production frontend should move scripts into static files and use a stricter Content Security Policy.

## 10. C++17 Deployment Governance Engine

The C++ implementation models container startup as a dependency graph.

Its purpose is to evaluate whether services can start in the correct order and whether the complete application becomes healthy.

### Domain model

The implementation defines:

- `Service`
- `ServiceState`
- `DeploymentResult`
- `DeploymentEngine`

### Dependency graph

The application represents dependencies as a directed graph.

    Database
       |
       v
    Backend
       |
       v
    Frontend

The engine uses depth-first search to determine a valid startup order.

### Cycle detection

Each node has one of three traversal states:

| Value | Meaning |
|---|---|
| 0 | Not visited |
| 1 | Currently being processed |
| 2 | Fully processed |

Encountering a node that is currently being processed indicates a dependency cycle.

For example:

    Service A -> Service B
         ^           |
         |___________|

This architecture cannot be started using a valid dependency ordering.

### Deployment evaluation

The engine:

1. Validates service registrations.
2. Validates dependencies.
3. Detects circular dependencies.
4. Calculates startup order.
5. Checks dependency health.
6. Evaluates simulated health results.
7. Records failures and restart attempts.
8. Produces a deployment report.

The graph traversal has time complexity of `O(V + E)`, where `V` represents services and `E` represents dependency relationships.

The C++ program is a deployment simulation, not a Docker Engine client.

## 11. Java 17 Enterprise Governance Model

The Java implementation provides a structured enterprise-oriented deployment model.

It uses records, enums, immutable collections and service classes.

### Domain types

| Type | Purpose |
|---|---|
| `ServiceDefinition` | Service configuration |
| `ResourceLimits` | CPU and memory allocation |
| `NetworkConfiguration` | Network membership and exposure |
| `ServiceRuntime` | Runtime state management |
| `DeploymentService` | Deployment governance |
| `GovernanceException` | Explicit policy failures |

### Resource governance

Every service has:

- Memory limits.
- CPU allocation.
- Network membership.
- Restart policy.
- Persistent storage requirements.
- Health check configuration.

These values support configuration validation before deployment.

### Network governance

The implementation checks that:

- Frontend and backend share a network.
- Backend and database share a network.
- Database storage is persistent.
- Database exposure is disabled.

### State transitions

The application uses explicit deployment states:

    CREATED
       |
       v
    STARTING
       |
       +----> HEALTHY
       |
       +----> UNHEALTHY
       |
       +----> FAILED

The runtime model prevents invalid state transitions.

A service cannot be considered healthy merely because it was registered.

### Enterprise implications

A deployment governance service should evaluate architecture and security constraints before executing operational actions.

The Java implementation demonstrates this separation between configuration validation and runtime execution.

It does not invoke the Docker Engine API or enforce operating-system resource limits directly.

## 12. PostgreSQL Data Model

The SQL implementation provides relational storage for application records and infrastructure monitoring.

### Main entities

| Table | Responsibility |
|---|---|
| `application_users` | Application identities |
| `tasks` | Task records |
| `docker_services` | Service registry |
| `service_dependencies` | Dependency relationships |
| `docker_networks` | Network definitions |
| `service_network_memberships` | Service-to-network mapping |
| `service_health_checks` | Health check history |

### Relationship model

    Application Users
           |
           v
         Tasks

    Docker Services
           |
           +---- Service Dependencies
           |
           +---- Network Memberships
           |
           +---- Health Check History
           |
           v
      Service Readiness

### Integrity enforcement

PostgreSQL constraints enforce:

- Unique service names.
- Unique usernames and email addresses.
- Valid task titles.
- Supported task statuses.
- Valid container ports.
- Valid restart policies.
- Mandatory database persistence.
- Restrictions against public database exposure.

Foreign keys maintain referential integrity between related entities.

Indexes support common access patterns, including task filtering, chronological retrieval and health history lookup.

### Triggers

The task update trigger automatically changes `updated_at` whenever a task is modified.

This prevents application code from needing to manage the timestamp independently.

### Views and reporting

The SQL script defines:

- `latest_service_health`
- `service_readiness`
- `task_status_report`

These provide reusable reporting structures.

A recursive CTE traverses service dependencies and identifies the relationship depth.

The deployment readiness function combines service state, health results, database persistence and database exposure constraints.

The health history is intentionally separate from the current deployment state. Recording a health check does not automatically change the service's deployment state.

## 13. Deployment Workflow

The project uses a reproducible local deployment process.

### Initial setup

The Python script generates:

- `compose.yaml`
- `Dockerfile.backend`
- `Dockerfile.frontend`
- `requirements.txt`
- `.dockerignore`
- `.env.example`

The frontend source is stored as `frontend.js`.

The backend source is stored as `app.py`.

The database initialization script can be stored separately as `init.sql` and mounted into PostgreSQL's initialization directory when automatic first-time initialization is required.

### Environment configuration

Create `.env` from `.env.example`.

Set a strong database password.

Ensure that `DATABASE_URL` uses the same username, password, database and service name as the PostgreSQL configuration.

The database hostname inside Docker Compose must be `db`, not `localhost`.

Inside a container, `localhost` refers to that same container.

### Build and start

Run the following commands from the project directory:

- `python app.py --scaffold`
- `docker compose config`
- `docker compose build`
- `docker compose up -d`

The frontend is accessible at:

`http://localhost:3000`

The backend is accessible internally at:

`http://backend:8000`

PostgreSQL is accessible internally at:

`db:5432`

### Inspect the deployment

Useful operational commands include:

- `docker compose ps`
- `docker compose logs`
- `docker compose logs backend`
- `docker compose logs frontend`
- `docker compose logs db`
- `docker compose top`
- `docker compose images`
- `docker network ls`
- `docker volume ls`

These commands help identify startup failures, unhealthy services, image configuration problems and storage issues.

### Stop the application

`docker compose down`

This removes the application containers and Compose-created networks but preserves the named volume.

Starting the application again with `docker compose up -d` reuses the existing database volume.

Avoid `docker compose down -v` when existing database data must be retained.

## 14. Failure Scenarios and Recovery

| Failure | Likely cause | Operational response |
|---|---|---|
| Database unhealthy | Initialization or storage failure | Inspect database logs |
| Backend cannot connect | Incorrect credentials or hostname | Verify environment configuration |
| Frontend returns 502 | Backend unavailable | Inspect backend health and logs |
| Port binding failure | Host port already occupied | Change the published host port |
| Container exits repeatedly | Application startup error | Inspect exit code and logs |
| Data disappears | Volume removed or incorrect mount | Verify volume configuration and backups |
| Dependency cycle | Invalid service relationships | Correct the dependency graph |
| Image build fails | Invalid Dockerfile or dependency | Inspect build output |
| Health check fails | Wrong endpoint or application failure | Test the health command inside the container |

### Restart and recovery distinction

Restarting a container does not necessarily repair the underlying problem.

For example, a database authentication error remains unresolved if the backend repeatedly restarts with incorrect credentials.

Operational recovery should identify the underlying failure before applying repeated restarts.

## 15. Security and Production Considerations

The demonstration establishes several basic security boundaries, but production deployment requires further controls.

### Container security

- Run application processes as non-root users.
- Use trusted and maintained base images.
- Pin image versions and preferably immutable digests.
- Scan images for known vulnerabilities.
- Avoid unnecessary Linux capabilities.
- Apply CPU and memory limits.
- Use read-only root filesystems where practical.
- Avoid embedding credentials in image layers.

### Network security

- Publish only necessary ports.
- Keep databases on private networks.
- Restrict access between services.
- Apply firewall and host security policies.
- Use TLS for communication across untrusted networks.

### Secret management

Environment variables are convenient for configuration, but production secrets require controlled storage, access permissions and rotation.

Do not commit `.env` files containing real credentials.

### Database security

- Use a dedicated application database role.
- Apply least-privilege permissions.
- Restrict administrative access.
- Back up persistent volumes.
- Test database restoration.
- Encrypt backups.
- Monitor connection usage.
- Configure retention policies.

### Observability

A production deployment should collect:

- Container resource usage.
- Application logs.
- Database logs.
- Health-check failures.
- Request latency.
- Error rates.
- Restart counts.
- Storage utilization.

Health checks alone are not a complete monitoring solution.

## 16. Performance and Scalability

Containerized services can scale independently, subject to their state and resource requirements.

The frontend and backend can be replicated when application behavior supports multiple instances.

PostgreSQL requires more careful scaling because it manages persistent transactional state.

### Performance considerations

| Component | Important consideration |
|---|---|
| Frontend | Asynchronous request handling |
| Backend | Database connection management |
| PostgreSQL | Index design and query plans |
| Docker images | Layer reuse and smaller build contexts |
| Networking | Avoid unnecessary external traffic |
| Storage | Volume performance and backup overhead |
| Orchestration | Startup dependencies and health intervals |

The demonstration creates a new PostgreSQL connection for each repository operation.

A production backend should use a bounded connection pool with appropriate connection limits, timeouts and cleanup.

The example also limits task retrieval to 500 records. Larger workloads require pagination and appropriate query strategies.

Horizontal scaling requires attention to:

- Stateless application design.
- Shared persistent storage.
- Database connection limits.
- Session management.
- Load balancing.
- Idempotent operations.
- Graceful termination.

## 17. Technical Distinctions

Several infrastructure concepts must remain distinct.

| Concept | What it controls |
|---|---|
| Docker image | Application packaging |
| Container | Runtime execution |
| Compose service | Declarative service configuration |
| Compose project | Coordinated application deployment |
| Network | Container communication |
| Volume | Persistent data |
| Health check | Runtime condition evaluation |
| Dependency condition | Startup ordering and health gating |
| Restart policy | Container restart behavior |
| Resource limit | Runtime resource allocation |

A successful image build does not prove that an application is operational.

A running container does not prove that its dependencies are available.

A healthy database does not prove that the complete application is ready.

A persistent volume does not guarantee that data can be recovered after a storage failure.

These distinctions are essential when designing reliable multi-service deployments.

## 18. Implementation Coverage

| Deliverable | Implemented capability |
|---|---|
| Python | Backend API, validation, PostgreSQL repository, scaffolding |
| JavaScript | Frontend interface, asynchronous proxy, request controls |
| C++17 | Dependency graph, cycle detection, deployment simulation |
| Java 17 | Enterprise configuration validation, state transitions, network governance |
| PostgreSQL | Application persistence, service registry, dependencies, health reporting |

The five implementations address separate aspects of the same multi-service application architecture.

The Python and JavaScript services implement the application runtime. C++ and Java provide independent deployment-governance simulations. PostgreSQL provides the relational data model and operational reporting mechanisms.

The actual container lifecycle, network creation, image building and volume management are handled by Docker Compose and the Docker Engine.
