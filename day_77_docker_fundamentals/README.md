# Docker Fundamentals: Architecture, Images, Containers and Registries

## 1. Project Scope

Docker is a containerization platform that packages applications and their dependencies into portable units called containers.

This project implements five complementary technical perspectives on Docker fundamentals:

- Python: repository and container runtime simulation.
- JavaScript: asynchronous, event-driven container management.
- C++17: resource-aware runtime and operational governance engine.
- Java 17: enterprise container platform with explicit domain models.
- PostgreSQL: relational inventory, lifecycle, registry and resource-management system.

The implementations focus on Docker architecture, Docker client, Docker daemon, images, containers, image layers and registries.

The programs simulate Docker Engine behavior. They do not replace the actual Docker Engine, containerd, OCI runtime or registry protocols.

## 2. Docker Architecture

Docker uses a client-server architecture.

The Docker client sends requests to the Docker daemon. The daemon manages images, containers, networks and volumes and coordinates container execution through the underlying runtime components.

### Architecture diagram

Docker CLI / Docker SDK

↓

Docker REST API

↓

Docker Daemon (`dockerd`)

↓

Containerd

↓

OCI Runtime (commonly `runc`)

↓

Linux Kernel

↓

Running Containers

The registry operates as a separate image-distribution service.

### Major components

| Component | Responsibility |
|---|---|
| Docker Client | Accepts commands and sends API requests |
| Docker Daemon | Manages Docker resources and coordinates operations |
| Docker Engine API | Communication interface between clients and the daemon |
| Containerd | Manages container lifecycle operations |
| OCI Runtime | Creates and runs containers using operating-system facilities |
| Docker Image | Read-only application filesystem and configuration |
| Docker Container | Runtime instance created from an image |
| Docker Registry | Stores and distributes container images |

### Docker Client

The Docker client is the user-facing interface.

Typical commands include:

- `docker version`
- `docker info`
- `docker images`
- `docker pull`
- `docker build`
- `docker run`
- `docker ps`
- `docker stop`
- `docker rm`
- `docker push`

The client communicates with the daemon using the Docker Engine API.

The CLI is not itself the container runtime. It requests operations from the daemon.

A client can communicate with a local daemon or a remotely accessible daemon, subject to authentication and transport configuration.

### Docker Daemon

The Docker daemon, commonly called `dockerd`, manages Docker resources.

Its responsibilities include:

- Image management.
- Container creation and lifecycle management.
- Network management.
- Volume management.
- Registry interactions.
- Resource configuration.
- Communication with containerd.

The daemon maintains the operational state of Docker resources.

Daemon availability is important because normal Docker Engine management operations depend on communication with it.

A daemon failure does not necessarily terminate already-running containers. Existing workloads may continue under the underlying runtime, depending on the failure and configuration.

## 3. Docker Images

A Docker image is an immutable template used to create containers.

An image contains:

- Application files.
- Runtime dependencies.
- Filesystem layers.
- Configuration metadata.
- Default environment variables.
- Entrypoint and command information.
- Operating-system and architecture information.

An image is not a running application.

A container is created from an image.

### Image layers

Docker images are constructed using filesystem layers.

For example, a Dockerfile might contain:

1. `FROM python:3.13-slim`
2. `WORKDIR /app`
3. `COPY requirements.txt .`
4. `RUN pip install -r requirements.txt`
5. `COPY application.py .`
6. `CMD ["python", "application.py"]`

The image build process produces filesystem changes and image configuration.

Layers can be reused between compatible images.

This reduces redundant storage and can improve build performance.

### Copy-on-write behavior

Container images provide read-only filesystem layers.

When a container starts, a writable container layer is created above the image layers.

The container can write changes without modifying the original image.

Conceptually:

Container Writable Layer

↓

Image Layer 4

↓

Image Layer 3

↓

Image Layer 2

↓

Base Image Layer

The writable layer belongs to the container and is not a substitute for persistent volumes.

Important distinction:

- Image layers are reusable image components.
- The container writable layer contains runtime filesystem changes.
- Volumes provide separate persistent storage.

### Image identifiers and tags

An image digest identifies content through a cryptographic hash.

A tag is a human-readable reference.

Examples:

- `python:3.13-slim`
- `nginx:stable`
- `company/web-service:1.0`
- `company/web-service:latest`

Tags can be reassigned to different image content.

A digest provides content-addressed identification and is preferable when a deployment requires an exact image reference.

A tag such as `latest` does not automatically mean the newest image available in every registry. It is simply a tag name.

### Image caching

Docker can reuse existing image layers during builds and pulls.

If a layer is already present, downloading it again may be unnecessary.

Layer reuse depends on content identity and build configuration.

Good Dockerfile design places relatively stable dependencies before frequently changing application files.

This can reduce unnecessary rebuilding.

## 4. Docker Containers

A container is a runtime instance created from an image.

Containers provide isolated processes and filesystem views using operating-system facilities.

Linux container isolation commonly uses:

- Namespaces for process, network and other resource isolation.
- Control groups for resource accounting and limits.
- Capabilities for restricting privileged operations.
- Linux security modules where configured.
- Filesystem layers for application files.

Containers share the host kernel. They are not equivalent to virtual machines with separate guest operating-system kernels.

### Container lifecycle

The implementations model these principal states:

| State | Meaning |
|---|---|
| Created | Container configuration exists but execution has not started |
| Running | Container process is executing |
| Stopped | Container has been stopped |
| Exited | Container process has terminated |
| Paused | Container processes are temporarily frozen |
| Removed | Container resource has been deleted |

A simplified lifecycle is:

Created → Running → Stopped → Running → Removed

An exited container can also be restarted if it has not been removed.

A removed container cannot be restarted.

### Container configuration

A container can be configured with:

- Image reference.
- Container name.
- Environment variables.
- Port mappings.
- Memory limits.
- CPU limits.
- Restart policies.
- Storage mounts.
- Network configuration.

The implementations validate resource requests and port mappings before starting containers.

### Port mapping

A container can expose an application port independently of the host port.

For example:

`8080:8000`

This represents:

- Host port: `8080`
- Container port: `8000`

The application listens inside the container on port `8000`.

The host forwards traffic through port `8080`.

A port conflict occurs when another active container or host process already owns the requested host port.

The simulations maintain host-port reservations to demonstrate this condition.

### Resource limits

Memory and CPU constraints help control resource consumption.

Example:

`docker run --memory=512m --cpus=1.0 nginx`

This configures a memory limit of 512 MB and a CPU quota equivalent to one CPU under Docker's resource-control configuration.

The implementations use resource reservation models to reject allocations exceeding simulated daemon capacity.

Actual Docker resource enforcement is performed through operating-system mechanisms rather than the application-level dictionaries or collections used in these examples.

### Container persistence

Container writable layers are generally treated as disposable.

Removing a container can remove its writable filesystem layer.

Persistent application data should be stored in volumes or appropriately managed bind mounts.

Container lifecycle management and persistent-data management are separate concerns.

## 5. Docker Registries

A Docker registry stores and distributes container images.

A registry allows developers and deployment systems to exchange images without rebuilding them independently.

Examples include:

- Docker Hub.
- Private enterprise registries.
- Cloud-managed container registries.
- Self-hosted registry services.

### Registry workflow

Developer

↓

Build Image

↓

Tag Image

↓

Authenticate

↓

Push Image

↓

Registry Storage

↓

Authenticate Deployment System

↓

Pull Image

↓

Create Container

### Push operation

An image is uploaded to a registry using a reference such as:

`docker push company/web-service:1.0`

The operation requires the appropriate registry permissions.

A successful push makes the image available for retrieval, subject to registry access policies.

### Pull operation

A deployment system retrieves an image using:

`docker pull company/web-service:1.0`

The daemon obtains the required image content and metadata.

Existing layers can be reused when the required content is already available locally.

### Registry authentication

Private registries require authentication.

Typical access controls distinguish:

- Pull permissions.
- Push permissions.
- Repository access.
- User and service-account permissions.

Production systems should use secret managers or protected credential stores.

Access tokens and passwords should not be hardcoded into Dockerfiles, source code or application logs.

### Tags versus digests

| Property | Tag | Digest |
|---|---|---|
| Identification | Human-readable | Content-addressed |
| Mutability | Can be reassigned | Identifies specific content |
| Deployment use | Convenient reference | Exact content reference |
| Example | `web-service:stable` | `web-service@sha256:...` |

For production deployments, digest-based image references improve reproducibility.

## 6. Python Implementation

The Python script provides a complete Docker environment simulator.

### Main classes

| Class | Responsibility |
|---|---|
| `DockerDaemon` | Maintains image, container, registry and runtime state |
| `DockerClient` | Provides client-facing operations |
| `Image` | Represents image metadata and layers |
| `ImageLayer` | Represents an individual filesystem layer |
| `Container` | Represents a container and its lifecycle |
| `Registry` | Represents registry storage and authentication |
| `ContainerStatus` | Defines container states |
| `ResourceError` | Represents resource-allocation failures |

### Important mechanisms

The daemon uses dictionaries to maintain resource relationships.

The image-tag dictionary maps image references to image identifiers.

Container records reference their source images using image IDs.

Port reservations are maintained separately from container metadata.

This makes port-conflict detection efficient.

The simulator supports:

- Image construction.
- Image inspection.
- Image tagging.
- Registry authentication.
- Image push and pull.
- Container creation.
- Container startup and shutdown.
- Container removal.
- Resource validation.
- Event recording.
- Inventory persistence.

### Validation and failure handling

The implementation rejects:

- Invalid image references.
- Empty image layers.
- Duplicate container names.
- Invalid port mappings.
- Occupied host ports.
- Invalid resource allocations.
- Missing registry images.
- Unauthorized registry operations.
- Invalid lifecycle transitions.

The inventory snapshot uses JSON serialization and a temporary file before replacement.

It represents a management snapshot, not a complete Docker daemon backup.

## 7. JavaScript Implementation

The JavaScript implementation uses an asynchronous, event-driven architecture.

It demonstrates how a container-management service can coordinate multiple operations.

### Main components

| Component | Responsibility |
|---|---|
| `DockerDaemon` | Coordinates image and container operations |
| `DockerClient` | Exposes client operations |
| `Image` | Maintains immutable image metadata |
| `Registry` | Handles image distribution |
| `Container` | Maintains runtime state |
| `ResourceManager` | Controls memory and CPU reservations |
| `MergeIndependentPolicy` | Demonstrates a separate policy-evaluation mechanism |

### Asynchronous operations

Registry transfers are asynchronous.

Promises represent operations that may complete or fail later.

The daemon uses a serialized operation queue for state-changing operations.

This reduces race conditions when concurrent requests attempt to reserve the same port or consume the same resource capacity.

### Event-driven architecture

The daemon extends Node.js `EventEmitter`.

It emits events for:

- Image construction.
- Image transfer.
- Container creation.
- Container startup.
- Container shutdown.
- Container removal.

An event listener records operational information without coupling the event consumer to the resource-management implementation.

### Resource management

`ResourceManager` tracks allocations using a `Map`.

It calculates current resource usage and validates new reservations.

Reservations are released when containers stop.

### Security considerations

The demonstration includes registry authentication and timing-safe token comparison.

The registry's in-memory credential storage is educational only.

A production service should use:

- Secret-manager integration.
- Short-lived credentials.
- Least-privilege registry permissions.
- TLS.
- Audit logging.
- Protected daemon endpoints.

The inventory file is written with restricted file permissions.

## 8. C++17 Implementation

The C++ implementation emphasizes explicit domain modeling and predictable runtime operations.

### Main components

| Component | Responsibility |
|---|---|
| `DockerDaemon` | Owns runtime state |
| `DockerClient` | Requests container operations |
| `Image` | Stores image identity and layer information |
| `ImageLayer` | Represents image filesystem layers |
| `Container` | Maintains container state |
| `Registry` | Models image publication |
| `ResourceCapacity` | Defines daemon capacity |
| `ResourceUsage` | Represents current consumption |
| `GovernanceEngine` | Evaluates a separate repository policy |

### STL data structures

The program uses:

- `unordered_map` for image and container lookup.
- `map` for ordered mappings and port allocations.
- `set` for required status checks.
- `vector` for image layers, logs and events.

Hash-map lookups provide average constant-time access.

Ordered maps are used where deterministic ordering and key-based traversal are useful.

### Resource allocation

The daemon validates available memory and CPU before starting a container.

It also validates all requested ports before reserving them.

This avoids partial resource allocation when a request fails validation.

Stopping a container releases its reservations.

### State management

Container state changes are performed through explicit lifecycle methods.

Illegal operations generate exceptions.

The implementation includes assertions that verify container cleanup and resource release.

### Identifier limitation

The C++ image identifier uses the standard-library hash facility for demonstration.

It is not a cryptographic image digest and must not be treated as a secure content identity.

The JavaScript, Java and Python implementations use SHA-256 for their simulated image identifiers.

A real image implementation must follow the appropriate OCI image and digest specifications.

## 9. Java 17 Implementation

The Java implementation models a container platform using enterprise-oriented domain types.

### Domain architecture

The implementation separates:

- Image metadata.
- Container configuration.
- Runtime state.
- Registry authentication.
- Resource allocation.
- Audit events.
- Enterprise policy evaluation.

### Java 17 features

The program uses records for immutable data structures.

Examples include:

- `ImageLayer`
- `Image`
- `ContainerConfiguration`
- `ResourceCapacity`
- `ResourceAllocation`
- `AuditEvent`
- `RepositoryPolicy`
- `PullRequest`
- `MergeDecision`

Enums define controlled lifecycle and decision states.

Interfaces separate eligibility evaluation from the implementation that performs it.

Collections and streams support inventory queries and resource aggregation.

### State transitions

The `Container` class validates state transitions.

An invalid transition generates a `ConflictException`.

This prevents removed containers from being restarted and running containers from being removed without stopping them.

### Resource allocation

The `ResourceManager` synchronizes resource reservation and release.

The implementation calculates total allocated memory and CPU before accepting new reservations.

The daemon also synchronizes its state-changing operations.

This provides a simplified concurrency-control model.

### Auditability

Each important operation produces an `AuditEvent`.

The audit history provides a record of image and container operations.

An enterprise implementation would extend this model with durable event storage, authenticated identities, timestamps from trusted infrastructure and retention policies.

## 10. PostgreSQL Database Architecture

The PostgreSQL implementation models a relational Docker inventory and operational management system.

The database represents infrastructure and lifecycle records independently of the in-memory implementations.

### Entity relationships

Docker Host

↓

Docker Daemon

↓

Containers

↓

Images

↓

Image Repositories

↓

Registries

Additional relationships:

- Images → Image Layers
- Images → Image Tags
- Images → Image Transfers
- Containers → Container Ports
- Containers → Environment Variables
- Containers → Logs
- Containers → Resource Allocations
- Daemons → Docker Events

### Core tables

| Table | Purpose |
|---|---|
| `docker_hosts` | Physical or virtual host inventory |
| `docker_daemons` | Docker daemon configuration and availability |
| `registries` | Registry information |
| `registry_accounts` | Registry permissions and credential references |
| `image_repositories` | Image repository ownership |
| `images` | Image metadata and digest |
| `image_layers` | Filesystem layer information |
| `image_tags` | Image reference management |
| `image_transfers` | Push and pull history |
| `containers` | Container inventory and lifecycle state |
| `container_ports` | Host and container port mappings |
| `container_environment` | Container environment configuration |
| `container_logs` | Operational log records |
| `resource_allocations` | Memory and CPU allocations |
| `docker_events` | Operational audit history |

### Constraints

The database uses:

- Primary keys.
- Foreign keys.
- Unique constraints.
- Check constraints.
- Partial indexes where appropriate.
- JSONB for event metadata.

The schema ensures that image references, container identities and registry relationships remain consistent.

### Triggers

The container insertion trigger validates daemon availability and image availability.

The port trigger detects conflicting active port assignments.

The resource-allocation trigger checks host capacity while locking the corresponding daemon row.

These mechanisms provide database-level integrity checks.

### Lifecycle function

`change_container_state()` validates container state transitions.

It coordinates:

1. Container state validation.
2. Daemon availability.
3. Port-conflict detection.
4. Resource allocation.
5. Resource release.
6. Event recording.

The operation runs within the caller's transaction.

### Registry procedure

`register_image_transfer()` validates image and registry availability before recording a transfer.

It creates a transfer record and marks the operation successful in the demonstration database.

A production registry integration would update the transfer state only after receiving a verified response from the actual registry service.

### Views

The database defines three operational views:

- `v_container_inventory`
- `v_daemon_resource_usage`
- `v_registry_image_inventory`

These provide simplified reporting interfaces without requiring repeated joins in every query.

### Important database limitation

The database models Docker operational state. It does not independently start containers, download image layers, authenticate against a real registry or enforce Linux kernel resource limits.

Those actions require integration with the Docker Engine API and underlying infrastructure.

## 11. Distinguishing the Core Concepts

The five implementations use different abstractions, but the underlying distinctions remain consistent.

| Concept | Meaning | Operational role |
|---|---|---|
| Docker Client | Interface for submitting requests | Sends commands |
| Docker Daemon | Resource-management service | Coordinates operations |
| Image | Immutable application template | Provides container filesystem and configuration |
| Image Layer | Reusable filesystem component | Supports image construction and distribution |
| Container | Runtime instance | Executes application processes |
| Registry | Image distribution service | Stores and distributes images |
| Container Runtime | Execution component | Creates and manages isolated processes |

The distinctions matter because an image, a container and a registry represent different stages of the application lifecycle.

Building an image does not start a container.

Pushing an image does not deploy an application.

Pulling an image does not automatically execute it.

Creating a container does not guarantee that its application will remain healthy.

## 12. Operational Workflow

A typical development and deployment workflow follows this sequence:

### Development

1. Write the application.
2. Create a Dockerfile.
3. Select a base image.
4. Define the working directory.
5. Install dependencies.
6. Copy application files.
7. Define the startup command.
8. Build the image.

### Distribution

1. Assign a repository and tag.
2. Authenticate to the registry.
3. Push the image.
4. Record the image digest.
5. Verify the registry artifact.

### Deployment

1. Authenticate to the registry.
2. Pull the image.
3. Verify the expected image identity.
4. Configure environment variables.
5. Configure ports and resources.
6. Create the container.
7. Start the container.
8. Inspect logs and runtime state.

### Maintenance

1. Monitor resource usage.
2. Investigate application failures.
3. Stop containers when required.
4. Restart eligible containers.
5. Remove obsolete containers.
6. Manage unused images.
7. Preserve application data in persistent storage.

## 13. Failure Conditions and Their Implications

| Failure | Cause | Appropriate handling |
|---|---|---|
| Daemon unavailable | Docker service failure | Restore daemon connectivity |
| Image not found | Invalid reference or missing pull | Verify repository and tag |
| Registry authentication failure | Invalid or expired credentials | Renew authorized credentials |
| Image pull failure | Network or registry problem | Retry with controlled backoff |
| Image build failure | Invalid instructions or dependencies | Inspect build output |
| Port conflict | Host port already allocated | Select an available port |
| Insufficient memory | Resource capacity exceeded | Adjust limits or host capacity |
| Insufficient CPU | Resource quota exceeded | Reassess workload allocation |
| Container exits | Application process terminates | Inspect logs and exit status |
| Invalid lifecycle transition | Operation incompatible with state | Inspect current container state |
| Image architecture mismatch | Incompatible image platform | Select or build the appropriate platform image |

Failure handling should preserve existing resource allocations and avoid leaving containers in inconsistent states.

## 14. Security and Production Considerations

### Image security

- Use trusted base images.
- Pin production dependencies.
- Verify image digests.
- Scan images for known vulnerabilities.
- Minimize unnecessary packages.
- Avoid including credentials in image layers.
- Maintain image provenance.

### Container security

- Run processes as non-root users where possible.
- Apply memory and CPU limits.
- Restrict Linux capabilities.
- Avoid privileged containers unless essential.
- Use read-only root filesystems when suitable.
- Restrict unnecessary network access.
- Apply appropriate seccomp and security-module policies.

### Registry security

- Use TLS.
- Require authentication for private repositories.
- Apply separate push and pull permissions.
- Prefer short-lived credentials.
- Rotate access credentials.
- Record image publication and retrieval events.

### Daemon security

Docker daemon access is highly privileged.

Access to a rootful Docker daemon can provide effective host-level control.

Production environments should:

- Restrict access to the Docker socket.
- Avoid exposing unauthenticated daemon endpoints.
- Apply least-privilege access.
- Protect remote API communication.
- Monitor administrative operations.
- Separate development and production infrastructure.

### Logging and monitoring

Operational monitoring should include:

- Daemon availability.
- Container restart counts.
- Container exit codes.
- CPU utilization.
- Memory consumption.
- Image pull failures.
- Registry authentication failures.
- Storage utilization.
- Network and port availability.

## 15. Performance and Design Considerations

### Image optimization

Smaller images generally require less storage and less data transfer.

Multi-stage builds can separate build dependencies from runtime dependencies.

Layer caching can reduce unnecessary rebuilds.

### Container optimization

Resource limits prevent individual workloads from consuming unlimited resources.

Limits must be chosen according to application requirements.

Excessively restrictive settings can cause application failures.

### Registry optimization

Registry caching and layer reuse can reduce repeated image transfers.

Image retention policies help control storage consumption.

### Database optimization

The PostgreSQL implementation uses indexes for common inventory and event queries.

Foreign keys maintain relationships between resources.

JSONB supports flexible event metadata.

Operational reports use views and aggregation queries to avoid repeating complex joins.

### Concurrency

Concurrent container-start operations must not reserve the same host port or exceed daemon capacity.

The in-memory implementations use serialized or synchronized operations.

The database uses transactions and row locking for resource-allocation validation.

Production systems must also consider multiple Docker daemons, distributed coordination, retry behavior and reconciliation after failures.

## 16. Running the Implementations

| Deliverable | Runtime | Execution |
|---|---|---|
| Python | Python 3.10+ | `python docker_fundamentals.py` |
| JavaScript | Node.js 18+ | `node docker_fundamentals.js` |
| C++17 | C++17 compiler | `g++ -std=c++17 -O2 -Wall -Wextra -pedantic docker.cpp -o docker` |
| Java | Java 17 | `javac DockerFundamentals.java` followed by `java DockerFundamentals` |
| PostgreSQL | PostgreSQL 15+ | Execute the SQL script using `psql` |

The Python and JavaScript programs create a JSON inventory file in the working directory.

The C++ and Java programs demonstrate their operational workflows through terminal output.

The PostgreSQL script creates the `docker_lab` schema, inserts demonstration records and executes operational reporting queries.

The SQL script drops and recreates its demonstration schema. It should therefore be executed only against a dedicated learning database or another database where replacing that schema is acceptable.

## 17. Practical Technical Boundaries

These implementations are educational models of Docker's architecture and operational responsibilities.

They intentionally distinguish simulation from actual container execution.

| Capability | Implemented simulation | Actual Docker Engine |
|---|---|---|
| Client requests | Yes | Yes |
| Daemon resource model | Yes | Yes |
| Image metadata | Yes | Yes |
| Layer metadata | Yes | Yes |
| Container lifecycle | Yes | Yes |
| Port-conflict checks | Yes | Yes |
| Resource reservation | Yes | Yes |
| Registry workflow | Yes | Yes |
| Actual filesystem layering | No | Yes |
| Linux namespace isolation | No | Yes |
| cgroup enforcement | No | Yes |
| Actual image transfer | No | Yes |
| Real container execution | No | Yes |
| Persistent volume management | Not implemented | Yes |
| Actual network isolation | Not implemented | Yes |
| OCI runtime integration | No | Yes |

The simulations focus on understanding resource ownership, lifecycle transitions, image distribution, validation, operational failures and management responsibilities.

They provide a foundation for understanding how Docker components cooperate during application packaging, distribution and execution.
