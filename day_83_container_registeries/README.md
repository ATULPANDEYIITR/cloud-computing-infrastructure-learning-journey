# Container Registries: Image Repositories, Tagging, Versioning, Access Control and Distribution

## 1. Container Registry Architecture

A container registry is a service that stores, organizes, manages, and distributes container images. It provides a centralized location for publishing application images and retrieving them during development, testing, and deployment.

A registry is part of the container delivery infrastructure. It connects image-building processes with deployment environments.

A typical architecture is:

    Source Code
        |
        v
    Container Build
        |
        v
    Image Configuration and Layers
        |
        v
    Image Manifest
        |
        v
    Container Registry
        |
        +------ Repository
        |          |
        |          +------ Image Tags
        |          +------ Image Digests
        |          +------ Image Versions
        |          +------ Image Layers
        |
        v
    Image Distribution
        |
        v
    Container Runtime
        |
        v
    Application Deployment

The registry manages image storage and distribution. It does not execute the application contained in an image.

### 1.1 Main components

| Component | Responsibility |
|---|---|
| Registry | Provides image storage and distribution services |
| Repository | Organizes images belonging to an application or component |
| Manifest | Describes an image and identifies its configuration and layers |
| Layer | Represents a filesystem change or image component |
| Tag | Human-readable reference to an image |
| Digest | Content-derived identifier for an image manifest |
| Registry credentials | Establish the identity of a registry client |
| Access policy | Determines which operations a user can perform |
| Distribution endpoint | Provides image manifests and layer content to clients |
| Audit log | Records registry operations |
| Lifecycle policy | Controls image retention, quarantine, and deletion |

## 2. Container Images and Image Repositories

### 2.1 Container images

A container image is an immutable package containing the filesystem and configuration required to create a container.

An image can contain:

- Application binaries.
- Runtime dependencies.
- System libraries.
- Application configuration.
- Filesystem layers.
- Execution metadata.

A container image is different from a running container.

| Container image | Running container |
|---|---|
| Stored artifact | Executing instance |
| Immutable image content | Runtime state can change |
| Distributed through registries | Created by a container runtime |
| Identified through tags and digests | Identified through runtime-specific identifiers |
| Used to create containers | Executes an application |

### 2.2 Image repositories

A repository is a logical collection of related images.

For example:

    production-registry/
        finance/
            payment-api/
            transaction-service/
            reporting-service/
        platform/
            authentication/
            notification/

The repository `finance/payment-api` can contain multiple versions of the payment application.

Repository naming conventions should support:

- Organizational ownership.
- Application identification.
- Environment separation where required.
- Consistent automation.
- Access-control boundaries.

A repository is not the same as an individual image version. It is the namespace in which image references are managed.

### 2.3 Registry types

| Registry type | Description | Typical use |
|---|---|---|
| Public registry | Allows public image retrieval | Open-source base images |
| Private registry | Restricts access to authorized identities | Enterprise applications |
| Self-hosted registry | Operated within an organization's infrastructure | Internal infrastructure |
| Managed registry | Operated as a cloud service | Distributed development and deployment |
| Proxy or cache registry | Caches upstream images | Reducing external network dependencies |

A public repository does not necessarily permit unrestricted image publishing. Publishing permissions remain a separate policy decision.

## 3. Image Manifests, Layers and Digests

### 3.1 Image manifests

An image manifest describes the components of an image.

An OCI image manifest generally identifies:

- Schema version.
- Manifest media type.
- Configuration descriptor.
- Layer descriptors.
- Layer media types.
- Content digests.
- Content sizes.

The manifest acts as the structural description of an image.

The image configuration describes runtime and filesystem metadata, while the layers contain filesystem content.

### 3.2 Image layers

Container images are commonly constructed from multiple filesystem layers.

For example:

    Layer 1: Base operating system
    Layer 2: Runtime dependencies
    Layer 3: Application libraries
    Layer 4: Application binaries
    Layer 5: Application configuration

Layer reuse reduces repeated data transfer and storage consumption.

When two images share identical layers, a registry or compatible client can reuse existing content instead of transferring duplicate content.

Layer reuse depends on matching content and compatible distribution behavior.

### 3.3 Content-addressable storage

Content-addressable storage identifies objects through their content digest.

A SHA-256 digest is represented as:

`sha256:<64 hexadecimal characters>`

A manifest digest identifies a particular manifest representation. A changed manifest produces a different digest.

This gives images a stable identity independent of their tags.

Important distinctions:

- A tag is a reference that can be reassigned.
- A digest identifies specific content.
- A manifest references configuration and layer descriptors.
- A layer digest identifies an individual content object.

Digest verification helps detect content corruption and unexpected changes.

A digest alone does not establish that an image is safe or trustworthy. Signature verification, provenance validation, vulnerability assessment, and access controls address different security requirements.

## 4. Image Tagging and Versioning

### 4.1 Image tags

A tag is a human-readable reference associated with an image manifest.

Example:

    finance/payment-api:1.0.0
    finance/payment-api:2.0.0
    finance/payment-api:latest
    finance/payment-api:production

The repository identifies the application collection. The tag identifies a particular image reference within that repository.

Tags are generally mutable unless repository policies prevent reassignment.

### 4.2 Mutable tags

A mutable tag can point to different image digests over time.

Example:

    latest -> sha256:IMAGE_A

After publishing a new version:

    latest -> sha256:IMAGE_B

The original image remains identifiable through its previous digest as long as the artifact has not been deleted.

Mutable tags are useful for development channels and automated build workflows.

Their disadvantage is that a deployment using `latest` may retrieve different image content at different times.

### 4.3 Immutable tags

An immutable tag cannot be reassigned to a different image.

Example:

    1.0.0 -> sha256:IMAGE_A

An attempt to change it to another digest is rejected.

Immutable tags are useful for:

- Production releases.
- Reproducible deployments.
- Release auditing.
- Deployment rollback.
- Change traceability.

A registry can enforce immutable tags through repository policy and database constraints or triggers.

### 4.4 Semantic versioning

Semantic versioning uses:

`MAJOR.MINOR.PATCH`

| Component | Meaning | Example |
|---|---|---|
| Major | Incompatible changes | 2.0.0 |
| Minor | Backward-compatible functionality | 1.3.0 |
| Patch | Backward-compatible corrections | 1.2.4 |

A release sequence might be:

    1.0.0
    1.0.1
    1.1.0
    1.2.0
    2.0.0

Semantic versioning provides a human-readable release convention. It does not automatically guarantee backward compatibility or image security.

### 4.5 Tags versus digests

| Property | Tag | Digest |
|---|---|---|
| Human readability | High | Low |
| Content identity | Indirect | Direct |
| Mutable | Usually | No, for a fixed content representation |
| Useful for development | Yes | Yes |
| Suitable for exact deployment identification | Less reliable | Preferred |
| Supports rollback | Through retained references | Through retained artifacts |

For production deployments, digest-pinned references reduce ambiguity.

Example:

`registry.example.internal/finance/payment-api@sha256:<digest>`

## 5. Private Registries and Access Control

Private registries restrict image access to authenticated identities with appropriate permissions.

Authentication and authorization are separate operations.

### 5.1 Authentication

Authentication establishes the identity of the client.

Common authentication mechanisms include:

- Username and password.
- Personal access tokens.
- Robot accounts.
- Cloud identity credentials.
- Short-lived access tokens.
- Workload identity.

Credentials should not be embedded in container images, source code, public repositories, or application logs.

A production registry should use secure transport and controlled credential rotation.

### 5.2 Authorization

Authorization determines whether an authenticated identity can perform a particular operation.

The implementations use three roles.

| Role | Pull | Push | Delete |
|---|---|---|---|
| Reader | Yes | No | No |
| Writer | Yes | Yes | No |
| Admin | Yes | Yes | Yes |

The access model is repository-specific.

A deployment service generally needs pull access without receiving publishing or deletion privileges.

An image-building service needs push access but should not automatically receive administrative rights.

An administrator can manage repository permissions and lifecycle operations.

### 5.3 Least privilege

Least privilege means assigning only the permissions necessary for an identity to perform its responsibilities.

A practical enterprise arrangement is:

    Registry Administrator
        |
        +---- Repository configuration
        +---- Permission management
        +---- Image lifecycle administration

    Build Service
        |
        +---- Image publication
        +---- Tag assignment

    Deployment Service
        |
        +---- Image retrieval
        +---- Digest verification

Separating these responsibilities reduces the impact of compromised credentials.

### 5.4 Repository-level security

A private registry should implement:

- Authentication before protected operations.
- Repository-specific authorization.
- TLS-protected communication.
- Credential rotation.
- Audit logging.
- Administrative access restrictions.
- Image signature verification.
- Vulnerability assessment.
- Controlled image deletion.
- Network and service access restrictions.

The demonstration implementations use credential hashes for authentication examples. They do not implement a production identity provider, TLS server, or secure token issuance system.

## 6. Image Distribution and Retrieval

Image distribution is the process of transferring image manifests and content layers from a registry to a client.

A typical retrieval workflow is:

    Deployment Request
          |
          v
    Registry Authentication
          |
          v
    Repository Authorization
          |
          v
    Resolve Tag or Digest
          |
          v
    Retrieve Manifest
          |
          v
    Identify Required Layers
          |
          v
    Download Missing Layers
          |
          v
    Verify Content Digests
          |
          v
    Prepare Local Image

### 6.1 Layer distribution

A client does not necessarily need to download every layer for every image.

If the required layer is already available locally, it can be reused.

This reduces:

- Network traffic.
- Deployment time.
- Registry bandwidth consumption.
- Repeated content transfer.

### 6.2 Distribution metrics

Useful operational measurements include:

| Metric | Purpose |
|---|---|
| Image pull count | Measures image retrieval frequency |
| Bytes transferred | Measures distribution volume |
| Pull success rate | Measures retrieval reliability |
| Pull latency | Measures distribution performance |
| Manifest count | Measures stored image artifacts |
| Layer count | Measures image composition |
| Storage consumption | Measures registry capacity usage |
| Failed authentication | Identifies access problems |
| Failed authorization | Identifies permission problems |

A production registry should also monitor cache hit rates, concurrent transfers, storage growth, network errors, and regional distribution performance.

### 6.3 Image distribution strategies

Common approaches include:

- Direct retrieval from a central registry.
- Regional registry replicas.
- Pull-through caching.
- Content-addressed layer reuse.
- CDN-assisted distribution.
- Controlled image mirroring.

Regional distribution can reduce latency and external network dependencies, although it introduces replication consistency and operational management requirements.

## 7. Registry Lifecycle Management

Image lifecycle management controls how artifacts move through operational states.

The implementations model:

| State | Meaning |
|---|---|
| Available | Image can be retrieved |
| Quarantined | Image is restricted pending investigation |
| Deleted | Image is no longer available |

A typical lifecycle is:

    Build
      |
      v
    Publish
      |
      v
    Verify
      |
      v
    Available
      |
      +------> Quarantined
      |             |
      |             +----> Restored
      |             |
      |             +----> Deleted
      |
      +------> Deprecated
                    |
                    v
                 Deleted

Deprecation is a release-management concept and does not necessarily mean that the underlying image content has been removed.

### 7.1 Garbage collection

Garbage collection removes artifacts that are no longer referenced by repository tags or other retained references.

For example:

    Tag 1.0.0 -> Image A
    Tag 2.0.0 -> Image B
    Tag latest -> Image B

If the `1.0.0` tag is deleted, Image A may become eligible for garbage collection.

Image B remains referenced by two tags.

Garbage collection must consider:

- Manifest references.
- Tag references.
- Shared layers.
- Quarantined images.
- Replication state.
- Active distribution operations.
- Retention requirements.

Deleting an image tag and deleting the underlying artifact are different operations.

A production registry should use reference-aware cleanup and safe storage reclamation. It should not delete shared layer data while retained manifests still reference those layers.

## 8. Python Implementation: Repository Workflow Simulation

File: `container_registry.py`

The Python implementation models the registry through domain-oriented classes.

### 8.1 Domain model

| Class | Responsibility |
|---|---|
| `ContainerRegistry` | Coordinates repository and user operations |
| `Repository` | Stores tags and image artifacts |
| `ImageManifest` | Represents image metadata and content identity |
| `ImageArtifact` | Stores image state and distribution metrics |
| `RegistryUser` | Represents an authenticated registry identity |
| `AuditEvent` | Records registry activity |

### 8.2 Important mechanisms

The `ImageManifest` dataclass produces a canonical representation before computing a SHA-256 digest.

This separates the identity of an image manifest from the tag used to reference it.

The `push()` method:

1. Authenticates the user.
2. Resolves the repository.
3. Checks publishing permissions.
4. Validates the tag.
5. Validates manifest metadata.
6. Computes the image digest.
7. Enforces immutable-tag policy.
8. Stores the artifact by digest.
9. Updates the tag reference.
10. Records an audit event.

The `pull()` method resolves either a tag or digest and verifies that the artifact remains available.

The `garbage_collect()` method identifies artifacts that are no longer referenced by repository tags.

### 8.3 Error handling

Custom exceptions distinguish:

- Authentication failures.
- Authorization failures.
- Missing repositories.
- Invalid references.
- Duplicate repository creation.
- Immutable-tag conflicts.

The script also uses assertions to verify that digest-based retrieval remains stable after tag operations.

### 8.4 Performance characteristics

Repository and user lookups use dictionaries, providing expected constant-time lookup.

Tag resolution and artifact retrieval are also expected constant-time operations.

Garbage collection requires scanning the repository's artifact and tag references.

Its approximate time complexity is:

`O(A + T)`

Where:

- `A` is the number of stored artifacts.
- `T` is the number of tags.

The implementation stores image metadata in memory and does not transfer actual filesystem layers.

## 9. JavaScript Implementation: Asynchronous Registry Policy Engine

File: `container_registry.js`

The JavaScript implementation focuses on event-driven operations, asynchronous publishing, and policy evaluation.

### 9.1 Event-driven architecture

The registry extends Node.js `EventEmitter`.

It emits events such as:

- `image:pushed`
- `audit`

These events allow operational components to react to registry activity.

For example, a successful image publication can trigger a deployment notification or an external verification workflow.

### 9.2 Policy objects

`RegistryPolicy` centralizes:

- Repository visibility.
- Immutable-tag configuration.
- Allowed CPU architectures.
- Image verification requirements.

The policy engine evaluates an operation before changing repository state.

This separates policy decisions from storage management.

### 9.3 Asynchronous publishing

The `push()` method returns a Promise.

A serialized write queue prevents concurrent publishing operations from producing unpredictable tag reassignment order within the demonstration registry.

This is especially important for mutable references such as `latest`.

The queue provides process-local coordination. A distributed registry requires database transactions, distributed locking, or another cross-instance concurrency-control mechanism.

### 9.4 Manifest normalization

The `canonicalManifest()` function validates the manifest and creates a normalized representation.

The normalized content is used to compute a deterministic digest.

The implementation also validates image architecture before accepting a publication.

### 9.5 Event and audit separation

Events communicate that an operation occurred.

Audit records preserve operational evidence.

These have different responsibilities:

| Events | Audit records |
|---|---|
| Support event-driven workflows | Support traceability |
| Notify subscribers | Record actors and operations |
| Can trigger downstream processing | Support investigations |
| Usually transient notifications | Require durable storage in production |

The implementation keeps both mechanisms separate.

## 10. C++17 Implementation: Registry Governance Engine

File: `container_registry.cpp`

The C++ implementation emphasizes explicit domain modeling, repository governance, STL containers, and controlled state transitions.

### 10.1 Core structures

| Structure or class | Responsibility |
|---|---|
| `Manifest` | Validates image configuration and layers |
| `ImageArtifact` | Stores manifest, status, and pull count |
| `Repository` | Manages tags and artifacts |
| `User` | Represents a registry identity |
| `Registry` | Coordinates access, publication, retrieval, and cleanup |
| `AuditEvent` | Captures operation outcomes |

### 10.2 STL data structures

The implementation uses:

- `map` for users, repositories, tags, and artifacts.
- `set` for protected tags and referenced digests.
- `vector` for audit records and image layers.
- `all_of` for tag validation.
- `find` and `count` for lookups.
- `erase` for artifact cleanup.

Ordered maps provide predictable logarithmic lookup and maintain ordered keys.

### 10.3 Governance behavior

The registry distinguishes the permissions required for publishing, retrieving, and deleting images.

The `authorize()` method enforces repository-level access.

The `protectTag()` method creates a protected release reference.

A protected tag cannot be reassigned or deleted through the implemented administrative workflow.

### 10.4 Content identity

The C++ program uses a deterministic demonstration identifier based on `std::hash`.

This is intentionally not presented as cryptographic content verification.

Production implementations must use SHA-256 or an equivalent approved cryptographic digest algorithm.

The distinction matters because `std::hash` is not a cryptographic integrity mechanism and is not guaranteed to produce identical values across different implementations or executions.

### 10.5 Complexity

For the ordered-map implementation:

| Operation | Approximate complexity |
|---|---|
| Repository lookup | `O(log R)` |
| User lookup | `O(log U)` |
| Tag lookup | `O(log T)` |
| Artifact lookup | `O(log A)` |
| Audit insertion | Amortized `O(1)` |
| Garbage collection | `O(A log T)` in the current reference-checking approach |

Where:

- `R` represents repositories.
- `U` represents users.
- `T` represents tags.
- `A` represents image artifacts.

## 11. Java 17 Implementation: Enterprise Registry Governance

File: `ContainerRegistryEnterprise.java`

The Java implementation emphasizes enterprise domain types, immutable data structures, policy objects, validation, and explicit lifecycle transitions.

### 11.1 Records and immutable structures

The implementation uses Java 17 records for:

- `ImageLayer`
- `ImageManifest`
- `AuditEvent`
- `RegistryPolicy`

Records provide concise data modeling and immutable component references.

Image layer collections are copied using `List.copyOf()` to prevent external modification of the manifest's layer collection.

### 11.2 Service architecture

The principal service classes are:

| Class | Responsibility |
|---|---|
| `RegistryService` | Registry operations and coordination |
| `Repository` | Repository-level state |
| `RegistryUser` | User identity and permissions |
| `ImageArtifact` | Image lifecycle and distribution |
| `RegistryPolicy` | Repository governance |
| `ImageManifest` | Validated image description |

### 11.3 Explicit state transitions

The artifact lifecycle uses an enum.

An image can be:

- Available.
- Quarantined.
- Deleted.

The transition methods prevent invalid operations.

For example, an available image can be quarantined. A quarantined image can be restored. A deleted image cannot be pulled.

These rules are enforced by the artifact domain object rather than being scattered throughout service methods.

### 11.4 Enterprise policy evaluation

The policy object determines whether an identity can perform an operation.

It also checks:

- Repository visibility.
- Required image verification.
- Allowed architectures.
- Immutable tag behavior.
- Protected tag restrictions.

The service and policy layers have separate responsibilities.

The service coordinates state changes, while the policy object determines whether an operation is permitted.

### 11.5 Cryptographic identity

Java's `MessageDigest` implements SHA-256.

The resulting digest identifies a canonical manifest representation.

`MessageDigest.isEqual()` is used when comparing credential-derived hashes.

A production implementation should use a dedicated credential-management system, appropriate password or token hashing, short-lived credentials, and managed secret rotation.

## 12. PostgreSQL Implementation: Relational Registry Management

File: `container_registry.sql`

The PostgreSQL implementation models registry operations through relational tables, constraints, triggers, functions, procedures, and views.

### 12.1 Database relationship model

    registries
        |
        v
    repositories
        |
        +------ repository_permissions
        |               |
        |               v
        |          registry_users
        |
        +------ image_artifacts
        |               |
        |               +------ image_layers
        |               |
        |               +------ image_distribution_events
        |
        +------ image_tags
        |
        +------ registry_audit

### 12.2 Relational entities

| Table | Purpose |
|---|---|
| `registries` | Registry configuration |
| `registry_users` | Registry identities |
| `repositories` | Repository metadata and policy |
| `repository_permissions` | User-to-repository permissions |
| `image_artifacts` | Stored image manifests |
| `image_layers` | Layer descriptors and sizes |
| `image_tags` | Version and tag references |
| `registry_audit` | Operational audit records |
| `image_distribution_events` | Image retrieval and transfer metrics |

The repository and artifact relationship is one-to-many.

An artifact can have multiple tags, while a repository can contain multiple artifacts.

### 12.3 Referential integrity

Primary keys provide stable row identity.

Foreign keys enforce relationships between:

- Registries and repositories.
- Users and permissions.
- Repositories and image artifacts.
- Artifacts and layers.
- Artifacts and tags.
- Artifacts and distribution events.

The `UNIQUE` constraints prevent duplicate repository names within a registry, duplicate user permissions, duplicate repository tags, and duplicate manifest digests within a repository.

### 12.4 Check constraints

Check constraints validate:

- Repository naming conventions.
- Registry endpoint requirements.
- Tag syntax.
- SHA-256 digest formatting.
- Architecture values.
- Layer sizes.
- Semantic version formats.
- Distribution event types.

These constraints prevent invalid data from being stored through ordinary SQL operations.

### 12.5 Triggers

Three major integrity mechanisms are implemented.

**Tag-to-repository validation**

`validate_tag_repository()` ensures that a tag and its referenced artifact belong to the same repository.

**Immutable-tag enforcement**

`enforce_tag_immutability()` prevents reassignment when repository policy or tag protection prohibits it.

**Protected-tag deletion control**

`prevent_protected_tag_deletion()` prevents deletion of protected references.

The layer trigger also prevents adding new layers to artifacts that are not available.

These mechanisms enforce database-level invariants independently of application-level validation.

### 12.6 Access-control function

`check_repository_access()` evaluates whether a user can perform a registry operation.

It considers:

- User activation.
- Registry activation.
- Repository activation.
- Repository visibility.
- Assigned role.
- Requested operation.

The function returns a Boolean eligibility result.

It is an application-level policy evaluation function, not a replacement for PostgreSQL row-level security or database authentication.

### 12.7 Publishing function

`publish_image()` performs a transactional publication workflow.

It:

1. Locks the repository row.
2. Validates repository existence.
3. Checks publishing permissions.
4. Enforces image verification requirements.
5. Validates digests and architecture.
6. Validates the tag.
7. Enforces immutable-tag rules.
8. Inserts the artifact if it does not already exist.
9. Resolves the artifact identifier.
10. Creates or updates the tag.
11. Records an audit event.

The repository-level row lock serializes publications targeting the same repository within the transaction.

The function assumes the supplied digest and verification result have been established by a trusted application service. PostgreSQL does not independently recompute the complete OCI manifest digest from the supplied metadata.

### 12.8 Pull function

`pull_image()` resolves an image through either a tag or manifest digest.

It checks repository access, ensures the artifact is available, returns image metadata and layer sizes, and records distribution and audit events.

The returned information supports deployment orchestration and registry reporting.

### 12.9 Garbage collection

`garbage_collect_repository()` removes artifacts that have no associated tags and are not quarantined.

The procedure uses a common table expression and `DELETE ... RETURNING` to count removed artifacts.

The `ON DELETE CASCADE` relationship removes associated layer records when an artifact is deleted.

The operation requires administrative permission.

The example assumes a simplified reference model. Production cleanup must account for OCI indexes, shared blobs, cross-repository mounts, active uploads, replication, retention requirements, and in-flight pulls.

### 12.10 Reporting views

`repository_inventory` provides repository-level inventory information.

`image_distribution_report` aggregates distribution events and transferred bytes.

The reporting queries also demonstrate:

- Repository access evaluation.
- Available image retrieval.
- Invalid image detection.
- Distribution analysis.
- Audit reporting.
- Layer storage aggregation.

## 13. OCI Compatibility and Registry Protocol Concepts

The Open Container Initiative (OCI) defines specifications that support interoperable container image formats and distribution.

Three important specification areas are:

| Specification area | Responsibility |
|---|---|
| OCI Image Format | Defines image manifests, configurations, and layers |
| OCI Distribution Specification | Defines registry interactions and distribution behavior |
| OCI Runtime Specification | Defines container runtime configuration and execution behavior |

These specifications address different parts of the container ecosystem.

### 13.1 Registry API operations

A registry commonly exposes operations for:

- Checking registry availability.
- Retrieving image manifests.
- Publishing image manifests.
- Retrieving image configuration and layers.
- Uploading image blobs.
- Checking blob existence.
- Deleting supported references where permitted.

Registry clients use HTTP requests to interact with these endpoints.

A distribution workflow typically involves retrieving a manifest and then obtaining the referenced blobs.

### 13.2 Multi-platform images

A single logical image reference can represent multiple platform-specific images.

For example:

    payments/service:2.0.0
        |
        v
    OCI Image Index
        |
        +---- linux/amd64 manifest
        |
        +---- linux/arm64 manifest

The client selects the appropriate manifest for its target platform.

This is important in environments that combine x86-64 and ARM-based infrastructure.

The demonstration programs model architecture metadata but do not implement complete OCI image-index parsing or multi-platform manifest resolution.

## 14. Production Security and Reliability Considerations

### 14.1 Image integrity

Digest verification establishes that retrieved content matches the expected content digest.

It does not establish the publisher's identity.

Image signing and signature verification provide a separate trust mechanism.

### 14.2 Image provenance

Provenance records can describe:

- Source repository.
- Source revision.
- Build process.
- Build dependencies.
- Builder identity.
- Publication time.
- Artifact digest.

Provenance helps establish where an image originated and how it was produced.

### 14.3 Vulnerability assessment

Registry security should include image scanning for:

- Known software vulnerabilities.
- Outdated operating-system packages.
- Vulnerable runtime dependencies.
- Exposed secrets.
- Misconfigured image components.

A vulnerable image can be quarantined pending remediation.

### 14.4 Supply-chain protection

A secure image distribution workflow should distinguish:

1. Image publication.
2. Content integrity verification.
3. Publisher identity verification.
4. Provenance validation.
5. Vulnerability assessment.
6. Deployment authorization.

These are separate security controls. Passing one does not imply that the others have passed.

### 14.5 Availability and resilience

Registry reliability depends on:

- Durable image storage.
- Database backups.
- Blob-storage redundancy.
- Regional replication.
- Network availability.
- Authentication service availability.
- Concurrent upload handling.
- Recovery procedures.

Registry replicas should preserve the relationship between manifests, tags, and referenced content.

### 14.6 Limitations of the implementations

The five implementations are educational registry-management models rather than complete production OCI registry servers.

| Capability | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Repository management | Yes | Yes | Yes | Yes | Yes |
| User authorization | Yes | Yes | Yes | Yes | Yes |
| Digest modeling | SHA-256 | SHA-256 | Demonstration hash | SHA-256 | Validated input |
| Tag management | Yes | Yes | Yes | Yes | Yes |
| Immutable tags | Yes | Yes | Yes | Yes | Yes |
| Protected tags | Limited | Policy-based | Yes | Yes | Yes |
| Image distribution metrics | Yes | Yes | Yes | Yes | Yes |
| Quarantine lifecycle | Defined state | Defined state | Defined state | State transitions | Yes |
| Garbage collection | Yes | Yes | Yes | Yes | Yes |
| Actual layer transfer | No | No | No | No | No |
| Complete OCI API | No | No | No | No | No |
| Distributed replication | No | No | No | No | No |
| Production authentication service | No | No | No | No | No |

The PostgreSQL implementation validates supplied digest formats but does not independently calculate the digest of actual manifest bytes.

The Python and JavaScript implementations use in-memory storage. Their data is lost when the process terminates.

The C++ demonstration hash is not suitable for production image integrity.

The Java implementation models lifecycle and governance but does not implement a network-accessible registry endpoint.

The JavaScript serialized write queue coordinates operations within one process, not across multiple registry instances.

A production system needs durable storage, secure authentication, network transport, content verification, concurrent upload management, replication, and complete OCI protocol handling.

## 15. Cross-Language Design Comparison

The implementations approach the same registry domain through different engineering priorities.

| Language | Primary engineering perspective | Important mechanism |
|---|---|---|
| Python | Domain modeling and workflow simulation | Dataclasses, dictionaries, exceptions |
| JavaScript | Event-driven distribution and policy evaluation | Promises, Maps, EventEmitter |
| C++17 | Explicit repository governance and state management | STL containers, enums, classes |
| Java 17 | Enterprise domain and lifecycle architecture | Records, immutable collections, policy objects |
| PostgreSQL | Persistent relational integrity and operational reporting | Constraints, triggers, functions, procedures |

The shared domain concepts remain consistent:

- Repositories organize image collections.
- Manifests describe image content.
- Digests identify content.
- Tags provide human-readable references.
- Roles determine operational permissions.
- Policies control publishing and retrieval.
- Audit events preserve operational history.
- Lifecycle operations manage artifact availability.
- Garbage collection removes unreferenced artifacts.

The implementations intentionally use different data structures and architectural approaches while preserving these domain distinctions.
