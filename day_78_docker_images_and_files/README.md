# Docker Images and Dockerfiles

## 1. Docker Container Image Fundamentals

Docker images are immutable, layered filesystem artifacts used to create containers. An image contains the application files, runtime dependencies, filesystem metadata, and configuration required to start a container.

A Docker image is not a running application. It is a packaged artifact from which one or more containers can be created.

The principal components are:

| Component | Description |
|---|---|
| Dockerfile | Text-based instructions describing how to construct an image |
| Build context | Files and directories made available to the image builder |
| Docker image | Immutable artifact produced by the build process |
| Image layer | Filesystem changes associated with image construction |
| Image manifest | Metadata describing image configuration and filesystem layers |
| Image configuration | Environment variables, entrypoint, command, user, and related metadata |
| Container | Runtime instance created from an image |
| Image registry | Repository for storing and distributing images |
| Image tag | Human-readable reference to an image |
| Image digest | Content-derived identifier used to identify a specific artifact |

### Image and container relationship

The relationship between an image and a container can be represented as:

    Dockerfile
        |
        v
    Build context
        |
        v
    Image builder
        |
        v
    Image configuration
        |
        +------ Filesystem layers
        |
        v
    Docker image
        |
        v
    Container creation
        |
        v
    Running application

An image can create multiple containers. Changes made to a container's writable layer do not automatically modify its original image.

## 2. Image Layers

An image is constructed using filesystem layers and configuration metadata.

A filesystem layer represents a set of filesystem changes. Depending on the build operation, a layer may introduce application files, dependencies, executables, or other filesystem content.

### 2.1 Layer creation

The principal Dockerfile instructions that create filesystem layers are:

- `FROM`: establishes a base image or build stage.
- `RUN`: executes commands during image construction.
- `COPY`: transfers files from the build context or another stage.
- `ADD`: transfers files and provides additional capabilities such as supported archive extraction.

Instructions such as `ENV`, `WORKDIR`, `USER`, `EXPOSE`, and `CMD` primarily contribute image configuration metadata rather than creating independent filesystem layers.

The distinction matters because the number of Dockerfile instructions is not necessarily equal to the number of filesystem layers.

### 2.2 Layer dependency

Layers are ordered and depend on preceding filesystem state.

    Base image
        |
        v
    Package installation
        |
        v
    Application dependencies
        |
        v
    Application source
        |
        v
    Final image

An image layer can be reused when its relevant build inputs and dependencies remain unchanged.

The relationship between a parent layer and its child layer is important for build-cache evaluation.

### 2.3 Copy-on-write behavior

Container filesystems commonly use union or overlay filesystem mechanisms.

An image provides the lower, read-only filesystem layers. A running container receives a writable layer.

When an application modifies an existing file, the storage driver may use copy-on-write behavior to represent the modification in the container's writable layer.

This allows multiple containers to share image layers without independently duplicating the complete image filesystem.

### 2.4 Image layers versus container writable layers

| Property | Image layer | Container writable layer |
|---|---|---|
| Purpose | Stores image filesystem changes | Stores runtime modifications |
| Lifecycle | Associated with the image | Associated with a container |
| Reuse | Can be shared across containers | Generally container-specific |
| Mutability | Read-only after image construction | Writable |
| Persistence | Remains while referenced | Depends on container lifecycle |
| Distribution | Distributed as image content | Not normally distributed as an image layer |

Applications requiring persistent data should use volumes or appropriate external storage rather than relying on container writable layers.

### 2.5 Layer size

The apparent size of an image depends on its filesystem layers, configuration, compression, and shared content.

Important measurements include:

- Compressed layer size.
- Uncompressed layer size.
- Total image size.
- Shared layer size.
- Container writable-layer usage.

Image size reporting must distinguish between the total size of an image and the additional storage consumed when another image reuses existing layers.

## 3. Dockerfile Structure and Instructions

A Dockerfile describes a sequence of build operations.

Its instructions are processed in order, with certain instructions defining build stages and others modifying the stage's filesystem or configuration.

### 3.1 FROM

`FROM` selects the base image for a build stage.

It can also introduce a named stage.

The multi-stage relationship is:

    FROM build-image AS builder
        |
        v
    Compile application
        |
        v
    FROM runtime-image AS runtime
        |
        v
    COPY --from=builder
        |
        v
    Final application image

A multi-stage build separates the environment required to construct an application from the environment required to execute it.

This can exclude compilers, development tools, temporary files, and build-only dependencies from the final image.

A controlled base image version or verified digest improves reproducibility.

The `latest` tag is mutable and should not be treated as a permanent version identifier.

### 3.2 RUN

`RUN` executes commands during image construction.

Typical operations include:

- Installing operating-system packages.
- Installing application dependencies.
- Compiling application source.
- Creating directories.
- Configuring filesystem permissions.
- Removing temporary build artifacts.

Each filesystem-changing `RUN` operation can contribute a filesystem layer.

Related commands should be combined when doing so reduces unnecessary retained filesystem content and does not reduce maintainability.

For Debian-based images, package installation commonly follows this sequence:

1. Refresh package indexes.
2. Install required packages.
3. Remove package indexes and temporary installation files.

Combining these operations in one `RUN` instruction prevents unnecessary intermediate filesystem content from remaining in earlier layers.

### 3.3 COPY

`COPY` transfers files from the build context or another build stage into the destination filesystem.

Typical uses include:

- Copying dependency manifests.
- Copying application source.
- Copying compiled executables from a build stage.
- Copying configuration files.

Dependency manifests should generally be copied before frequently changing application source.

This arrangement improves the probability that dependency installation can reuse its existing cache entry when application source changes.

### 3.4 ADD

`ADD` provides file-copy functionality with additional behavior, including supported local archive extraction and remote URL handling.

`COPY` is generally preferable for ordinary file transfers because its behavior is more explicit.

Remote downloads should use verified artifacts and controlled integrity checks rather than relying on unverified downloads during image construction.

### 3.5 WORKDIR

`WORKDIR` establishes the working directory for subsequent instructions.

It also affects the default working directory when the container starts.

Explicit working directories improve Dockerfile readability and reduce dependence on implicit paths.

### 3.6 ENV

`ENV` defines environment variables available in subsequent build instructions and the resulting image configuration.

Examples include:

- Runtime mode.
- Application port.
- Application configuration paths.
- Runtime-specific behavior.

Credentials should not be embedded in `ENV` instructions.

Environment variables placed in image configuration may be visible through image inspection and container metadata.

BuildKit secrets or an appropriate external secret-management mechanism should be used for sensitive build inputs and runtime credentials.

### 3.7 ARG

`ARG` defines build-time variables.

Build arguments can influence image construction without automatically becoming runtime environment variables.

They are useful for controlled build configuration, but they should not be used as a mechanism for protecting secrets.

Build arguments may be exposed through build metadata, logs, provenance, or other build outputs depending on the build process.

### 3.8 EXPOSE

`EXPOSE` documents the intended container listening port.

It does not automatically publish the port to the host.

Host-to-container port mapping must be configured separately when starting the container or defining its deployment configuration.

### 3.9 USER

`USER` specifies the user and optionally the group under which subsequent instructions and the container process execute.

Running application processes as a non-root user reduces the impact of certain application compromises.

The user must have appropriate permissions for required application directories and files.

### 3.10 CMD and ENTRYPOINT

These instructions define container startup behavior.

| Instruction | Purpose |
|---|---|
| CMD | Provides the default command or default arguments |
| ENTRYPOINT | Defines the primary executable |
| Both | ENTRYPOINT defines the executable while CMD can provide default arguments |

Shell form and exec form have different process and signal-handling behavior.

Exec form is generally preferable for application startup because it avoids an unnecessary intermediate shell process.

Correct process handling is important for graceful termination and container orchestration.

### 3.11 LABEL

`LABEL` adds metadata to an image.

Useful metadata includes:

- Application name.
- Maintainer information.
- Source repository.
- Build version.
- Revision identifier.
- License information.

Labels support artifact identification and operational management.

### 3.12 HEALTHCHECK

`HEALTHCHECK` defines a command that can be used to determine whether a container is functioning correctly.

A health check should evaluate actual application readiness or health rather than merely verifying that a process exists.

An inappropriate health check can create misleading operational signals.

### 3.13 VOLUME

`VOLUME` declares a mount point for persistent or externally managed storage.

It does not itself establish a complete storage-management policy.

The actual storage location and lifecycle depend on the runtime configuration.

### 3.14 SHELL

`SHELL` changes the shell used by subsequent shell-form instructions.

It is relevant when build commands require particular shell behavior.

## 4. Docker Build Context

The build context is the set of files made available to the builder.

When a build command is executed, the selected context determines which local files can be accessed through ordinary `COPY` and `ADD` instructions.

For example:

    docker build -t inventory-api:1.0 .

The final period identifies the current directory as the build context.

An unnecessarily large context increases file-transfer costs and can expose irrelevant files to the build process.

### 4.1 .dockerignore

A `.dockerignore` file excludes unnecessary content from the build context.

Common exclusions include:

- `.git`
- `node_modules`
- Python virtual environments.
- Cache directories.
- Local environment files.
- Test output.
- Temporary files.
- Local build artifacts.

Sensitive files should be excluded where they are not required for construction.

The `.dockerignore` file reduces unnecessary transfer and helps limit accidental inclusion of local data.

It does not replace proper secret-management controls.

## 5. Image Building and Build Lifecycle

Image construction involves more than executing Dockerfile instructions.

A practical build lifecycle includes:

1. Selecting a Dockerfile.
2. Establishing the build context.
3. Resolving the base image.
4. Processing build arguments.
5. Evaluating build instructions.
6. Checking cache eligibility.
7. Creating or reusing filesystem layers.
8. Constructing image configuration.
9. Producing the final image.
10. Tagging and optionally publishing the artifact.

### 5.1 Build context and instruction processing

The builder uses the Dockerfile and available build inputs to determine the operations required to produce the image.

A build may fail because of:

- Invalid Dockerfile syntax.
- Missing files.
- Invalid base image references.
- Network failures.
- Package installation failures.
- Compilation errors.
- Permission problems.
- Insufficient storage.
- Invalid build arguments.

Failure handling should preserve diagnostic output and identify the failing stage or instruction.

### 5.2 Image tags

An image tag is a human-readable reference.

For example:

    inventory-api:1.0.0
    inventory-api:1.1.0
    inventory-api:production

A tag can be moved to refer to another image.

Therefore, a tag alone does not provide immutable artifact identification.

### 5.3 Image digests

An image digest identifies content using a cryptographic hash.

Digest-based references provide stronger artifact identity than mutable tags.

For controlled production deployments, a digest can be used to ensure that the intended image content is deployed.

A registry may store multiple tags that refer to the same underlying image manifest.

## 6. Docker Build Cache

Docker build caching avoids repeating work when relevant build inputs remain unchanged.

The builder evaluates whether an earlier build result can be reused.

### 6.1 Cache dependencies

A layer's cache eligibility depends on relevant inputs and the preceding build state.

Conceptually:

    Base image
        |
        v
    Dependency manifest
        |
        v
    Dependency installation
        |
        v
    Application source
        |
        v
    Application build

If application source changes but the dependency manifest remains unchanged, the dependency installation stage may remain reusable.

If the dependency manifest changes, the installation stage generally needs to be evaluated again.

Cache behavior also depends on builder implementation, build configuration, external inputs, and cache settings.

### 6.2 Instruction ordering

Consider two approaches.

**Less efficient ordering**

    COPY . .
    RUN install-dependencies

Changes to unrelated application files can invalidate the dependency installation cache.

**Improved ordering**

    COPY dependency-manifest .
    RUN install-dependencies
    COPY application-source .

The dependency installation can remain cached when only application source changes.

### 6.3 Cache invalidation

Cache entries can become unusable when relevant inputs change.

Examples include:

- A changed parent image.
- Modified source files.
- Changed dependency manifests.
- Modified build arguments.
- Changed instruction arguments.
- Different build-stage dependencies.

External package repositories and remote resources require special consideration because their contents can change independently of local source files.

A cached operation should not automatically be interpreted as proof that external dependencies remain current or secure.

### 6.4 Cache management

Build cache can be inspected and managed through Docker commands.

Important operations include:

- `docker image history`
- `docker image inspect`
- `docker builder du`
- `docker builder prune`

Cache pruning removes eligible cached build data. It should be coordinated with build-storage requirements and the expected cost of rebuilding.

## 7. Multi-Stage Builds

Multi-stage builds use multiple `FROM` instructions to separate construction environments.

A typical application build has two stages.

| Stage | Responsibility | Typical contents |
|---|---|---|
| Builder | Construct application artifacts | Compiler, development dependencies, source code |
| Runtime | Execute the application | Application executable, runtime dependencies |

The runtime stage receives only the artifacts required for execution.

### Practical advantages

- Reduced runtime image size.
- Fewer unnecessary packages.
- Smaller operational attack surface.
- Separation of build and runtime dependencies.
- Cleaner application packaging.

### Important considerations

A multi-stage build does not automatically guarantee a minimal image.

The runtime stage may still contain unnecessary packages, copied development dependencies, or temporary files.

The final stage must be evaluated independently.

## 8. Docker Image Optimization

Image optimization aims to reduce unnecessary content, improve build efficiency, and simplify runtime operation.

### 8.1 Reduce base image overhead

Use an appropriate base image rather than selecting an image solely because it is popular or familiar.

Evaluate:

- Operating-system requirements.
- Architecture compatibility.
- Required runtime libraries.
- Security maintenance.
- Image size.
- Update availability.

Minimal images may reduce unnecessary packages, but they must still contain the libraries and utilities required by the application.

### 8.2 Use multi-stage builds

Separate application compilation from application execution.

Only required artifacts should be copied into the final stage.

### 8.3 Optimize package installation

Install only required packages.

Combine related package operations and remove package indexes and temporary artifacts within the same filesystem-changing operation.

### 8.4 Optimize dependency installation

Use lockfiles and reproducible dependency installation.

Copy dependency manifests before application source.

Avoid including development dependencies in the production runtime image unless explicitly required.

### 8.5 Optimize build context

Use `.dockerignore` to exclude unnecessary files.

A smaller context can improve transfer speed and reduce the chance of accidentally exposing local files.

### 8.6 Minimize retained files

Remove temporary build artifacts, package caches, and unnecessary documentation from the final runtime image.

Deleting files in a later layer does not necessarily remove the data from earlier image layers.

This is why cleanup should occur within the same relevant `RUN` operation whenever practical.

### 8.7 Avoid unnecessary layers

Combine related filesystem operations where appropriate.

Do not combine every command into one enormous instruction.

Readable and maintainable Dockerfiles are important for debugging and security review.

### 8.8 Select appropriate file ownership

Set appropriate ownership and permissions for application files.

Avoid granting unnecessary write permissions to the runtime user.

### 8.9 Image optimization comparison

| Technique | Primary benefit | Important consideration |
|---|---|---|
| Multi-stage builds | Smaller runtime artifacts | Correct artifact transfer |
| Minimal base images | Reduced package footprint | Runtime compatibility |
| `.dockerignore` | Smaller build context | Required files must remain available |
| Dependency-first COPY | Better cache reuse | Correct dependency boundaries |
| Package cleanup | Reduced retained content | Cleanup must occur in the same layer |
| Non-root execution | Reduced privilege | Filesystem permissions |
| Digest pinning | Reproducible base reference | Controlled update process |
| Dependency lockfiles | Reproducible dependency resolution | Regular security updates |

## 9. Docker Image Security

An image is part of the application's software supply chain.

Its security depends on its base image, dependencies, build process, configuration, and runtime privileges.

### 9.1 Base image security

Use maintained and verified base images.

Evaluate the source, supported versions, security updates, and image provenance.

Digest pinning helps identify exact image content, but it does not automatically guarantee that the content is secure or current.

### 9.2 Secret management

Do not place credentials in:

- Dockerfile `ENV` instructions.
- Dockerfile `ARG` instructions.
- Source files copied into the image.
- Shell command history.
- Unprotected build logs.

Use appropriate build secrets and runtime secret-management mechanisms.

### 9.3 Non-root execution

Use an explicitly defined application user.

Verify that the user can read required files and write only to directories where write access is necessary.

### 9.4 Vulnerability scanning

Image scanning evaluates known vulnerabilities in operating-system packages and application dependencies.

Important fields include:

- Vulnerability identifier.
- Package name.
- Installed version.
- Fixed version.
- Severity.
- Scanner version.
- Scan timestamp.

A vulnerability assessment must be interpreted in context.

A scan that reports no findings does not establish that an image is completely secure.

### 9.5 Image signing and provenance

Image signing helps establish artifact authenticity and integrity.

Build provenance records information about the build inputs and process.

These controls support software supply-chain governance and should be integrated with registry and deployment policies.

### 9.6 Runtime security

Image security should be combined with runtime controls.

Examples include:

- Non-root container execution.
- Read-only root filesystems where practical.
- Restricted Linux capabilities.
- Resource limits.
- Network segmentation.
- Controlled volume mounts.
- Appropriate seccomp profiles.

## 10. Python Implementation

The Python implementation provides a standalone Dockerfile analysis and image-layer simulation system.

### Main components

| Component | Responsibility |
|---|---|
| `InstructionType` | Defines supported Dockerfile instructions |
| `Instruction` | Represents an individual parsed instruction |
| `Layer` | Stores simulated layer information |
| `Finding` | Represents a validation or security observation |
| `DockerfileParser` | Parses Dockerfile instructions |
| `DockerfileAnalyzer` | Identifies security and optimization concerns |
| `ImageBuilder` | Simulates layer creation and caching |
| `BuildResult` | Stores build metrics and findings |
| `DockerCLI` | Executes selected real Docker commands |

### Parsing mechanism

The parser handles:

- Empty lines.
- Comments.
- Instruction names.
- Instruction arguments.
- Continued logical lines.
- Invalid instructions.
- Missing arguments.
- Missing initial `FROM`.

The parser provides logical instruction numbering. This should not be confused with physical Dockerfile line numbering.

### Image-layer simulation

The `ImageBuilder` calculates deterministic cache keys using SHA-256.

Each layer depends on its preceding simulated layer and instruction content.

The cache stores estimated layer-size contributions.

A repeated build can therefore demonstrate cache reuse.

The implementation deliberately separates:

- Dockerfile instructions.
- Simulated filesystem layers.
- Cache keys.
- Estimated size.
- Security findings.

The size estimates are educational values, not actual measurements from Docker.

### Real Docker integration

The `DockerCLI` class uses Python's `subprocess.run`.

It supports:

- Image construction.
- Image inspection.
- Image history.

Commands use argument lists rather than shell command concatenation.

This reduces shell-injection exposure.

The Docker CLI must be installed, accessible through PATH, and connected to a functioning Docker daemon.

## 11. JavaScript Implementation

The JavaScript implementation provides an event-driven build-analysis pipeline.

### Main components

| Component | Responsibility |
|---|---|
| `DockerfileParser` | Parses Dockerfile instructions |
| `Layer` | Calculates layer identity |
| `BuildCache` | Maintains reusable build entries |
| `BuildEngine` | Processes layer dependencies |
| `SecurityPolicy` | Evaluates security requirements |
| `OptimizationAnalyzer` | Produces optimization recommendations |
| `DockerPipeline` | Coordinates the complete workflow |
| `DockerCLI` | Integrates with the Docker command-line interface |

### Event-driven execution

`BuildEngine` extends Node.js `EventEmitter`.

It emits events for:

- `layer-built`
- `cache-hit`
- `build-complete`

`DockerPipeline` forwards relevant events to its consumers.

This separation allows a user interface, logging component, or monitoring service to observe build progress without being directly coupled to layer construction.

### Cache implementation

The implementation uses a JavaScript `Map` for cache storage.

A SHA-256 hash represents the simulated relationship between a parent layer and its instruction.

The cache is maintained in memory and is not a persistent BuildKit cache.

### Security policy

The security policy evaluates:

- Mutable base image tags.
- Credentials in environment variables.
- Root runtime execution.
- Unverified remote scripts.
- Missing startup instructions.
- Package-manager cleanup.

Findings have explicit severity values.

The pipeline calculates whether security errors block the build.

### Asynchronous and operational extension

The event-driven design can be extended to asynchronous build orchestration.

In an operational implementation, asynchronous build workers would also require:

- Cancellation.
- Timeouts.
- Retry policies.
- Distributed locking where appropriate.
- Persistent build state.
- Resource limits.
- Structured logging.

The supplied implementation deliberately keeps build simulation synchronous.

## 12. C++17 Implementation

The C++ implementation models image construction as a collection of typed domain objects.

### Main components

| Component | Responsibility |
|---|---|
| `Instruction` | Represents a Dockerfile instruction |
| `ImageLayer` | Represents an image-layer candidate |
| `BuildMetrics` | Stores build statistics |
| `DockerfileParser` | Validates and parses instructions |
| `SecurityAnalyzer` | Identifies Dockerfile security concerns |
| `ImageCache` | Stores reusable layer estimates |
| `OptimizationAnalyzer` | Produces optimization recommendations |
| `DockerBuildEngine` | Creates the build report |
| `DockerImageRegistry` | Models image publication controls |

### Type-safe modeling

The implementation uses enumerations for instruction types, severity levels, and build statuses.

This reduces dependence on unrestricted string comparisons.

Structures represent domain objects with clearly defined responsibilities.

### Cache behavior

The C++ cache uses an `unordered_map`.

This provides average constant-time lookup for cache entries.

The educational implementation uses FNV-1a to calculate deterministic cache keys.

FNV-1a is not a cryptographic hash and must not be used for production artifact integrity or security verification.

A production implementation should use an appropriate cryptographic content digest.

### Registry publication

The registry checks whether a build contains security errors before accepting the artifact.

It also prevents duplicate image names within the in-memory registry model.

This demonstrates the separation between constructing an image and authorizing its publication.

The registry is not a real Docker registry and does not implement network distribution.

## 13. Java 17 Implementation

The Java implementation models Docker image construction as an enterprise build-governance workflow.

### Domain types

Java records represent immutable data structures.

Examples include:

- `Instruction`
- `Finding`
- `ImageLayer`
- `BuildMetrics`
- `BuildReport`
- `BuildRequest`

Enums represent:

- Dockerfile instruction types.
- Finding severity.
- Build states.
- Layer status.

### Build service

`BuildService` coordinates parsing, policy evaluation, layer planning, and build reporting.

Its processing sequence is:

    BuildRequest
        |
        v
    DockerfileParser
        |
        v
    SecurityPolicy
        |
        v
    LayerPlanner
        |
        v
    BuildCache
        |
        v
    BuildReport
        |
        v
    ImageRegistry

### State management

`BuildLifecycle` maintains explicit build states.

The modeled states are:

| State | Meaning |
|---|---|
| CREATED | Initial state |
| VALIDATED | Request has passed initial processing |
| BUILDING | Layer planning is underway |
| BUILT | Image build simulation succeeded |
| FAILED | Processing failed |
| PUBLISHED | Artifact passed publication controls |

Invalid transitions raise exceptions.

For example, a successfully published build cannot transition back into the building state.

### Security and publication

The `SecurityPolicy` evaluates image construction requirements.

The `ImageRegistry` rejects artifacts that contain security errors.

The policy evaluation and publication responsibilities remain separate.

A Dockerfile can be syntactically valid while still violating security requirements.

A successfully constructed image can also be rejected by publication policy.

### Immutability

The Java implementation uses immutable records and defensive copies of collections.

This prevents external callers from modifying the contents of an already-created build report.

The in-memory registry is a simplified enterprise model, not a replacement for a production artifact registry.

## 14. PostgreSQL Implementation

The PostgreSQL implementation provides a relational representation of Docker image construction and governance.

It separates Dockerfile definitions, build executions, image layers, published artifacts, security assessments, and deployment records.

### Entity relationships

    Repositories
        |
        v
    Dockerfiles
        |
        v
    Dockerfile Instructions
        |
        v
    Image Builds
        |
        +------ Image Layers
        |
        +------ Build Cache
        |
        v
    Image Artifacts
        |
        +------ Security Assessments
        |           |
        |           v
        |       Vulnerability Findings
        |
        +------ Policy Evaluations
        |
        v
    Image Deployments

### Main relational entities

| Table | Responsibility |
|---|---|
| `repositories` | Stores application repositories |
| `base_images` | Records available base image references |
| `dockerfiles` | Stores versioned Dockerfile content |
| `dockerfile_instructions` | Stores individual Dockerfile instructions |
| `image_builds` | Records build executions |
| `image_layers` | Stores layer metadata and dependencies |
| `build_cache` | Records reusable build-cache information |
| `image_artifacts` | Stores published image metadata |
| `security_assessments` | Stores image scanning results |
| `vulnerability_findings` | Stores individual vulnerability records |
| `build_policies` | Defines repository-level image requirements |
| `policy_evaluations` | Stores eligibility decisions |
| `image_deployments` | Records image deployment activity |

### Relational integrity

Primary keys identify records.

Foreign keys enforce relationships between repositories, Dockerfiles, builds, layers, artifacts, and assessments.

Unique constraints prevent duplicate repository names, Dockerfile versions, layer numbers within a build, artifact digests, and other conflicting identifiers.

Check constraints enforce positive version numbers, non-negative sizes, and valid digest formats.

### Layer dependency management

The `image_layers` table contains a self-referencing parent relationship.

A layer can identify the preceding layer within the same build.

The `validate_layer_parent()` trigger prevents a layer from referring to an invalid parent or a parent that appears later in the layer sequence.

### Build-state transitions

The `image_builds` table tracks the build lifecycle.

The `validate_build_transition()` trigger rejects invalid state changes.

The modeled lifecycle is:

    QUEUED
       |
       v
    VALIDATING
       |
       v
    BUILDING
       |
       v
    BUILT

Failure and cancellation are represented as terminal outcomes.

### Security assessments

Security assessments are stored separately from image artifacts.

This allows an artifact to receive multiple assessments over time.

The vulnerability table records package-level findings.

The `update_security_assessment_counts()` trigger maintains the aggregate counts when findings are inserted, updated, or deleted.

### Build policies

The `build_policies` table stores controls such as:

- Non-root execution.
- Digest-pinned base image requirements.
- Successful vulnerability scanning.
- Maximum image size.
- Maximum critical vulnerabilities.
- Maximum high-severity vulnerabilities.
- Signed-image requirements.

The `evaluate_image_eligibility()` function evaluates a published image against its repository policy.

It returns an eligibility result and a JSONB array containing identified violations.

### Policy evaluation

The `evaluate_all_images()` procedure processes enabled repository policies and stores the results in `policy_evaluations`.

A policy decision is stored separately from the underlying image and security assessment.

This preserves the distinction between the artifact's technical properties and its authorization for a particular use.

### Reporting

The database includes queries for:

- Dockerfile instruction retrieval.
- Dockerfile validation.
- Image size aggregation.
- Layer cache utilization.
- Vulnerability reporting.
- Image eligibility.
- Deployment history.
- Multi-stage build analysis.
- Optimization opportunities.
- Recursive layer dependencies.
- Repository build performance.

Indexes support common retrieval and reporting operations.

The recursive CTE demonstrates how layer dependencies can be traversed.

## 15. Docker Build Optimization Workflow

A practical image optimization process should evaluate both the Dockerfile and the resulting image.

The following workflow provides a structured approach.

| Stage | Activity | Expected result |
|---|---|---|
| 1 | Inspect the Dockerfile | Understand existing instructions |
| 2 | Inspect the build context | Identify unnecessary files |
| 3 | Inspect the base image | Evaluate size and maintenance |
| 4 | Review instruction ordering | Improve cache reuse |
| 5 | Review package installation | Remove unnecessary dependencies |
| 6 | Evaluate multi-stage construction | Separate build and runtime content |
| 7 | Review permissions | Minimize runtime privileges |
| 8 | Build the image | Produce the candidate artifact |
| 9 | Inspect image layers | Identify large filesystem contributions |
| 10 | Scan the image | Identify known vulnerabilities |
| 11 | Evaluate governance policies | Determine publication eligibility |
| 12 | Publish and deploy | Distribute the approved artifact |

The optimization process should compare actual measurements before and after changes.

Relevant measurements include:

- Total image size.
- Compressed image size.
- Number of filesystem layers.
- Build duration.
- Cache-hit rate.
- Build-context size.
- Vulnerability counts.
- Runtime startup time.

A smaller image is not automatically a better image. Runtime compatibility, security maintenance, reliability, and reproducibility must also be considered.

## 16. Build and Execution Commands

### Python

Run the demonstration:

`python docker_images.py`

Analyze an existing Dockerfile:

`python docker_images.py --dockerfile Dockerfile`

Build an actual image:

`python docker_images.py --build --context . --tag inventory-api:1.0`

Inspect a local image:

`python docker_images.py --image inventory-api:1.0`

### JavaScript

Run the demonstration:

`node docker-images.js`

Analyze an existing Dockerfile:

`node docker-images.js --analyze Dockerfile`

Build an actual image:

`node docker-images.js --docker-build . --file Dockerfile --tag inventory-api:1.0`

Inspect an image:

`node docker-images.js --inspect inventory-api:1.0`

### C++17

Compile:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic docker_images.cpp -o docker_images`

Execute:

`./docker_images`

On Windows:

`docker_images.exe`

### Java 17

Compile:

`javac DockerEnterprise.java`

Execute:

`java DockerEnterprise`

### PostgreSQL

Execute the complete SQL script using PostgreSQL's `psql` client:

`psql -U postgres -d docker_learning -f docker_images.sql`

The target database must already exist.

The SQL script creates the `docker_platform` schema and its objects.

## 17. Limitations and Engineering Considerations

The five implementations deliberately use different models of Docker image construction.

| Implementation | Primary model | Important limitation |
|---|---|---|
| Python | Parsing, simulation, and CLI integration | Simulated image sizes are estimates |
| JavaScript | Event-driven analysis and cache evaluation | In-memory synchronous simulation |
| C++17 | Typed layer and registry model | Educational non-cryptographic cache key |
| Java 17 | Enterprise build lifecycle and policy service | In-memory registry and simulated builds |
| PostgreSQL | Persistent relational governance model | Stores image metadata rather than actual image binaries |

The simulated build engines do not reproduce all internal Docker or BuildKit behavior.

Actual layer construction depends on the selected builder, filesystem changes, build arguments, external resources, cache configuration, platform, and other build inputs.

The SQL model also does not implement a complete OCI image registry, image manifest parser, or binary layer storage engine.

Production deployment requires appropriate integration with the Docker Engine or BuildKit, a compatible registry, vulnerability scanners, artifact-signing mechanisms, and deployment infrastructure.

The distinction between Dockerfile instructions, filesystem layers, image configuration, build-cache entries, image artifacts, and runtime containers remains fundamental to understanding and engineering Docker image workflows.
