# Object Storage: Data Model, Version History, Lifecycle, and Access Governance

## Technical scope

Object storage holds data as individually addressable objects inside buckets. It is designed for documents, images, telemetry exports, application artifacts, backups, logs, and other data accessed through object-oriented operations rather than conventional filesystem directory operations.

An object storage service generally separates the following concerns:

- **Bucket management** establishes a namespace, ownership boundary, default settings, and a place to configure access and lifecycle controls.
- **Object management** handles keys, payload bytes, content metadata, integrity information, and object-specific operations.
- **Versioning** preserves historical representations when an object is replaced or deleted.
- **Lifecycle management** applies age-based transitions and expiration policies to reduce storage costs and manage retention.
- **Access policies** determine which principals can perform which actions against which resources under specified conditions.

These mechanisms interact, but they are not interchangeable. Versioning preserves recoverable history; lifecycle rules determine when stored versions become candidates for transition or deletion; access policies determine whether an operation is permitted. A lifecycle rule is not an authorization policy, and versioning is not a backup strategy by itself.

The implementations in this collection use an in-memory service model, an event-driven JavaScript service, a C++ governance engine, a Java enterprise domain model, and a PostgreSQL relational schema. They share the same domain while exploring different engineering concerns.

## Object identity and key design

A bucket provides the namespace in which object keys are interpreted. A key such as `reports/monthly.json` identifies a logical object, not a physical disk path. Prefixes such as `reports/` are useful for grouping objects, filtering listings, applying policies, and assigning lifecycle rules.

The slash character in a key does not imply that the storage system must maintain filesystem directories. It is part of the key's naming convention.

A versioned object has two related identifiers:

- The logical key identifies the resource being addressed by ordinary reads and writes.
- The version ID identifies a particular stored representation of that resource.

For example, `reports/monthly.json` might have versions `v-2026-09-01` and `v-2026-09-02`. A read without a version ID selects the current logical representation. A historical read explicitly selects a version.

The Python, JavaScript, C++, and Java programs validate object keys before accepting them. They reject empty keys, absolute-style leading slashes, parent-directory segments, and invalid lengths. Such validation prevents confusing application assumptions about paths with the storage service's actual key semantics.

Bucket names have stricter naming rules than object keys because they frequently participate in service-level namespaces, URLs, and resource identifiers.

## Payloads and metadata

The payload contains the object's bytes. Metadata describes the payload or supplies application-specific attributes.

System metadata in these implementations includes content type, content length, creation or modification time, a digest, and an ETag-like value. User metadata includes fields such as `department`, `classification`, and `revision`.

Content type controls how downstream consumers interpret bytes. Content length supports transfer validation. A cryptographic digest helps detect unintended content changes. User metadata supports filtering, classification, ownership context, and downstream processing.

Metadata must be validated independently from the payload. A correct payload with an incorrect content length is still an inconsistent object record. The SQL implementation enforces equality between `content_length` and the byte length of `payload` through both a check constraint and a trigger.

The Java implementation stores immutable metadata records and defensively copies user metadata. Its object version also clones payload arrays when constructed and retrieved, preventing callers from changing stored bytes through a shared mutable array reference.

The JavaScript implementation converts string payloads into Node.js buffers and normalizes user metadata into a frozen object. This makes byte length and digest calculation explicit and avoids treating JavaScript character counts as equivalent to UTF-8 byte counts.

The Python implementation calculates SHA-256 and a representative ETag. Its comments distinguish the simulator's ETag convention from real multipart-upload behavior. In actual cloud services, an ETag must not automatically be assumed to be a cryptographic checksum.

## Versioning and deletion semantics

Versioning changes the meaning of an overwrite or delete operation.

With versioning enabled, writing to an existing key creates a new version. The previous current version becomes noncurrent. A normal delete creates a delete marker rather than necessarily erasing historical payloads.

A delete marker is a logical state change, not an object payload. It makes the key appear absent to an ordinary read while allowing authorized callers to retrieve an older version by ID. Permanently deleting a version is a separate operation that targets a specific version identifier.

Versioning disabled typically replaces the current representation instead of retaining a complete history. Suspended versioning introduces additional rules for null versions; provider-specific behavior should be consulted before implementing an exact cloud-compatible state machine.

The Python, JavaScript, C++, and Java programs represent version histories as ordered collections associated with a key. The most recent entry represents the current state. Explicit version lookup searches the history for a matching ID.

The SQL model stores `object_versions` as separate relational rows. A unique constraint on `(object_id, version_id)` prevents duplicate version identifiers within a logical object. A partial unique index constrains current non-delete-marker payloads, while the `current_object_inventory` view hides keys whose latest entry is a delete marker.

This distinction matters operationally. A delete marker can make a key disappear from an ordinary listing without eliminating the storage consumed by prior versions. Version-aware inventory and noncurrent-version cleanup are therefore necessary for accurate retention and cost management.

## Conditional writes and integrity

A concurrent application can read an object, perform a calculation, and then attempt to replace the object after another application has already updated it. Blindly accepting the second write can overwrite newer information.

Conditional writes reduce this risk. The Python, JavaScript, and Java implementations accept an expected ETag or digest and reject a write when the current representation no longer matches the expected value.

This is an optimistic concurrency mechanism. It is useful for configuration files, deployment manifests, generated reports, and records updated by multiple services.

The payload digest serves a different purpose. A conditional token compares the expected current state, while SHA-256 verifies that the retrieved payload matches its recorded digest. Production services should calculate and verify integrity values at a trusted boundary.

The SQL script demonstrates consistency constraints, but the sample digest values are illustrative. It deliberately does not claim that the database validates SHA-256 merely because a column contains 64 hexadecimal characters. A production design can calculate the digest in a trusted application or use an appropriate database extension.

## Access policies and authorization

An access policy associates an effect with actions, resources, principals, and optional conditions.

The model distinguishes these elements:

| Element | Meaning in the storage model |
|---|---|
| Principal | An authenticated identity or role making a request |
| Action | An operation such as `object:Get`, `object:Put`, or `object:DeleteVersion` |
| Resource | A bucket or a key-specific resource identifier |
| Effect | `Allow` or `Deny` |
| Condition | A required request attribute, such as a transport-security indicator |

The example policy allows a report-writing role to write report objects when the request context satisfies a transport condition. A separate auditor role can read report history. An explicit deny prevents deletion under a protected legal-record prefix.

Authorization follows three important rules in the teaching model:

- Unauthenticated principals are rejected.
- A matching explicit deny takes precedence over matching allow statements.
- A request without a matching allow is denied.

The Python implementation represents policy statements with immutable data classes and checks principal names, roles, actions, resources, and conditions. The JavaScript implementation uses `EventEmitter` to publish authorization and storage events. The C++ implementation uses typed actions and effects, while the Java program uses enums, records, collections, and a dedicated authorization service.

The PostgreSQL function `evaluate_access` implements comparable policy matching over normalized relational tables. It uses joins and `EXISTS` predicates to determine whether matching deny or allow statements exist.

These are simplified policy engines. They do not implement every feature of a cloud provider's IAM language, organization-level restrictions, session policies, service control policies, object ownership settings, encryption-key policies, or network boundary controls. The production authorization model must include every applicable policy layer.

## Lifecycle management

Lifecycle management automates storage transitions and expiration using object age, key prefixes, and version state.

A lifecycle rule can define a storage-class transition after a specified age, expiration of current objects, expiration of noncurrent versions, or cleanup of incomplete uploads.

A report archive policy might transition old exports to a less frequently accessed storage class after 30 days and remove noncurrent versions after a longer retention interval. Temporary exports might have a shorter expiration interval.

Lifecycle actions require careful interpretation:

- A transition changes the storage class, not the logical object key.
- An expiration rule does not necessarily mean that every historical version is immediately erased.
- A versioned current-object expiration can create a delete marker.
- Noncurrent-version expiration targets older versions rather than the current representation.
- Incomplete multipart uploads require separate tracking because they may not appear as ordinary completed objects.

The Python and JavaScript implementations execute lifecycle rules in memory and return counts of transitions, expirations, and noncurrent deletions. The C++ engine evaluates lifecycle rules over a repository of version histories. The Java service uses explicit `LifecycleRule` records. The SQL script stores lifecycle configuration in `lifecycle_rules` and contains a query that identifies objects whose age satisfies a configured rule.

The SQL lifecycle query is intentionally an evaluation query, not an automatic deletion job. A real lifecycle worker must handle concurrent writes, policy changes, retention holds, retries, and idempotency. It should also distinguish rule eligibility from successful completion.

Storage-class transitions have provider-specific costs and retrieval characteristics. An archive class may impose minimum storage durations, retrieval charges, restore delays, or restrictions on direct reads. The sample programs simulate these conditions rather than claiming identical behavior across providers.

## Python implementation

The Python file concentrates on a service model with explicit operations and validation.

`ObjectStorage` owns buckets and audit events. Each `Bucket` contains its versioning state, policy statements, lifecycle rules, incomplete-upload records, and per-key histories. `StoredVersion` contains payload bytes, metadata, timestamps, storage class, and retention information.

The service separates authorization from operation execution. `_require` evaluates access before writes, reads, deletes, and listings. The policy evaluator checks explicit denies before allows.

Conditional writes compare the supplied ETag with the current version. Historical retrieval accepts an explicit version ID. Versioned deletion inserts a marker, while version-specific deletion removes a selected version subject to retention checks.

The lifecycle processor calculates age from timestamps and evaluates matching prefix rules. Its demonstration backdates an object within the controlled simulation so that an archive transition can be observed without waiting several weeks.

The program also demonstrates paginated listing, integrity verification, unauthenticated-access rejection, and audit records. It is intentionally in-memory, so a process restart loses its data. Its lock protects individual bucket mutations within one process but does not provide distributed transaction semantics.

## JavaScript implementation

The JavaScript file emphasizes event-driven behavior and the Node.js runtime.

`ObjectStorageService` extends `EventEmitter`. Successful operations, denied requests, and lifecycle execution emit `storage:event` records. The built-in listener appends immutable event snapshots to an audit collection. Other consumers can attach independent listeners for metrics or alerting without changing storage methods.

Buffers represent payload bytes. The service computes content digests, normalizes metadata, and returns defensive buffer copies. Its policy evaluation uses role membership, resource-prefix matching, explicit-deny precedence, and request-context conditions.

The implementation models version-aware reads and deletes, conditional writes, object listing, and lifecycle transitions. It also demonstrates why an event-driven audit mechanism is useful: operational monitoring can be separated from the core operation that mutates object state.

The event emitter itself is synchronous. A production event-processing system must not assume that a local event listener is a durable message queue. Reliable audit delivery requires a persistence mechanism or an outbox-style design so that a successful object write cannot silently lose its associated audit event.

## C++ case study

The C++ program models deployment evidence storage for an engineering organization. Deployment manifests are stored under a release prefix, while compliance evidence has stricter deletion controls.

The architecture separates:

- `Principal`, which describes the caller and its roles.
- `PolicyStatement`, which stores effects, actions, resource prefixes, principals, and conditions.
- `ObjectVersion`, which captures a payload representation and its lifecycle state.
- `Bucket`, which owns policy configuration, version histories, and lifecycle rules.
- `GovernanceEngine`, which applies authorization and executes storage operations.

Typed enums represent actions, versioning states, storage classes, and policy effects. This avoids relying on arbitrary action strings throughout the authorization logic.

The engine validates key structure and metadata consistency, creates versions, retrieves historical records, inserts delete markers, and evaluates lifecycle candidates. It rejects unauthorized access and prevents permanent deletion during an active retention period.

The sample checksum helper uses `std::hash` only as a deterministic illustrative field. It is not cryptographically secure and must not be used as a production integrity mechanism. A real implementation should use a cryptographic digest library or a trusted storage API.

The ordered version collection makes current-state lookup inexpensive, while historical lookup requires searching a key's history. With \(n\) versions for a key, a linear historical lookup takes \(O(n)\) time. A production implementation can index versions by ID while preserving a separate current-version pointer.

The sample is a single-process model. It does not include durable storage, distributed locking, network authentication, concurrent request handling, or crash recovery.

## Java implementation

The Java implementation emphasizes explicit domain types and service-oriented policy enforcement.

Records such as `Principal`, `ObjectMetadata`, `PolicyStatement`, and `LifecycleRule` provide concise value models. Enums define allowed actions, policy effects, storage classes, and versioning states.

The `Bucket` class owns the key-to-version-history mapping and policy configuration. `StorageService` handles bucket lookup, access checks, object creation, retrieval, deletion, and lifecycle processing.

The service validates conditional updates against a recorded digest. It clones payload arrays through the `ObjectVersion` API, uses `MessageDigest` for SHA-256, and returns immutable user metadata.

Authorization is centralized in `authorize` and `require`. This separation makes it possible to test policy decisions independently from the code that stores or retrieves payloads.

The lifecycle implementation distinguishes current versions from noncurrent versions and respects modeled retention timestamps. It remains a simulation: real lifecycle workers need atomic state changes, durable scheduling, idempotent retries, and careful handling of simultaneous writes.

The sample domain types are not a complete production storage SDK. A production service would also require durable repositories, explicit transaction boundaries, access-control integration, operational telemetry, and a clear ownership model for policy changes.

## PostgreSQL data model

The SQL implementation represents object storage as a relational model rather than storing all state in a single JSON document.

`buckets` stores ownership, versioning state, encryption defaults, and bucket identity. `objects` represents logical keys within buckets. `object_versions` stores payload bytes, version IDs, metadata fields, checksums, storage class, delete-marker state, creation time, noncurrent time, and retention information.

`object_metadata` stores user-defined metadata as key-value rows. This avoids requiring a schema change whenever an application introduces a new metadata attribute.

The policy schema is normalized across `bucket_policy_statements`, `policy_actions`, `policy_principals`, `policy_resources`, and `policy_conditions`. These relationships support policy queries without embedding all policy behavior in application-only configuration.

`lifecycle_rules` stores transition and expiration ages, target storage classes, key prefixes, and incomplete-upload cleanup intervals. `incomplete_uploads` records multipart uploads that have not produced completed objects. `storage_audit_events` records decisions and operational outcomes.

Database constraints enforce unique bucket names, unique logical keys within a bucket, unique version identifiers within an object, valid storage-state values, valid metadata keys, nonnegative payload lengths, and consistency between payload bytes and recorded length.

Indexes support version history queries, noncurrent cleanup, prefix-based inventory, lifecycle evaluation, and recent audit lookups. The partial current-payload index provides an additional database-level guard against multiple current non-delete-marker versions.

The `evaluate_access` function evaluates bucket policy statements using principals, roles, actions, resources, and request conditions. The `current_object_inventory` view exposes the logical current inventory while hiding a key whose latest entry is a delete marker.

The transaction example locks the logical object row, marks its prior current version as noncurrent, and inserts a replacement version. This demonstrates why version creation must update related state atomically. A production transaction also needs appropriate authorization, checksum validation, error handling, and a consistent definition of the current version.

The SQL sample requires PostgreSQL features such as identity columns, enums, JSONB, partial indexes, triggers, and PL/pgSQL. It does not require `pgcrypto`, because checksums are supplied by the application. The sample digest values are illustrative and should not be treated as verified content hashes.

## Performance and production boundaries

The in-memory implementations are useful for understanding storage semantics but do not reproduce the scale or durability of a cloud object store.

Large object collections require pagination. The Python listing example uses a continuation key, while the JavaScript listing produces a sorted inventory. Production APIs typically return opaque continuation tokens because a key alone may not represent every pagination state, especially when listings change during traversal.

Version histories grow over time. Historical retrieval and noncurrent cleanup need indexes or dedicated lookup structures when a key has many versions. Lifecycle jobs should process bounded batches rather than scanning every object in one transaction.

Object metadata can become expensive when many tiny objects are stored. Metadata limits, request rates, listing costs, and object-count growth should be considered alongside raw payload capacity.

Lifecycle actions and deletes should be idempotent where possible. A retry must not accidentally delete a newer version created after the original request. Version-specific operations and concurrency preconditions reduce this risk.

Access policies should use least privilege. Broad wildcard permissions are easy to misconfigure, and explicit deny statements must be tested against all intended access paths. Anonymous access, cross-account access, and transport-security requirements need deliberate handling.

Versioning does not guarantee immutable retention. A principal with sufficient permissions may still delete historical versions unless a separate retention or object-lock mechanism prevents it. A production compliance system must distinguish ordinary versioning from legally enforceable retention.

The audit trail should capture identity, action, target resource, decision, timestamp, and a useful reason or request identifier. Sensitive payload contents and credentials should not be copied into audit messages. Durable audit storage, access restrictions, retention, and integrity protection are separate operational requirements.
