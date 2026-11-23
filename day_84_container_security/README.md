# Container Security Engineering

## 1. Technical Scope

Container security protects the complete container lifecycle, from image construction and dependency management to deployment and runtime execution.

A container image contains an application, its runtime, dependencies, configuration and filesystem layers. A vulnerable or incorrectly configured image can introduce risks into every environment in which it is deployed.

This implementation covers five connected security areas:

| Security area | Primary objective |
|---|---|
| Image scanning | Identify vulnerable packages and dependencies |
| Minimal images | Reduce unnecessary components and attack surface |
| Vulnerability management | Prioritize, remediate and verify security findings |
| Runtime security | Detect and restrict suspicious container behavior |
| Secrets management | Prevent credentials from entering images and logs |

The five source files implement these controls using different engineering approaches.

## 2. Container Image Architecture

A container image is a collection of filesystem layers and metadata used to create container instances.

A typical image includes:

- Base operating system or minimal runtime.
- Application executable.
- Runtime dependencies.
- Application configuration.
- Image metadata.
- Entrypoint and command definitions.
- User and permission settings.

The image is immutable after construction. Changes require building a new image.

A container is a running instance of an image. Multiple containers can use the same image while maintaining separate process and runtime states.

### Image construction workflow

Build context → Base image → Dependency installation → Application files → Image layers → Image digest → Security scan → Signature verification → Registry → Deployment admission → Runtime monitoring

Each stage introduces different security considerations.

An image that passes a vulnerability scan is not automatically secure. Runtime configuration, image provenance, secret exposure and deployment privileges must also be evaluated.

## 3. Image Scanning

Image scanning examines image contents to identify known vulnerabilities and configuration weaknesses.

A scanner can inspect:

- Operating system packages.
- Application dependencies.
- Language-specific libraries.
- Package versions.
- Known CVEs.
- Embedded credentials.
- Image configuration.
- Filesystem contents.

### 3.1 Common vulnerability sources

| Source | Example |
|---|---|
| Operating system | Vulnerable system library |
| Application dependency | Outdated Python package |
| Runtime | Vulnerable Java runtime |
| Build dependency | Compromised compiler component |
| Application package | Insecure third-party library |

A vulnerability is commonly identified through its Common Vulnerabilities and Exposures identifier.

Examples use the format `CVE-YYYY-NNNN`.

### 3.2 Severity classification

The implementations use five severity categories.

| Severity | Meaning | Typical treatment |
|---|---|---|
| CRITICAL | Severe security impact | Block deployment |
| HIGH | Significant security exposure | Block deployment under strict policy |
| MEDIUM | Moderate security exposure | Evaluate against thresholds |
| LOW | Lower assessed impact | Track and remediate |
| UNKNOWN | Insufficient classification | Investigate before acceptance |

CVSS provides a standardized vulnerability severity scoring methodology. Severity alone does not determine actual operational risk.

Practical prioritization should also consider:

- Exploit availability.
- Network accessibility.
- Application exposure.
- Required privileges.
- Vulnerable code execution paths.
- Available remediation.
- Existing compensating controls.

A critical vulnerability in an unreachable component may have a different operational priority from an exploitable high-severity vulnerability in an internet-facing service.

### 3.3 Vulnerability data model

The implementations distinguish three related entities:

1. Vulnerability: The CVE record and its published characteristics.
2. Package: The specific component and installed version.
3. Image finding: The relationship between a vulnerable package and a particular image.

This distinction prevents a CVE record from being incorrectly treated as proof that every image contains the affected package.

The PostgreSQL implementation uses `vulnerabilities`, `image_packages` and `image_vulnerabilities` to maintain these relationships.

### 3.4 Vulnerability remediation

A typical remediation process is:

1. Identify the affected image.
2. Identify the vulnerable package.
3. Determine the installed version.
4. Check whether a fixed version exists.
5. Update the dependency.
6. Rebuild the image.
7. Scan the new image.
8. Verify the new image digest.
9. Evaluate deployment eligibility.
10. Retain the scan and remediation history.

A finding should not be marked resolved simply because a newer package version is available. The rebuilt image must be verified.

## 4. Minimal Container Images

Minimal images reduce the number of components required to execute an application.

A smaller image can reduce:

- Vulnerable package count.
- Unnecessary executable availability.
- Filesystem complexity.
- Image transfer time.
- Storage consumption.
- Potential attack surface.

### 4.1 Image design approaches

| Image approach | Characteristics | Security considerations |
|---|---|---|
| General-purpose OS image | Includes many system utilities | Larger attack surface |
| Slim image | Removes unnecessary packages | Requires dependency validation |
| Minimal runtime image | Includes application runtime components | Smaller operational footprint |
| Distroless image | Excludes conventional shells and package managers | Requires appropriate debugging strategy |
| Scratch-based image | Starts with an empty base filesystem | Application must provide all required runtime components |

Minimal images are not automatically secure. They can still contain vulnerable libraries, unsafe application code, embedded credentials or incorrect runtime permissions.

### 4.2 Multi-stage builds

Multi-stage builds separate compilation dependencies from the final runtime image.

Typical structure:

Build stage:
- Compiler.
- Package manager.
- Development dependencies.
- Build scripts.
- Intermediate artifacts.

Runtime stage:
- Required runtime.
- Application executable.
- Essential libraries.
- Application configuration.

The final image should not contain unnecessary compilers, source-control tools, package caches or build credentials.

### 4.3 Non-root execution

Running a container as root increases the consequences of certain application and container-runtime compromises.

The implementations enforce a non-root user through a numerical UID.

The numerical UID is evaluated because usernames and account databases may not exist in minimal images.

A production container should also consider:

- Read-only root filesystem.
- Restricted Linux capabilities.
- Appropriate seccomp profile.
- AppArmor or SELinux controls.
- Resource limits.
- Restricted host mounts.
- Restricted device access.

A non-root UID is an important control, but it does not replace these additional restrictions.

### 4.4 Privileged execution

Privileged containers receive significantly broader host-level capabilities than ordinary containers.

This increases the risk that a compromised container could affect its host.

Production workloads should generally avoid privileged execution.

Where specific capabilities are required, grant only the necessary capabilities rather than enabling unrestricted privileged mode.

## 5. Vulnerability Management and Policy Evaluation

Scanning identifies findings. Security policies determine whether those findings are acceptable.

These are separate operations.

The implemented policy evaluates:

- Maximum critical vulnerability count.
- Maximum high vulnerability count.
- Maximum medium vulnerability count.
- Image size.
- Execution identity.
- Privileged execution.
- Shell availability.
- Signature verification.
- Secret exposure.
- Unknown vulnerability classifications.
- Availability of vulnerability fixes.

### 5.1 Admission decisions

The implementations use three outcomes.

| Decision | Meaning | Operational effect |
|---|---|---|
| ALLOW | All mandatory controls pass | Deployment may proceed |
| DENY | A mandatory control fails | Deployment is rejected |
| REVIEW | Findings require additional assessment | Automated deployment is withheld |

The distinction between `DENY` and `REVIEW` is important.

A medium-severity vulnerability exceeding a configured threshold may require investigation. A root-running image or an image containing an exposed private key is treated as a mandatory rejection.

The sample policies are illustrative rather than universal security standards.

### 5.2 Policy evaluation sequence

Image metadata
→ Vulnerability inventory
→ CVE thresholds
→ Execution configuration
→ Minimal image requirements
→ Signature verification
→ Provenance verification
→ Secret exposure
→ Admission decision

The policy must be evaluated against the exact immutable image digest that will be deployed.

Using only a mutable image tag can create a time-of-check/time-of-use problem. The tag might reference a different image after scanning.

## 6. Image Provenance and Integrity

Image provenance provides information about where an image originated and how it was constructed.

Important provenance information includes:

- Publisher identity.
- Source repository.
- Source revision.
- Build pipeline.
- Build identity.
- Signature.
- Attestation.
- Image digest.

### 6.1 Image digest

An image digest identifies a specific image manifest or content-addressed artifact.

The implementations validate SHA-256 digest formatting.

A tag such as `payments-api:1.4.2` is a human-readable reference. It is not a guarantee that the referenced image will remain unchanged.

A digest provides a stronger identity for security evaluation and deployment.

### 6.2 Image signatures

Digital signatures provide a way to verify that an image was signed by an expected identity and that the signed content has not been modified.

A production signature verification workflow must validate:

1. Signature integrity.
2. Signer identity.
3. Trusted identity policy.
4. Image digest binding.
5. Certificate or key trust.
6. Relevant attestation claims.

The sample implementations model signature verification as a Boolean result. They do not implement cryptographic signature verification or certificate-chain validation.

A real deployment admission controller must perform those operations using an appropriate trusted verification mechanism.

## 7. Runtime Security

Image scanning is primarily a pre-deployment activity.

Runtime security examines the behavior of an active container.

A container can pass an image scan and still become compromised through:

- Application vulnerabilities.
- Runtime exploitation.
- Malicious requests.
- Insecure application configuration.
- Credential theft.
- Unauthorized process execution.
- Unsafe mounted filesystems.
- Network-based attacks.

### 7.1 Runtime event categories

| Event | Security concern |
|---|---|
| PROCESS_EXECUTION | Unexpected executable activity |
| SHELL_EXECUTION | Interactive or unauthorized shell |
| PRIVILEGED_EXECUTION | Elevated execution privileges |
| SECRET_ACCESS | Unexpected credential access |
| FILESYSTEM_WRITE | Unauthorized filesystem modification |
| NETWORK_CONNECTION | Unexpected outbound or lateral communication |

### 7.2 Runtime decision model

The source files implement a simple rule-based monitoring engine.

Examples:

- Root execution: DENY.
- Shell execution: DENY.
- Privileged execution: DENY.
- Known suspicious networking utility: DENY.
- Unexpected secret access: REVIEW.
- Filesystem modification: REVIEW.
- Ordinary application process: ALLOW.

These rules demonstrate policy evaluation rather than a complete runtime detection platform.

Actual runtime monitoring should incorporate process ancestry, container identity, namespace information, capabilities, filesystem context, network destination and workload behavior.

### 7.3 Runtime isolation controls

Important Linux and container-runtime controls include:

| Control | Security purpose |
|---|---|
| Namespaces | Isolate processes, networks and other resources |
| cgroups | Restrict and account for resource usage |
| seccomp | Restrict permitted system calls |
| Linux capabilities | Reduce privileged operations |
| AppArmor | Apply mandatory access restrictions |
| SELinux | Enforce mandatory access-control policies |
| Read-only filesystem | Reduce unauthorized filesystem changes |
| Network policies | Restrict communication paths |

Runtime security requires monitoring and enforcement. Recording suspicious events without preventing prohibited activity does not provide complete protection.

## 8. Secrets Management

Secrets are sensitive values used to authenticate or authorize access.

Examples include:

- Database passwords.
- API keys.
- Cloud access credentials.
- Private keys.
- Authentication tokens.
- Service account credentials.
- Encryption keys.

### 8.1 Why secrets must not be embedded in images

Embedding credentials in Dockerfiles, environment files or image layers can expose them through:

- Image registries.
- Build caches.
- Container inspection.
- Image extraction.
- Source repositories.
- CI/CD logs.
- Layer history.

Removing a secret in a later image layer does not necessarily remove it from earlier layers.

A leaked credential should be treated as compromised even after the visible file is deleted.

### 8.2 Secret scanning

The implementations recognize common patterns for:

- AWS access keys.
- Private-key headers.
- GitHub tokens.
- Password assignments.

These are heuristic detection patterns.

They cannot establish whether every discovered value is valid, and they cannot detect every secret format.

A production secret scanner should combine:

- Pattern matching.
- Entropy analysis.
- Contextual validation.
- Provider-specific verification where safe.
- False-positive management.
- Secret fingerprinting.

### 8.3 Secure secret delivery

A secure workflow is:

Application deployment
→ Workload identity verification
→ Secret manager authorization
→ Short-lived credential retrieval
→ Application use
→ Credential rotation or expiration

Secrets should be supplied at runtime through an appropriately secured mechanism.

They should not be stored in image layers or exposed through application logs.

Examples of secret-delivery approaches include mounted secret files, workload identity and external secret-manager integrations.

### 8.4 Credential incident response

When a credential is discovered in an image:

1. Block the image.
2. Identify affected environments.
3. Revoke or rotate the exposed credential.
4. Investigate potential unauthorized access.
5. Remove the credential from the build process.
6. Rebuild the image.
7. Rescan the replacement image.
8. Verify its provenance and digest.
9. Record remediation evidence.

Removing the credential from the latest image alone is insufficient.

## 9. Python Implementation

**File:** `container_security.py`

The Python implementation provides a complete repository-independent container security simulation.

### 9.1 Main components

| Component | Responsibility |
|---|---|
| `Vulnerability` | Models an individual CVE finding |
| `ContainerImage` | Maintains image metadata and security attributes |
| `SecurityPolicy` | Defines deployment requirements |
| `ImageScanner` | Evaluates vulnerabilities and image configuration |
| `ScanReport` | Records findings and admission decisions |
| `RuntimeMonitor` | Evaluates runtime events |
| `SecretScanner` | Detects common credential patterns |
| `DeploymentGate` | Prevents deployment of non-compliant images |

### 9.2 Important mechanisms

The implementation uses dataclasses to represent structured security information.

Enums prevent arbitrary severity and decision values from being introduced into the domain model.

The scanner separates finding identification from admission evaluation.

The deployment gate records scan results and raises a security exception when an image is not permitted.

Audit output is written through a temporary file followed by replacement to reduce the risk of partially written reports.

### 9.3 Execution

Run using Python 3.10 or later.

The program requires no external packages.

The demonstration evaluates:

- A compliant minimal image.
- A root-running image.
- A privileged image.
- An image with exposed secrets.
- An image with an unverified signature.
- Runtime shell execution.
- Unexpected secret access.

Assertions validate the principal admission and runtime decisions.

## 10. JavaScript Implementation

**File:** `container_security.js`

The JavaScript implementation focuses on asynchronous policy evaluation and event-driven runtime monitoring.

### 10.1 Main components

| Component | Responsibility |
|---|---|
| `ImageManifest` | Validates and freezes image metadata |
| `SecurityPolicy` | Maintains immutable policy configuration |
| `VulnerabilityScanner` | Performs asynchronous vulnerability evaluation |
| `RuntimeSecurityMonitor` | Emits security events |
| `SecretDetector` | Detects credential exposure patterns |
| `AdmissionController` | Applies deployment admission decisions |

### 10.2 Event-driven architecture

The runtime monitor extends Node.js `EventEmitter`.

When an event is observed:

1. The event is validated.
2. The process identity is extracted.
3. The runtime policy is evaluated.
4. The decision is recorded.
5. A security event is emitted.

This separates event collection from downstream event handling.

The scanner uses `Promise.all()` to evaluate independent vulnerability records concurrently.

The implementation does not assume that concurrent checks replace external vulnerability intelligence or cryptographic verification.

### 10.3 Execution

Run using Node.js 18 or later.

Command:

`node container_security.js`

No third-party npm packages are required.

## 11. C++17 Implementation

**File:** `container_security.cpp`

The C++ implementation uses a strongly typed governance engine.

### 11.1 Main components

| Component | Responsibility |
|---|---|
| `Vulnerability` | Represents CVE information |
| `ContainerImage` | Models image configuration |
| `SecurityPolicy` | Defines governance constraints |
| `ImageScanner` | Evaluates image compliance |
| `RuntimeSecurityEngine` | Evaluates runtime events |
| `SecretDetector` | Identifies suspicious credential patterns |
| `AdmissionController` | Enforces deployment decisions |

### 11.2 Engineering decisions

The implementation uses:

- `enum class` for strongly typed security states.
- `std::vector` for vulnerability and event collections.
- `std::map` for severity aggregation.
- `std::set` for blocked process identities.
- `std::optional` for potentially unavailable fixed versions.
- `std::regex` for format and secret detection.
- Exceptions for invalid configurations and rejected deployments.

The image scanner uses a linear traversal of vulnerability findings.

For an image with \(n\) vulnerability records, the primary evaluation complexity is:

\[
O(n)
\]

Additional policy checks use a fixed number of image attributes and thresholds.

The runtime process lookup uses a set, providing logarithmic lookup complexity.

### 11.3 Execution

Compile using a C++17-compatible compiler:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic container_security.cpp -o container_security`

Run:

`./container_security`

The implementation uses only the C++ standard library.

## 12. Java 17 Implementation

**File:** `ContainerSecurity.java`

The Java implementation models container security as an enterprise domain with explicit policy and service boundaries.

### 12.1 Main components

| Component | Responsibility |
|---|---|
| `Vulnerability` record | Immutable CVE information |
| `ContainerImage` | Image metadata and lifecycle state |
| `SecurityPolicy` record | Immutable policy configuration |
| `Finding` record | Individual security finding |
| `ScanReport` record | Immutable scan output |
| `ImageScanner` | Security assessment service |
| `RuntimePolicy` | Runtime enforcement rules |
| `RuntimeMonitor` | Event history and statistics |
| `SecretScanner` | Secret-pattern detection |
| `AdmissionService` | Deployment admission and audit history |

### 12.2 Enterprise domain design

The implementation separates:

- Image registration.
- Security scanning.
- Policy evaluation.
- Runtime event processing.
- Deployment authorization.

Image lifecycle states are represented through `ImageState`.

A successful scan can approve an image. A mandatory violation blocks it. Findings that require additional assessment produce a scanned state.

The admission service uses synchronization around the admission operation to protect its shared audit and deployment state within a single application instance.

This is not a substitute for distributed locking or transactional persistence in a multi-instance production deployment.

### 12.3 Execution

Compile:

`javac --release 17 ContainerSecurity.java`

Run:

`java ContainerSecurity`

No third-party dependencies are required.

## 13. PostgreSQL Implementation

**File:** `container_security.sql`

The PostgreSQL implementation provides a relational security governance model.

It separates the inventory of container artifacts from vulnerability intelligence, individual findings, scans, policy evaluations and deployment records.

### 13.1 Database relationships

Repositories
→ Container Images
→ Image Packages
→ Vulnerabilities
→ Image Vulnerability Findings

Container Images
→ Image Scans
→ Policy Evaluations
→ Deployment Records

Container Images
→ Image Secrets
→ Image Provenance
→ Runtime Events

Security Policies
→ Policy Evaluations

### 13.2 Important tables

| Table | Purpose |
|---|---|
| `repositories` | Registry and ownership information |
| `container_images` | Image identity and configuration |
| `image_packages` | Installed package inventory |
| `vulnerabilities` | CVE reference data |
| `image_vulnerabilities` | Image-specific vulnerability findings |
| `image_scans` | Scan execution and results |
| `image_secrets` | Potential exposed credentials |
| `image_provenance` | Publisher and build evidence |
| `security_policies` | Environment-specific security requirements |
| `policy_evaluations` | Historical admission decisions |
| `runtime_events` | Runtime security observations |
| `deployments` | Deployment authorization and outcome |

### 13.3 Referential integrity

Primary keys uniquely identify records.

Foreign keys maintain relationships between repositories, images, packages and vulnerability records.

Check constraints enforce valid:

- Image digests.
- Severity values.
- CVE identifiers.
- Package versions.
- Image sizes.
- User IDs.
- Scan counts.
- Lifecycle-related timestamps.

Unique constraints prevent duplicate image digests within a repository and duplicate vulnerability associations for the same package and image.

### 13.4 Database functions and procedures

`evaluate_image()` calculates deployment eligibility from image attributes, vulnerability counts and an active security policy.

`complete_image_scan()` performs scan completion and persists the resulting policy decision.

The procedure locks the scan row while processing it, helping prevent concurrent completion of the same scan.

### 13.5 Triggers

Three triggers provide additional integrity controls.

| Trigger | Enforcement |
|---|---|
| `trg_image_state_transition` | Prevents invalid lifecycle transitions |
| `trg_scan_lifecycle` | Updates image lifecycle after completed scans |
| `trg_deployment_admission` | Rejects deployment approval for non-approved images |

Database triggers enforce local data integrity. They do not replace authorization checks in the deployment platform.

### 13.6 Views

`image_security_posture` presents image-level security information.

`runtime_security_report` aggregates runtime observations by image, container and event category.

These views support security dashboards and reporting without requiring repeated reconstruction of the underlying joins.

### 13.7 Indexing

Indexes support frequently used retrieval patterns:

- Repository and image history.
- Image lifecycle.
- Image digest.
- Package lookup.
- CVE severity.
- Vulnerability associations.
- Scan history.
- Unresolved secret findings.
- Runtime event history.
- Deployment rejections.

Partial indexes reduce index size for selected operational queries, such as unresolved secrets and denied runtime events.

GIN indexing supports searches involving JSONB runtime event details.

### 13.8 Execution

Run the SQL script against PostgreSQL 15 or later.

The script creates a dedicated schema named `container_security`.

The sample data demonstrates compliant and non-compliant images, vulnerability associations, scan completion, policy evaluation and deployment admission.

The SQL script is designed for an isolated learning database. Re-executing it against an existing populated schema is not an idempotent migration.

## 14. Container Security CI/CD Workflow

Container security should be integrated into the continuous integration and continuous deployment pipeline.

### 14.1 Build-time controls

The build process should:

- Use trusted base images.
- Pin dependencies where appropriate.
- Avoid embedding credentials.
- Use multi-stage builds.
- Minimize installed packages.
- Generate image metadata.
- Produce provenance evidence.

### 14.2 Pre-deployment controls

Before deployment:

1. Generate the image digest.
2. Scan the exact image.
3. Evaluate CVE findings.
4. Validate package versions.
5. Check for embedded secrets.
6. Verify image signature.
7. Verify provenance.
8. Evaluate deployment policy.
9. Record the admission decision.

### 14.3 Runtime controls

After deployment:

- Restrict privileges.
- Enforce non-root execution.
- Apply resource limits.
- Restrict network communication.
- Monitor unexpected processes.
- Detect unauthorized filesystem writes.
- Monitor credential access.
- Record security events.
- Reassess images when new vulnerabilities are published.

### 14.4 Integrated workflow

Source code
    |
    v
Build pipeline
    |
    v
Minimal image construction
    |
    v
Package and dependency inventory
    |
    v
Vulnerability and secret scanning
    |
    v
Image signature and provenance
    |
    v
Policy evaluation
    |
    +---- DENY ------> Reject deployment
    |
    +---- REVIEW ----> Manual security assessment
    |
    +---- ALLOW -----> Deployment admission
                           |
                           v
                    Runtime protection
                           |
                           v
                    Security monitoring
                           |
                           v
                    Remediation and rebuild

## 15. Security Controls and Failure Scenarios

| Failure scenario | Security consequence | Required control |
|---|---|---|
| Vulnerable base image | Known exploitable components | Image scanning and base-image updates |
| Excessive image packages | Increased attack surface | Minimal images |
| Root execution | Increased impact of compromise | Non-root execution |
| Privileged container | Increased host exposure | Capability restriction |
| Unverified image signature | Untrusted image origin | Signature verification |
| Missing provenance | Unknown build origin | Build attestations |
| Embedded password | Credential exposure | Secret scanning and rotation |
| Mutable image tag | Image substitution risk | Digest-based deployment |
| Shell in production image | Additional execution capability | Minimal runtime images |
| Unexpected process | Potential compromise | Runtime monitoring |
| Unauthorized file write | Filesystem tampering | Read-only filesystem |
| Unrestricted outbound access | Potential data exfiltration | Network restrictions |
| New CVE after deployment | Previously approved image becomes vulnerable | Continuous vulnerability reassessment |

## 16. Limitations of the Implementations

The five files provide executable security-policy simulations and a relational governance model. They are not complete production container security platforms.

The following distinctions are important.

| Implemented capability | Production requirement not implemented |
|---|---|
| CVE record evaluation | Live vulnerability database integration |
| Package inventory | Full OCI image-layer extraction |
| Signature verification flag | Cryptographic signature verification |
| Provenance verification flag | Attestation and trust-chain validation |
| Secret-pattern detection | Comprehensive secret discovery and provider validation |
| Runtime event evaluation | Kernel-level process and syscall monitoring |
| Deployment admission | Kubernetes admission webhook integration |
| Audit data structures | Distributed, tamper-resistant audit storage |
| Image policy evaluation | Centralized policy distribution and versioning |
| Deployment history | Distributed transactional deployment coordination |

The secret scanners are pattern-based. They can produce false positives and miss secrets that do not match the configured expressions.

The runtime engines demonstrate deterministic rule evaluation. They do not provide kernel instrumentation, behavioral baselines or advanced threat detection.

The SQL implementation stores security decisions and supports admission evaluation. Production systems should also enforce database authorization, audit access, retention and separation of duties.

## 17. Performance and Operational Considerations

### Image scanning

Scanning cost depends on:

- Number of image layers.
- Number of installed packages.
- Size of dependency inventories.
- Vulnerability database size.
- Scanner implementation.
- Network access to vulnerability intelligence.

Image-layer and vulnerability database caching can reduce repeated scanning overhead.

### Minimal images

Smaller images generally reduce transfer and storage requirements.

They also require testing to ensure that all application dependencies, certificates, locale files and runtime libraries are available.

### Runtime monitoring

Runtime event volume can become substantial in high-throughput environments.

Production implementations should use:

- Event filtering.
- Bounded queues.
- Sampling where appropriate.
- Structured event formats.
- Appropriate retention.
- Centralized alerting.
- Rate limiting.

### Database performance

The relational model uses indexes for frequently queried foreign keys and operational filtering columns.

Large runtime-event and scan-history tables may require time-based partitioning and archival.

### Security policy management

Security policies should be version-controlled and changes should be auditable.

A policy change must not silently alter the interpretation of an earlier scan result. Historical evaluations should retain the policy version or a reference to the exact policy configuration used.

## 18. Security Engineering Distinctions

The following concepts represent different controls and should not be treated as interchangeable.

| Concept | What it establishes |
|---|---|
| Image scanning | Identifies known image vulnerabilities and configuration issues |
| Minimal image design | Reduces unnecessary components |
| Vulnerability remediation | Removes or mitigates identified weaknesses |
| Image signing | Establishes cryptographic integrity and signer evidence |
| Provenance | Records the origin and construction history |
| Secret scanning | Identifies potentially exposed credentials |
| Secret management | Controls credential storage, delivery and rotation |
| Runtime security | Observes and restricts active container behavior |
| Admission control | Determines whether a workload can be deployed |
| Continuous monitoring | Detects security changes and violations after deployment |

A secure container deployment requires these controls to work together.

A minimal image can contain a critical vulnerability. A signed image can contain malicious software. A vulnerability-free image can expose embedded credentials. An approved image can still be deployed with unsafe runtime permissions.

Security assessment must therefore evaluate the image, its provenance, deployment configuration and runtime behavior as separate but connected dimensions.
