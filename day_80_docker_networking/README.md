# Docker Networking: Bridge Networks, Host Networking and Container Communication

## 1. Introduction

Docker networking provides the communication infrastructure connecting containers with other containers, the Docker host, external systems, and services.

Containers have isolated network namespaces by default. Each namespace can maintain its own network interfaces, routing table, IP addresses, and network configuration.

Docker network drivers determine how these namespaces communicate.

This implementation examines four important areas:

- Bridge networking
- Host networking
- Container-to-container communication
- Custom Docker networks

The implementations model network creation, address allocation, DNS resolution, connectivity, port publishing, network isolation, and operational validation.

## 2. Docker Network Architecture

A Docker networking environment consists of several cooperating components.

| Component | Responsibility |
|---|---|
| Docker daemon | Manages containers and network resources |
| Network driver | Determines network connectivity behavior |
| Network namespace | Isolates container network configuration |
| Virtual Ethernet pair | Connects network namespaces |
| Linux bridge | Forwards Ethernet frames between attached interfaces |
| IP address | Identifies a network endpoint |
| Gateway | Provides a route outside the local subnet |
| Port publishing | Exposes container services through host ports |
| DNS service | Resolves container names and network aliases |
| Firewall rules | Control permitted traffic |

### Simplified bridge architecture

    External Client
          |
       Host IP
          |
      Host Port
          |
      Docker Host
          |
       Linux Bridge
          |
      ---------------
      |      |      |
     veth   veth   veth
      |      |      |
    Web     API   Database
    172.20  172.20 172.20

A virtual Ethernet pair provides a connection between the host-side networking environment and a container network namespace.

A Linux bridge forwards traffic between connected interfaces when network and security rules permit it.

Docker manages the configuration required to create these connections.

## 3. Bridge Networking

### 3.1 Definition

Bridge networking connects containers through a virtual Layer 2 network.

Docker supports a default bridge network and user-defined bridge networks.

The bridge driver is commonly used when containers must communicate without directly sharing the host network namespace.

Each attached container receives an IP address from the network's configured subnet.

Example:

| Container | IP address | Service |
|---|---|---|
| web | 172.20.0.2 | HTTP |
| api | 172.20.0.3 | API |
| database | 172.20.0.4 | PostgreSQL |

The gateway is typically configured as the first usable address, such as `172.20.0.1`.

These addresses are illustrative. Actual allocation depends on Docker's network configuration.

### 3.2 Default bridge network

Docker creates a default bridge network named `bridge`.

Containers connected to it can communicate using their IP addresses.

The default bridge does not provide the same automatic container-name DNS service as user-defined bridge networks.

Legacy linking mechanisms should not be confused with modern network-based service discovery.

### 3.3 User-defined bridge networks

A custom bridge network allows administrators to define an independent communication boundary.

Example network design:

| Network | Subnet | Participants |
|---|---|---|
| frontend | 172.20.0.0/24 | Web, API |
| backend | 172.21.0.0/24 | API, Database |

The API container belongs to both networks.

The web container does not belong to the backend network.

Consequently, the API can communicate with the database over the backend network while the web container remains outside that network.

This arrangement reduces unnecessary connectivity.

### 3.4 Bridge network properties

- Containers receive addresses from the network subnet.
- Containers can communicate over shared network connectivity.
- User-defined bridge networks support automatic DNS-based service discovery.
- Containers can be connected to multiple networks.
- Networks provide logical isolation.
- Published ports can expose selected services externally.

## 4. Host Networking

Host networking allows a container to share the host's network namespace.

Unlike bridge networking, the container does not receive an independent bridge-network IP address.

The container uses the host's network interfaces and ports.

### 4.1 Architecture

    External Client
          |
       Host IP
          |
      Host Network Namespace
          |
      ---------------------
      |                   |
    Host Process      Container Process
                       Host Networking

### 4.2 Characteristics

| Property | Host networking |
|---|---|
| Separate container IP | No |
| Host network namespace | Shared |
| Independent bridge gateway | No |
| Bridge DNS | Not applicable |
| Port publishing | Generally unnecessary |
| Port collision risk | High |
| Network isolation | Reduced |

### 4.3 Port collision

Suppose an application already listens on host port `8080`.

A host-networked container attempting to bind the same port can encounter an address-in-use error.

Unlike bridge networking with published ports, host networking does not provide a separate host-to-container port mapping boundary.

Host networking is useful when an application requires direct access to host networking behavior, but it should be selected deliberately.

## 5. Container-to-Container Communication

Containers can communicate using network addresses and service ports.

For example:

    Web Container
         |
         | HTTP request
         |
    API Container
         |
         | PostgreSQL connection
         |
    Database Container

The web application connects to the API using an internal service name and port.

The API connects to PostgreSQL using its database service name.

Example application configuration:

| Setting | Value |
|---|---|
| API hostname | api-service |
| API port | 8000 |
| Database hostname | db |
| Database port | 5432 |

A custom bridge network allows Docker's embedded DNS service to resolve network aliases.

Applications should use service names rather than hard-coded container IP addresses.

Container IP addresses can change when containers are recreated or reattached.

### 5.1 Network membership

A container can belong to multiple networks.

Example:

| Container | Frontend | Backend |
|---|---|---|
| Web | Yes | No |
| API | Yes | Yes |
| Database | No | Yes |

This creates an application topology with separate frontend and backend communication domains.

### 5.2 Communication requirements

Successful communication generally requires:

1. Both containers to be running.
2. Appropriate network connectivity.
3. A valid destination address.
4. A service listening on the destination port.
5. Firewall rules permitting traffic.
6. Correct application protocol configuration.

DNS resolution alone does not guarantee that a service is reachable.

A resolved IP address can still lead to a failed connection if the destination application is unavailable or traffic is blocked.

## 6. Port Publishing and Port Mapping

Port publishing makes a container service accessible through a Docker host port.

Consider:

    Host Port 8080
          |
          v
    Container Port 80
          |
          v
       Nginx

The mapping is:

| Host | Container |
|---|---|
| 8080 | 80 |

A client can connect to the Docker host on port `8080`, and Docker forwards the traffic to the container service on port `80`.

### 6.1 Port mapping syntax

The general Docker command format is:

`docker run -p HOST_PORT:CONTAINER_PORT IMAGE`

A more explicit example is:

`docker run -d --name web -p 8080:80 nginx:1.27`

For TCP:

`docker run -d -p 8080:80/tcp nginx:1.27`

For a particular host interface:

`docker run -d -p 127.0.0.1:8080:80 nginx:1.27`

Binding to `127.0.0.1` restricts host-port exposure to the host's loopback interface.

Publishing a port does not mean that the application is automatically reachable through every network interface.

The host firewall, routing configuration, and application binding address also matter.

### 6.2 Exposed versus published ports

These concepts are different.

| EXPOSE | Published port |
|---|---|
| Documents an application port | Configures host-port access |
| Does not independently create external access | Creates a host-to-container forwarding rule |
| Can be used as image metadata | Requires an actual network configuration |

An application can listen on a port without publishing that port to the host.

Containers on the same bridge network may still communicate with the application through its internal container port.

## 7. Custom Docker Networks

Custom networks provide controlled communication boundaries.

A custom network has several important properties:

- Network name
- Network driver
- Subnet
- Gateway
- Attached containers
- DNS aliases
- Network configuration

### 7.1 Subnet planning

Example:

| Network | CIDR | Gateway |
|---|---|---|
| frontend | 172.20.0.0/24 | 172.20.0.1 |
| backend | 172.21.0.0/24 | 172.21.0.1 |
| monitoring | 172.22.0.0/24 | 172.22.0.1 |

A subnet must not overlap another network using the same routing domain.

Overlapping networks can create ambiguous routing and address allocation problems.

Subnet planning should account for:

- Existing host routes
- VPN networks
- Corporate LAN ranges
- Cloud VPC ranges
- Other Docker networks
- Kubernetes pod and service CIDRs where applicable

### 7.2 Network lifecycle

The typical lifecycle is:

    Create Network
          |
          v
    Create Container
          |
          v
    Connect Container
          |
          v
    Allocate IP Address
          |
          v
    Register DNS Alias
          |
          v
    Communicate
          |
          v
    Disconnect Container
          |
          v
    Remove Network

A network should not be removed while active containers still depend on it.

## 8. Docker Networking Commands

| Operation | Command |
|---|---|
| List networks | `docker network ls` |
| Inspect network | `docker network inspect frontend` |
| Create bridge | `docker network create frontend` |
| Create custom subnet | `docker network create --driver bridge --subnet 172.20.0.0/24 frontend` |
| Connect container | `docker network connect frontend web` |
| Disconnect container | `docker network disconnect frontend web` |
| Remove network | `docker network rm frontend` |
| Remove unused networks | `docker network prune` |
| Inspect container | `docker inspect web` |

### 8.1 Create a custom bridge

`docker network create --driver bridge --subnet 172.20.0.0/24 frontend`

### 8.2 Create containers

`docker run -d --name web --network frontend nginx:1.27`

`docker run -d --name api --network frontend python:3.13`

### 8.3 Inspect connectivity

`docker network inspect frontend`

`docker inspect web`

`docker exec web getent hosts api`

The last command checks whether the container can resolve the API service name. The image must contain the required diagnostic utility.

## 9. Python Implementation

File: `docker_networking.py`

The Python implementation provides a network-management simulator.

### Main classes

| Class | Responsibility |
|---|---|
| `DockerHost` | Manages networks, containers and port bindings |
| `DockerNetwork` | Stores network configuration and attachments |
| `Container` | Represents a running or stopped container |
| `PortBinding` | Validates host-to-container port mappings |
| `NetworkDriver` | Identifies bridge and host drivers |

### Important operations

- `create_network()` creates a bridge or host network.
- `create_container()` registers a container.
- `connect()` attaches a container to a network.
- `_allocate_ip()` assigns a unique address.
- `resolve()` performs simulated DNS lookup.
- `can_communicate()` evaluates network membership and destination ports.
- `publish_port()` registers host-port forwarding.
- `disconnect()` removes an attachment and its aliases.
- `stop_container()` removes active published bindings.
- `inspect_network()` displays network configuration.

### Address allocation

The allocator starts after the network gateway and checks available addresses.

It excludes the gateway and reserves the network and broadcast addresses.

For a `/24` network, this implementation supports the usable host range between the gateway and broadcast address.

### Important distinction

The simulator models Docker network behavior. It does not create real Linux bridges, network namespaces, firewall rules, or packet forwarding.

Its connectivity checks represent logical eligibility rather than actual socket-level communication.

## 10. JavaScript Implementation

File: `docker_networking.js`

The JavaScript implementation uses an event-driven design.

### Main engineering mechanisms

| Mechanism | Purpose |
|---|---|
| `Map` | Stores containers and networks |
| `Set` | Tracks network membership |
| `EventEmitter` | Supports event-driven network operations |
| `crypto.randomUUID()` | Generates unique container identifiers |
| `Object.freeze()` | Protects selected configuration objects |
| Promises | Support asynchronous operation orchestration |
| Exceptions | Represent invalid network operations |

The implementation uses JavaScript's event-oriented model to separate network state changes from operational notifications.

The `WorkerNode`-style separation of network objects and container objects allows individual network operations to be validated independently.

The simulation uses the Node.js standard library and requires no third-party packages.

## 11. C++17 Implementation

File: `docker_networking.cpp`

The C++ implementation uses explicit domain structures and a network-management engine.

### Main structures

| Structure or class | Responsibility |
|---|---|
| `IPv4` | Parses and represents IPv4 addresses |
| `Subnet` | Performs CIDR and overlap validation |
| `PortBinding` | Represents a published port |
| `Container` | Stores container state |
| `Network` | Stores driver and attachment information |
| `DockerEngine` | Manages network operations |

### Design decisions

The implementation represents IPv4 addresses as unsigned 32-bit integers.

CIDR masks are calculated using bitwise operations.

Subnet overlap is checked mathematically rather than by enumerating every address.

The engine uses ordered STL maps for deterministic inventory reporting.

The use of `std::optional` distinguishes bridge configuration from host networking configuration.

### Complexity

Let:

- N = number of containers
- M = number of networks
- A = number of active network attachments
- D = number of DNS aliases

| Operation | Approximate complexity |
|---|---|
| Container lookup | O(log N) |
| Network lookup | O(log M) |
| Subnet overlap against all networks | O(M) |
| DNS alias lookup | O(log D) |
| Network attachment lookup | O(log N) |
| Network inventory | O(A) |

The implementation prioritizes clear state management and deterministic results over high-scale packet-processing performance.

## 12. Java 17 Implementation

File: `DockerNetworkingEnterprise.java`

The Java implementation uses an enterprise-oriented domain model.

### Main domain types

- `DockerNetwork`
- `Container`
- `ResourceAddress`
- `PortMapping`
- `NetworkPolicy`
- `NetworkService`
- `AuditEvent`

Records are used for immutable configuration and event data.

The network service controls the lifecycle of containers and networks.

### Policy evaluation

The `NetworkPolicy` class checks:

- Permitted source network membership
- Destination port authorization
- Destination port availability

A policy is evaluated separately from the underlying network membership check.

This distinction is important because connectivity and authorization are not equivalent.

A container can share a network with another container while an application-level or firewall policy still denies its traffic.

### Audit events

The service records operational events such as:

- Network creation
- Container creation
- Network attachment
- Network detachment
- Port publishing
- Container shutdown

This provides a basic operational history for diagnosing configuration changes.

## 13. PostgreSQL Implementation

File: `docker_networking.sql`

The database implementation models Docker networking as a relational inventory and operational governance system.

### Entity relationships

    Docker Hosts
         |
         +------ Docker Networks
         |
         +------ Containers
                    |
                    v
              Network Attachments
                    |
                    v
              DNS Aliases

    Containers
         |
         +------ Port Mappings
         |
         +------ Communication Attempts
         |
         +------ Network Policies

### Table responsibilities

| Table | Purpose |
|---|---|
| `docker_hosts` | Docker host inventory |
| `docker_networks` | Network drivers, subnets and gateways |
| `containers` | Container metadata and lifecycle |
| `network_attachments` | Container-to-network relationships |
| `dns_aliases` | Network-specific service names |
| `port_mappings` | Published host ports |
| `network_policies` | Communication authorization rules |
| `communication_attempts` | Connectivity evaluation history |
| `network_events` | Operational audit records |

### Data integrity

The schema uses:

- Primary keys
- Foreign keys
- Unique constraints
- Check constraints
- Partial unique indexes
- Triggers
- Transactional functions

The network configuration trigger validates host and subnet settings.

The subnet-overlap trigger prevents overlapping bridge networks on the same Docker host.

The IP-allocation trigger checks network membership and allocates an available address.

Partial unique indexes protect active IP allocations and published host ports.

### Transactional operations

The `attach_container()` function creates a network attachment and registers DNS aliases in the same transaction.

If an alias violates a uniqueness constraint, the transaction fails and the attachment is rolled back.

The `detach_container()` function retains historical attachment information by setting `disconnected_at`.

This allows operational reporting without deleting historical records.

### Communication evaluation

The `evaluate_communication()` function considers:

1. Whether the network exists.
2. Whether both containers exist.
3. Whether both containers are running.
4. Whether both containers belong to the same host.
5. Whether both containers have an active attachment to the selected network.
6. Whether the destination port has an active published mapping.
7. Whether an explicit network policy permits or denies traffic.

This is a simplified governance model, not a complete representation of Docker's packet-forwarding engine.

## 14. Important Technical Distinctions

### 14.1 Bridge versus host networking

| Feature | Bridge | Host |
|---|---|---|
| Network namespace | Separate | Shared with host |
| Container IP | Independent | Host network addresses |
| Port mapping | Supported | Generally unnecessary |
| Network isolation | Greater | Reduced |
| Gateway | Bridge gateway | Host routing |
| DNS aliases | Supported on user-defined bridge | Not bridge DNS |
| Port conflicts | Managed through published ports | Shared host port space |

### 14.2 Container IP versus published host port

A container IP identifies its internal network endpoint.

A published host port provides an entry point through the Docker host.

These are different network addressing concepts.

For example:

- Container IP: `172.20.0.3`
- Container service port: `8000`
- Host IP: `192.168.1.10`
- Published host port: `8080`

The host mapping can forward traffic from host port `8080` to container port `8000`.

### 14.3 Network membership versus DNS resolution

Network membership determines whether containers share a network.

DNS resolution identifies an endpoint by name.

Successful DNS resolution does not guarantee successful application communication.

### 14.4 Network isolation versus application authorization

A network boundary limits which containers share a communication domain.

Application authorization determines whether a particular request is permitted.

Both mechanisms may be required to protect sensitive services.

## 15. Security Considerations

Docker networking introduces security responsibilities at several levels.

### Network segmentation

Separate public-facing services from internal databases.

A web container should not automatically receive access to every backend service.

### Restrict published ports

Avoid publishing administrative and database ports to all host interfaces unless required.

Prefer loopback bindings for host-local administration.

### DNS and service identity

Container names and aliases provide service discovery, not cryptographic identity.

Sensitive service communication should use appropriate authentication and encryption.

### Host networking

Host networking reduces network isolation and can increase exposure to host-level services.

It should not be selected merely to avoid configuring port mappings.

### Subnet planning

Prevent overlapping address ranges and unintended routes.

### Secrets

Database passwords, API keys, and certificates should not be embedded in container images or committed to source control.

### Firewall controls

Docker-managed firewall rules can interact with host firewall configurations.

A production deployment should validate both Docker network configuration and host-level firewall behavior.

### Monitoring

Monitor:

- Published ports
- Network attachments
- Container restarts
- DNS failures
- Connection failures
- Unexpected network changes
- Unused networks

## 16. Edge Cases and Failure Handling

| Failure | Expected behavior |
|---|---|
| Duplicate network name | Reject creation |
| Duplicate container name | Reject creation |
| Invalid IPv4 address | Reject configuration |
| Invalid CIDR | Reject configuration |
| Overlapping bridge subnet | Reject network creation |
| Exhausted address pool | Reject attachment |
| Duplicate DNS alias | Reject alias registration |
| Unknown DNS name | Return resolution failure |
| Container not running | Reject or deny communication |
| Destination port unavailable | Deny simulated communication |
| Duplicate host port | Reject publication |
| Host network with bridge subnet | Reject configuration |
| Invalid network membership | Reject communication |
| Disconnect from host network | Reject independent detachment |

## 17. Performance Considerations

Network configuration operations are control-plane operations and should be separated from packet forwarding.

The implementations use maps and indexed relational tables to support efficient lookups.

For larger environments:

- Avoid repeated full inventory scans.
- Index network and container identifiers.
- Index DNS aliases by network.
- Use partial indexes for active attachments.
- Avoid unnecessarily large broadcast domains.
- Limit published ports.
- Track historical events separately from active state.
- Use connection pooling for application-to-database traffic.

Actual network throughput depends on the host kernel, network driver, hardware, packet size, firewall rules, and workload.

## 18. Testing and Execution

### Python

File: `docker_networking.py`

Run:

`python docker_networking.py`

The script executes assertions for custom networks, DNS, network isolation, multiple network memberships, port publishing, host networking, and subnet conflicts.

### JavaScript

File: `docker_networking.js`

Run:

`node docker_networking.js`

The event-driven simulation should be executed using Node.js 18 or later.

### C++17

File: `docker_networking.cpp`

Compile:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic docker_networking.cpp -o docker_networking`

Run:

`./docker_networking`

### Java 17

File: `DockerNetworkingEnterprise.java`

Compile:

`javac --release 17 DockerNetworkingEnterprise.java`

Run:

`java DockerNetworkingEnterprise`

### PostgreSQL

File: `docker_networking.sql`

Execute:

`psql -U postgres -d postgres -v ON_ERROR_STOP=1 -f docker_networking.sql`

The script creates a dedicated schema, relational objects, triggers, functions, sample records, evaluation queries, and reporting views.

It should be executed using a PostgreSQL account with permission to create schemas and the `pgcrypto` extension.

## 19. Implementation Limitations

These programs are educational network-management models rather than replacements for Docker Engine.

They do not create real network namespaces, virtual Ethernet interfaces, Linux bridges, NAT rules, DNS servers, or packet-filtering configurations.

The SQL model represents inventory and simplified connectivity governance. In particular, its published-port requirement and explicit policy evaluation are simplified abstractions and do not reproduce every Docker forwarding rule.

The Python and C++ communication models validate logical membership and service-port declarations rather than performing actual socket connections.

The Java policy model demonstrates application-level authorization and should not be interpreted as a complete Docker firewall implementation.

Production networking also requires consideration of IPv6, routing, DNS lifecycle, firewall behavior, network driver capabilities, and host-level security configuration.

## 20. Key Terminology

| Term | Definition |
|---|---|
| Container | Isolated application execution environment |
| Network namespace | Linux isolation mechanism for network resources |
| Bridge | Virtual Layer 2 network connecting interfaces |
| Host networking | Sharing the host network namespace |
| veth pair | Virtual Ethernet interface pair |
| CIDR | Network address and prefix representation |
| Subnet | Logical IP address range |
| Gateway | Routing endpoint for traffic outside a subnet |
| NAT | Network Address Translation |
| Port publishing | Exposing a container service through a host port |
| DNS alias | Network-specific name resolving to a container |
| Network attachment | Association between a container and a network |
| Network segmentation | Dividing infrastructure into communication domains |
| Port collision | Multiple services attempting to bind the same address and port |
| Network isolation | Restricting communication between network domains |

## 21. Relationship to Container Orchestration

Docker networking provides foundational concepts used by larger container platforms.

Container orchestration systems manage networking at a broader infrastructure level.

For example, Kubernetes introduces:

- Pod networking
- Cluster networking
- Service discovery
- ClusterIP services
- NodePort services
- LoadBalancer services
- Network policies
- Container Network Interface (CNI) plugins

Docker bridge networking and Kubernetes pod networking are not interchangeable.

Docker bridge networks generally connect containers through a host-managed bridge.

Kubernetes commonly expects each pod to receive its own cluster-routable IP address through the cluster's networking implementation.

Understanding Docker networking therefore provides a foundation for studying container communication, service discovery, network isolation, and distributed application infrastructure.
