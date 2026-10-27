## Scope

This project models relational database architecture through executable implementations covering schemas, tables, keys, normalization, indexes, constraints, transactions, and ACID-oriented state management.

The examples also use a repository-development domain to provide realistic relationships between structured data:

`Repository → Branch → Commit → Pull Request → Review → Conversation → Status Check → Branch Protection → Merge Eligibility`

The repository workflow is used as application data. The central technical subject remains relational database architecture.

## Architectural Model

The implementation separates data according to entity ownership and dependency:

    User
     ├── Repository
     │    └── Branch
     │         └── Commit
     │
     └── Review

    Repository
     └── Pull Request
          ├── Commits
          ├── Reviews
          │    └── Review Comments
          ├── Conversations
          └── Status Checks

    Branch
     └── Branch Protection Policy
          └── Approval Requirements

    Pull Request + Reviews + Checks + Policy
                     │
                     ▼
              Merge Eligibility
                     │
                     ▼
                   Merge

This separation prevents unrelated attributes from being stored repeatedly and makes dependencies explicit.

## Schemas and Tables

A database schema provides a namespace for related database objects. The PostgreSQL implementation creates the `relational_architecture` schema and places the domain tables, functions, triggers, and view inside it.

The principal relations are:

| Relation | Purpose |
|---|---|
| `app_user` | Stores user identity attributes |
| `repository` | Stores repository ownership and visibility |
| `branch` | Stores repository branches and protection state |
| `commit_record` | Stores immutable commit metadata |
| `pull_request` | Stores proposed changes between branches |
| `pull_request_commit` | Associates commits with pull requests |
| `review` | Stores reviewer decisions |
| `review_comment` | Stores detailed review discussion |
| `conversation` | Tracks discussion resolution |
| `status_check` | Stores automated validation state |
| `branch_protection_policy` | Stores repository enforcement rules |
| `approval_requirement` | Stores role-specific approval requirements |
| `merge_record` | Stores successful merges |
| `audit_event` | Stores operational audit information |
| `account` | Demonstrates transactional financial state |

Primary keys identify rows. Foreign keys enforce relationships between entities.

For example, a branch references its repository, while a pull request references its source and target branches. A review references both the pull request and reviewer.

## Normalization

The schema follows normalized relational design principles.

User information is stored once in `app_user`. Repositories reference users rather than duplicating usernames and email addresses. Branches reference repositories rather than storing repository attributes repeatedly.

The structure can be viewed as:

    app_user
       │
       ├── repository
       │       │
       │       └── branch
       │              │
       │              └── pull_request
       │
       └── review

The `pull_request_commit` relation resolves the many-to-many relationship between pull requests and commits.

Normalization reduces common anomalies:

- Update anomalies are reduced because a user's attributes have a single authoritative row.
- Insertion anomalies are reduced because users can exist independently of repositories.
- Deletion anomalies are reduced because removing a repository does not require duplicative user data to be removed.
- Referential integrity is enforced through foreign keys.

Normalization does not mean every possible relation must be split into the maximum number of tables. Decomposition should preserve useful dependencies while keeping queries and constraints practical.

## Keys and Constraints

The PostgreSQL model uses several forms of integrity enforcement.

### Primary Keys

Every major entity has a primary key. PostgreSQL identity columns generate numeric identifiers without requiring application-side ID allocation.

### Foreign Keys

Foreign keys enforce valid relationships.

Examples include:

`repository.owner_id → app_user.user_id`

`branch.repository_id → repository.repository_id`

`review.pull_request_id → pull_request.pull_request_id`

`branch_protection_policy.branch_id → branch.branch_id`

### Unique Constraints

The schema prevents duplicate logical values where appropriate.

The `app_user` table has unique indexes on case-insensitive usernames and email addresses.

Repositories are unique for a particular owner and repository name.

Branches are unique within a repository.

### Check Constraints

Check constraints enforce local validity rules such as:

- non-negative account balances
- positive approval requirements
- valid repository visibility values
- valid pull request states
- valid review states
- valid status-check states
- non-empty required text

Database constraints are preferable to application-only validation when a rule must remain true regardless of which application writes the data.

## Indexes

Indexes are created for access patterns rather than for every column.

Examples include:

| Index | Query purpose |
|---|---|
| `app_user_username_uq` | Case-insensitive username uniqueness |
| `app_user_email_uq` | Case-insensitive email uniqueness |
| `branch_repository_idx` | Branch lookup by repository |
| `commit_repository_time_idx` | Recent commits for a repository |
| `pull_request_repository_state_idx` | Pull request filtering by repository and state |
| `review_pr_reviewer_idx` | Reviewer history for a pull request |
| `conversation_pr_state_idx` | Conversation state lookup |
| `status_check_pr_status_idx` | Status-check filtering |
| `account_owner_idx` | Account lookup by owner |

Indexes improve read performance but consume storage and add write-maintenance cost. The implementation therefore indexes columns used by relationship traversal, filtering, uniqueness, and reporting rather than indiscriminately indexing every field.

## Transactions

A transaction groups related changes into one logical unit.

The Python, JavaScript, C++17, and Java 17 implementations model transaction staging explicitly. Changes are made against a temporary representation and become persistent only after validation succeeds.

The PostgreSQL implementation uses actual transactions:

`BEGIN → SELECT ... FOR UPDATE → UPDATE → INSERT audit record → COMMIT`

The transfer operation updates both accounts as one unit. Row locks prevent conflicting transactions from modifying the same account rows concurrently during the critical operation.

A failed operation can instead use `ROLLBACK`, leaving persistent state unchanged.

## ACID Principles

### Atomicity

A transaction is treated as one unit.

For an account transfer, both the debit and credit must succeed together. A failure must not leave only one side of the transfer applied.

### Consistency

Constraints preserve valid database states.

Examples include:

- foreign-key relationships
- unique usernames
- non-negative balances
- valid status values
- valid approval counts

Application-level validation complements these rules, but critical invariants are represented at the database boundary where practical.

### Isolation

Concurrent operations must not incorrectly overwrite one another.

The in-memory implementations use version numbers for optimistic concurrency detection.

The PostgreSQL transaction uses `FOR UPDATE` to lock account rows during the transfer.

Different isolation strategies involve different trade-offs between concurrency, locking, throughput, and anomaly prevention.

### Durability

After a successful PostgreSQL `COMMIT`, the transaction is considered committed database state rather than temporary application state.

The application examples model commit boundaries explicitly. The PostgreSQL implementation provides the actual transactional persistence mechanism.

## Python Implementation

The Python file builds an in-memory relational-style store with:

- `dataclass` domain records
- dictionaries representing indexed entity collections
- validation exceptions
- normalized users and accounts
- transaction snapshots
- optimistic version checking
- rollback behavior
- audit records
- file-based audit export
- assertions for invariants

The `Transaction` class stages account changes before committing them.

The balance conservation assertion verifies that a transfer does not create or destroy account value.

The implementation intentionally uses only the Python standard library.

## JavaScript Implementation

The JavaScript file models the database using `Map` collections and an event-driven architecture.

`RelationalStore` owns persistent application state while `Transaction` operates on staged account copies.

`EventEmitter` exposes database events for user creation and audit activity.

The implementation also uses asynchronous Node.js file handling to persist the generated audit log.

JavaScript-specific concerns include:

- explicit safe-integer validation
- `Map` for keyed entity access
- events for operational activity
- asynchronous file output
- Promise-based error propagation
- immutable transaction-state constants

The implementation is executable with a Node.js runtime and does not require npm packages.

## C++17 Implementation

The C++ program treats the architecture as a typed repository and transaction engine.

It uses:

- `struct` for domain records
- classes for database and transaction boundaries
- `enum class` for transaction state
- STL unordered maps
- exception-based validation
- `std::int64_t` for monetary values
- version numbers for optimistic concurrency

The C++ design emphasizes explicit ownership and typed state transitions.

The transaction engine checks versions before applying staged changes. This avoids silently replacing a newer account state with an older transaction snapshot.

The program also evaluates a separate merge-eligibility rule using required checks, approvals, and unresolved conversations. That rule is intentionally separate from the database transaction model.

## Java 17 Implementation

The Java implementation uses enterprise-oriented domain modeling.

The model includes:

- records for immutable domain values
- enums for explicit states
- collections for repository state
- a transaction service
- a merge eligibility service
- policy objects
- stream-based approval evaluation
- validation through constructors and service methods

`TransactionService` stages balances and records the original account versions.

`MergeEligibilityService` evaluates policy requirements independently of transaction persistence.

This separation illustrates a useful architectural distinction between domain policy evaluation and state persistence.

## PostgreSQL Implementation

The PostgreSQL script provides the most complete relational representation.

It includes:

- schema creation
- normalized tables
- primary keys
- foreign keys
- unique constraints
- check constraints
- partial indexes
- views
- CTEs
- PL/pgSQL functions
- triggers
- transactional operations
- sample data
- reporting queries
- merge-eligibility evaluation

The `merge_eligibility` view combines independent state sources:

    Pull Request
         │
         ├── Active approvals
         ├── Status checks
         ├── Unresolved conversations
         └── Target-branch policy
                  │
                  ▼
           Merge eligibility

This prevents a single review record from being treated as equivalent to complete merge authorization.

## Review, Approval, and Enforcement Separation

The repository example distinguishes four related concepts.

### Pull Requests

A pull request represents a proposed change between a source branch and target branch.

Its data includes:

- source branch
- target branch
- author
- title
- state
- draft state
- associated commits

The pull request is the workflow container for the proposed change.

### Code Review

Reviews evaluate the proposed change.

A review can be:

- approved
- changes requested
- commented

Review comments provide more detailed discussion and can track resolution independently.

A review therefore represents an evaluation event, not repository-level enforcement.

### Approvals

Approvals are specific review decisions that contribute to an approval requirement.

The schema stores approval state separately from policy requirements.

This distinction permits policies such as requiring two active approvals even when a pull request contains several comments or changes-requested reviews.

Dismissed approvals are excluded from active approval counts.

### Branch Protection

Branch protection defines repository-level enforcement.

The model can require:

- minimum approvals
- passing status checks
- resolved conversations
- no direct pushes
- no force pushes
- no branch deletion
- linear history

Branch protection therefore determines which conditions must hold before a change can enter a protected branch.

The four concepts interact without being interchangeable:

    Pull Request
        │
        ▼
    Code Review
        │
        ▼
    Approval Decisions
        │
        ├───────────────┐
        ▼               ▼
    Status Checks   Conversations
        │               │
        └───────┬───────┘
                ▼
        Branch Protection
                │
                ▼
        Merge Eligibility
                │
                ▼
              Merge

## Failure Conditions

The implementations explicitly reject several invalid states.

Examples include:

- duplicate usernames
- missing foreign-key owners
- negative balances
- zero or negative transfer amounts
- transfers to the same account
- insufficient funds
- transactions used after completion
- concurrent version changes
- failed status checks
- unresolved protected-branch conversations
- insufficient approvals
- invalid pull request states

These failures are represented as explicit exceptions or database errors rather than silently ignored.

## Performance Considerations

Normalized data can require joins because information is intentionally separated.

Indexes reduce the cost of common relationship and filtering operations, but indexes also increase write overhead.

The PostgreSQL implementation uses composite indexes where multiple predicates commonly occur together.

The in-memory implementations use dictionaries or maps for direct identifier lookup. Their transaction snapshots copy account state, which is simple and predictable but becomes expensive as the number of staged rows increases.

A production implementation would normally rely on the database engine's transaction manager, locking mechanisms, query planner, buffer management, logging, and durable storage rather than copying an entire dataset into application memory.

## Security Considerations

Database security should not depend exclusively on application validation.

Relevant controls include:

- least-privilege database roles
- parameterized SQL
- foreign-key enforcement
- server-side constraints
- controlled schema permissions
- transaction boundaries
- audit logging
- restricted direct modification of protected data
- careful handling of concurrent updates

The PostgreSQL design keeps important integrity rules inside the database so that multiple clients cannot bypass them simply by implementing different application logic.

Sensitive credentials are deliberately absent from the sample data.

## Practical Data Flow

A typical repository change moves through these data states:

    User creates repository
            │
            ▼
    Branch is created
            │
            ▼
    Commits are recorded
            │
            ▼
    Pull Request references branches and commits
            │
            ▼
    Review records evaluate the change
            │
            ├── Comments
            └── Approval decisions
            │
            ▼
    Status checks record automated results
            │
            ▼
    Branch policy supplies required conditions
            │
            ▼
    Eligibility view evaluates all conditions
            │
            ▼
    Merge record persists successful merge

Each stage has its own relation and integrity rules.

## Limitations

The Python, JavaScript, C++17, and Java 17 programs are architectural simulations rather than database engines. Their transaction behavior demonstrates concepts such as staging, rollback, and optimistic concurrency but does not reproduce every property of PostgreSQL transaction processing.

The PostgreSQL schema is deliberately focused on relational architecture and repository governance. It does not attempt to implement a complete source-control platform.

The merge-eligibility model is intentionally simplified. Production governance can include reviewer groups, ownership rules, stale-approval invalidation, merge queues, signed commits, deployment environments, administrator bypass rules, and more complex permission systems.

The examples use simple identifiers and sample data for deterministic execution.

## Educational Distinctions

The central distinctions implemented by the project are:

| Concept | Primary responsibility |
|---|---|
| Schema | Organizes database objects |
| Table | Stores a relation of structured records |
| Primary key | Identifies a row |
| Foreign key | Enforces a relationship |
| Unique constraint | Prevents duplicate logical values |
| Check constraint | Enforces row-level validity |
| Index | Improves selected access paths |
| Normalization | Reduces redundant and anomalous data structures |
| Transaction | Groups changes into one logical unit |
| Atomicity | Prevents partial transaction completion |
| Consistency | Preserves defined database invariants |
| Isolation | Controls interaction between concurrent transactions |
| Durability | Preserves committed state |
| Pull Request | Represents a proposed repository change |
| Code Review | Evaluates the proposed change |
| Approval | Records an explicit review decision |
| Branch Protection | Enforces repository-level merge conditions |

The implementations keep these responsibilities separate while showing how they cooperate in a realistic relational application.
