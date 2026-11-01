For the topic specified at the end, generate exactly SIX independent deliverables:

1. Complete Python script
2. Complete JavaScript file
3. Complete C++17 program
4. Complete Java 17 program
5. Complete PostgreSQL SQL script
6. Complete Markdown README.md

# STRICT OUTPUT FORMAT

Output exactly six fenced code blocks and nothing else.

The six blocks MUST appear in exactly this order:

1. Python
2. JavaScript
3. C++17
4. Java 17
5. PostgreSQL
6. Markdown README.md

Use exactly these fence types:

- First block: `python`
- Second block: `javascript`
- Third block: `cpp`
- Fourth block: `java`
- Fifth block: `sql`
- Sixth block: `markdown`

IMPORTANT: The examples above describe the required structure. Do not output example placeholders themselves.

There must be:

- Exactly six fenced code blocks.
- Exactly one block per deliverable.
- No text before the first block.
- No text between blocks.
- No text after the sixth block.
- No additional or fragmented blocks.
- No nested triple backticks inside any block.
- No filenames, labels, introductions, explanations, conclusions, or commentary outside the six blocks.

The sixth block is the complete README.md file. ALL Markdown content must remain inside that single final Markdown block.

The README MUST NOT contain any fenced code blocks. Never use triple backticks anywhere inside the README. Use inline code with single backticks, Markdown tables, headings, bullets, paragraphs, and plain-text diagrams where needed.

# GENERAL CONTENT RULES

All six deliverables must be complete, technically accurate, directly relevant, and usable.

If the topic contains multiple categories, keep them technically distinct. Do not repeat the same explanation across categories.

Depth must come from:

- Actual implementations.
- Realistic workflows.
- Algorithms.
- Data structures.
- Validation.
- State management.
- Database operations.
- Security controls.
- Edge cases.
- Failure handling.
- Performance considerations.
- Concrete design decisions.

Do not use:

- Placeholders.
- TODOs.
- Pseudocode.
- Unfinished logic.
- Generic tutorials.
- Unrelated examples.
- Filler.
- Repetitive headings.
- Shallow numbered lists.
- Motivational language.
- Exaggerated claims.
- Meta-commentary.

Do not mention ChatGPT, AI, language models, prompts, generation, or the creation process.

Do not use these phrases:

- "Let's dive in"
- "Welcome to"
- "By the end of this"
- "Furthermore"
- "Moreover"
- "In addition"
- "Overall"

# PYTHON

Create one complete, self-contained Python script that progresses from fundamental to advanced concepts relevant to the topic.

Use Python-specific strengths where appropriate:

- Functions.
- Classes.
- Dictionaries.
- Lists.
- Sets.
- Dataclasses.
- Enums.
- Validation.
- Exceptions.
- File handling.
- APIs or automation where relevant.
- Testing or assertions.
- Standard-library features.

Use executable implementations instead of excessive explanation.

Comments must explain important mechanisms.

Include realistic examples, edge cases, validation, failure conditions, performance considerations, security considerations, debugging information, and production considerations where relevant.

Avoid unnecessary external dependencies.

The script must run as provided.

# JAVASCRIPT

Create one complete, self-contained JavaScript file that complements rather than mechanically translates the Python implementation.

Use JavaScript-specific capabilities where relevant:

- Objects.
- Classes.
- Maps and Sets.
- Asynchronous processing.
- Promises.
- Event-driven behavior.
- Validation.
- Policy evaluation.
- Structured data processing.
- Node.js standard-library functionality where appropriate.

Progress from basic topic-specific behavior into a realistic implementation.

Include meaningful validation, error handling, edge cases, performance considerations, and security considerations where applicable.

Use meaningful names and comments.

Avoid unnecessary npm dependencies.

The file must be executable in an appropriate JavaScript runtime.

# C++17

Create one complete C++17 program as a realistic technical case study specifically related to the topic.

Use a coherent non-trivial scenario rather than isolated syntax examples.

Use appropriate:

- Classes.
- Structs.
- Enums.
- Functions.
- STL containers.
- Algorithms.
- Validation.
- Exception handling.
- Input/output.
- Modular design.

The C++ implementation should provide a substantially different engineering perspective from Python and JavaScript where practical.

Comments must explain important architectural and implementation decisions.

Include applicable:

- Edge cases.
- Constraints.
- Trade-offs.
- Complexity.
- Performance.
- Security considerations.
- Failure conditions.

The program must compile with C++17 or later.

Do not use unnecessary external libraries.

Do not use placeholders or pseudocode.

# JAVA 17

Create one complete Java 17 program using a realistic enterprise-oriented scenario related to the topic.

The implementation must complement the other languages rather than simply translate them.

Use Java-specific features where appropriate:

- Classes.
- Interfaces.
- Enums.
- Records.
- Collections.
- Streams.
- Generics.
- Immutable structures.
- Validation.
- Custom exceptions.
- Domain modeling.
- Explicit state transitions.
- Service classes.
- Policy objects.

Represent domain behavior, policies, workflows, state transitions, and validation explicitly.

Include meaningful:

- Failure states.
- Validation.
- Edge cases.
- Policy conflicts.
- Security considerations.
- Performance implications.
- Design trade-offs.

The program must compile and run using Java 17 or later with no unnecessary third-party dependencies.

Do not use placeholders, TODOs, pseudocode, or generic Java tutorials.

# POSTGRESQL

Create one complete, executable PostgreSQL script representing the topic through a realistic relational model and workflow.

Use topic-specific:

- Schemas where useful.
- Tables.
- Primary keys.
- Foreign keys.
- Unique constraints.
- Check constraints.
- Indexes.
- Views.
- CTEs.
- Functions.
- Procedures where appropriate.
- Triggers.
- Transactions.
- Realistic DDL.
- Realistic DML.

Include sample records covering meaningful states, roles, decisions, policies, valid conditions, and failure cases.

Demonstrate meaningful queries for:

- Retrieval.
- Validation.
- Aggregation.
- Evaluation.
- Reporting.
- Workflow state.
- Eligibility decisions.

Enforce important database-level rules using constraints and triggers where appropriate.

Use indexes only where they provide a clear query-performance benefit.

Demonstrate transactional integrity where relevant.

Use PostgreSQL-specific SQL comments to explain important design decisions.

The script must execute as provided in PostgreSQL.

Do not use placeholders, pseudo-SQL, unfinished definitions, or generic SQL tutorials.

# README.MD

Create one complete, professional README.md explaining the actual technical and educational content implemented in the five source files.

The entire README MUST be contained inside the sixth and final `markdown` block.

The README MUST NOT contain any fenced code blocks or triple backticks.

Use:

- Descriptive headings.
- Precise paragraphs.
- Markdown tables.
- Useful bullet lists.
- Plain-text diagrams.
- Inline code.

Use plain, precise, academic English.

Make every section specific to the topic.

Explain actual:

- Concepts.
- Mechanisms.
- Terminology.
- Workflows.
- Rules.
- Distinctions.
- Implementation decisions.
- Edge cases.
- Limitations.
- Practical implications.

Describe what each implementation actually does rather than merely saying that it demonstrates the topic.

Explain the actual Python, JavaScript, C++17, Java 17, and PostgreSQL mechanisms used.

Do not duplicate source code.

Do not create a generic programming-language tutorial.

Do not include sections titled:

- Summary.
- Next Steps.
- Further Learning.
- Recommendations.
- Resources.
- Conclusion.

Do not recommend books, websites, courses, videos, tools, or unrelated projects.

Do not create a repetitive conclusion.

# TOPIC-SPECIFIC REQUIREMENTS

Treat the following four areas as related but distinct.

## PULL REQUESTS

Cover:

- Pull Request lifecycle and mechanics.
- Source and target branches.
- Changesets and commits.
- Review requests.
- Conversations.
- Status checks.
- Merge behavior and strategies.
- Draft Pull Requests.
- Base-branch synchronization.
- Merge conflicts.
- Reopening Pull Requests.
- Closing Pull Requests.

## CODE REVIEW

Cover:

- Review mechanics.
- Inline comments.
- Review states.
- Review discussions.
- Requested changes.
- Approval behavior.
- Reviewer responsibilities.
- Review quality and scope.
- Review criteria.
- Review workflows.
- Resolving discussions.
- Review-related failure modes.

## APPROVALS

Cover:

- Approval semantics.
- Eligible reviewers.
- Required reviews.
- Approval requirements.
- Stale approvals.
- Dismissed approvals.
- Review policies.
- Reviewer eligibility.
- Effect of approvals on merge eligibility.

## BRANCH PROTECTION

Cover:

- Protected branches.
- Required status checks.
- Required reviews.
- Direct-push restrictions.
- Force-push restrictions.
- Branch deletion restrictions.
- Conversation requirements.
- Linear-history requirements where applicable.
- Merge restrictions.
- Administrator behavior where applicable.
- Bypass mechanisms where applicable.
- Repository governance.

Do NOT treat these four areas as interchangeable.

Explain their relationship clearly:

- A Pull Request provides the workflow for proposing changes.
- Code Review evaluates those changes.
- Approvals represent review decisions.
- Branch Protection enforces repository-level conditions before merging.

Do not repeat Pull Request material under Code Review.

Do not repeat Code Review material under Approvals.

Do not repeat Approval material under Branch Protection.

When concepts overlap, explain the relationship instead of duplicating the same material.

Use realistic repository-development scenarios.

# IMPLEMENTATION PERSPECTIVES

**Python:**

Model and simulate repository workflow behavior.

**JavaScript:**

Provide a complementary interactive, event-driven, or policy-evaluation model.

**C++17:**

Implement a repository governance and merge-eligibility engine evaluating Pull Requests, reviews, approvals, status checks, protected branches, and merge conditions.

**Java 17:**

Implement an enterprise repository-governance model with explicit domain types, review policies, approval rules, state transitions, validation, and merge-eligibility services.

**PostgreSQL:**

Model repositories, branches, Pull Requests, commits, reviewers, reviews, review comments, status checks, branch-protection policies, approval requirements, and merge eligibility.

# REALISTIC DOMAIN RELATIONSHIP

Use a realistic domain model such as:

Repository
→ Branches
→ Commits
→ Pull Requests
→ Reviews
→ Review Comments
→ Conversations
→ Status Checks
→ Branch Protection Policies
→ Approval Requirements
→ Merge Eligibility
→ Merge

Clearly distinguish:

- Proposed changes.
- Branch state.
- Review decisions.
- Approval decisions.
- Automated status checks.
- Repository-level enforcement.
- Final merge eligibility.

# QUALITY STANDARD

The six deliverables must function as deliberately designed technical learning artifacts.

Quality must come from:

- Actual technical implementations.
- Accurate terminology.
- Realistic repository scenarios.
- Executable behavior.
- Meaningful edge cases.
- Clear distinctions between concepts.
- Relationships between mechanisms.
- Concrete design decisions.
- Correct performance considerations.
- Correct security considerations.
- Realistic failure handling.
- Meaningful validation.

Do not increase length through repetitive headings, shallow bullets, generic explanations, duplicated concepts, or artificial complexity.

# FINAL INTERNAL VALIDATION

Before producing the response, verify internally that:

- Exactly six fenced code blocks exist.
- The order is Python, JavaScript, C++17, Java 17, PostgreSQL, Markdown.
- There is no text outside the six blocks.
- Each deliverable is contained in exactly one block.
- The README is entirely inside the sixth block.
- The README contains no triple backticks.
- There are no nested fenced blocks.
- No deliverable is split across multiple blocks.
- All five source files are complete and executable.
- The README accurately describes the five implementations.
- No placeholders or TODOs exist.
- No meta-commentary exists.
- The four topic areas remain technically distinct.
- The output can be copied directly into six separate files.

# TOPIC

Database Scaling | Vertical scaling, horizontal scaling, partitioning, sharding, read replicas
