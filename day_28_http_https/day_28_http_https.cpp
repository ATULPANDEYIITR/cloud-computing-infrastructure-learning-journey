/*
 * HTTP AND HTTPS: C++17 TECHNICAL CASE STUDY
 *
 * Scenario:
 * A secure API gateway for a financial-service application.
 *
 * The program models:
 *   - HTTP request/response messages
 *   - HTTP methods and status codes
 *   - routing
 *   - validation
 *   - authentication/authorization concepts
 *   - idempotency
 *   - rate limiting
 *   - caching with ETags
 *   - security headers
 *   - structured errors
 *   - observability
 *   - request processing
 *
 * The standard library is intentionally used so that the case study remains
 * self-contained. Real production HTTPS transport requires a mature TLS/HTTP
 * implementation such as an appropriately configured platform or networking
 * library. Implementing TLS cryptography from scratch is not appropriate.
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic http_https_case_study.cpp -o http_https_case_study
 */

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;


// ============================================================================
// SECTION 1: BASIC HTTP TYPES
// ============================================================================

enum class HttpMethod {
    GET,
    HEAD,
    POST,
    PUT,
    PATCH,
    DELETE_METHOD,
    OPTIONS
};

string methodToString(HttpMethod method) {
    switch (method) {
        case HttpMethod::GET: return "GET";
        case HttpMethod::HEAD: return "HEAD";
        case HttpMethod::POST: return "POST";
        case HttpMethod::PUT: return "PUT";
        case HttpMethod::PATCH: return "PATCH";
        case HttpMethod::DELETE_METHOD: return "DELETE";
        case HttpMethod::OPTIONS: return "OPTIONS";
    }

    throw invalid_argument("Unknown HTTP method");
}


enum class StatusClass {
    INFORMATIONAL,
    SUCCESS,
    REDIRECTION,
    CLIENT_ERROR,
    SERVER_ERROR,
    UNKNOWN
};


StatusClass classifyStatus(int status) {
    if (status >= 100 && status < 200) return StatusClass::INFORMATIONAL;
    if (status >= 200 && status < 300) return StatusClass::SUCCESS;
    if (status >= 300 && status < 400) return StatusClass::REDIRECTION;
    if (status >= 400 && status < 500) return StatusClass::CLIENT_ERROR;
    if (status >= 500 && status < 600) return StatusClass::SERVER_ERROR;
    return StatusClass::UNKNOWN;
}


string statusReason(int status) {
    static const unordered_map<int, string> reasons = {
        {200, "OK"},
        {201, "Created"},
        {202, "Accepted"},
        {204, "No Content"},
        {301, "Moved Permanently"},
        {302, "Found"},
        {304, "Not Modified"},
        {307, "Temporary Redirect"},
        {308, "Permanent Redirect"},
        {400, "Bad Request"},
        {401, "Unauthorized"},
        {403, "Forbidden"},
        {404, "Not Found"},
        {405, "Method Not Allowed"},
        {409, "Conflict"},
        {422, "Unprocessable Content"},
        {429, "Too Many Requests"},
        {500, "Internal Server Error"},
        {502, "Bad Gateway"},
        {503, "Service Unavailable"},
        {504, "Gateway Timeout"}
    };

    auto iterator = reasons.find(status);

    if (iterator == reasons.end()) {
        return "Unknown";
    }

    return iterator->second;
}


// ============================================================================
// SECTION 2: CASE-STUDY DATA MODELS
// ============================================================================

struct HttpRequest {
    HttpMethod method;
    string target;
    map<string, string> headers;
    string body;

    string header(const string& name) const {
        for (const auto& [key, value] : headers) {
            string normalizedKey = key;
            string normalizedName = name;

            transform(
                normalizedKey.begin(),
                normalizedKey.end(),
                normalizedKey.begin(),
                ::tolower
            );

            transform(
                normalizedName.begin(),
                normalizedName.end(),
                normalizedName.begin(),
                ::tolower
            );

            if (normalizedKey == normalizedName) {
                return value;
            }
        }

        return "";
    }
};


struct HttpResponse {
    int statusCode;
    map<string, string> headers;
    string body;

    string serialize() const {
        ostringstream output;

        output << "HTTP/1.1 "
               << statusCode
               << " "
               << statusReason(statusCode)
               << "\r\n";

        for (const auto& [name, value] : headers) {
            output << name << ": " << value << "\r\n";
        }

        output << "\r\n";
        output << body;

        return output.str();
    }
};


void printSection(const string& title) {
    cout << "\n" << string(78, '=') << "\n";
    cout << title << "\n";
    cout << string(78, '=') << "\n";
}


// ============================================================================
// SECTION 3: APPLICATION DOMAIN
// ============================================================================

struct Account {
    int id;
    string owner;
    double balance;
    bool active;
};


class AccountRepository {
private:
    unordered_map<int, Account> accounts;

public:
    AccountRepository() {
        accounts.emplace(1001, Account{1001, "Alice", 125000.0, true});
        accounts.emplace(1002, Account{1002, "Bob", 42000.0, true});
        accounts.emplace(1003, Account{1003, "Carol", 0.0, false});
    }

    optional<Account> findById(int id) const {
        auto iterator = accounts.find(id);

        if (iterator == accounts.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    bool updateBalance(int id, double newBalance) {
        auto iterator = accounts.find(id);

        if (iterator == accounts.end()) {
            return false;
        }

        if (newBalance < 0) {
            return false;
        }

        iterator->second.balance = newBalance;
        return true;
    }
};


// ============================================================================
// SECTION 4: REQUEST ID GENERATION
// ============================================================================

string createRequestId() {
    static mt19937 generator(
        static_cast<unsigned int>(
            chrono::high_resolution_clock::now()
                .time_since_epoch()
                .count()
        )
    );

    uniform_int_distribution<int> distribution(100000, 999999);

    return "req-" + to_string(distribution(generator));
}


// ============================================================================
// SECTION 5: INPUT VALIDATION
// ============================================================================

struct ValidationResult {
    bool valid;
    vector<string> errors;
};


ValidationResult validateRequest(const HttpRequest& request) {
    ValidationResult result{true, {}};

    const string host = request.header("Host");

    if (host.empty()) {
        result.valid = false;
        result.errors.push_back("Missing Host header.");
    }

    if (request.target.empty() || request.target.front() != '/') {
        result.valid = false;
        result.errors.push_back("Request target must use origin-form beginning with '/'.");
    }

    if (request.method == HttpMethod::POST ||
        request.method == HttpMethod::PUT ||
        request.method == HttpMethod::PATCH) {

        const string contentType = request.header("Content-Type");

        if (contentType.empty()) {
            result.valid = false;
            result.errors.push_back("Body-bearing request requires Content-Type.");
        }
    }

    const string contentLength = request.header("Content-Length");

    if (!contentLength.empty()) {
        try {
            const size_t declared = stoull(contentLength);

            if (declared != request.body.size()) {
                result.valid = false;
                result.errors.push_back(
                    "Content-Length does not match actual body length."
                );
            }
        } catch (const exception&) {
            result.valid = false;
            result.errors.push_back("Invalid Content-Length.");
        }
    }

    return result;
}


// ============================================================================
// SECTION 6: RATE LIMITER
// ============================================================================

class TokenBucket {
private:
    double capacity;
    double refillRate;
    double tokens;
    chrono::steady_clock::time_point lastUpdate;

    void refill() {
        const auto now = chrono::steady_clock::now();

        const double elapsed =
            chrono::duration<double>(now - lastUpdate).count();

        lastUpdate = now;

        tokens = min(
            capacity,
            tokens + elapsed * refillRate
        );
    }

public:
    TokenBucket(double capacity, double refillRate)
        : capacity(capacity),
          refillRate(refillRate),
          tokens(capacity),
          lastUpdate(chrono::steady_clock::now()) {

        if (capacity <= 0 || refillRate <= 0) {
            throw invalid_argument(
                "Rate limiter capacity and refill rate must be positive."
            );
        }
    }

    bool allow(double cost = 1.0) {
        refill();

        if (cost <= 0 || cost > capacity) {
            return false;
        }

        if (tokens < cost) {
            return false;
        }

        tokens -= cost;
        return true;
    }
};


// ============================================================================
// SECTION 7: IDEMPOTENCY STORE
// ============================================================================

class IdempotencyStore {
private:
    unordered_map<string, HttpResponse> completedRequests;

public:
    optional<HttpResponse> find(const string& key) const {
        auto iterator = completedRequests.find(key);

        if (iterator == completedRequests.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    void save(const string& key, const HttpResponse& response) {
        completedRequests[key] = response;
    }
};


// ============================================================================
// SECTION 8: ETAG CACHE
// ============================================================================

class RepresentationCache {
private:
    struct Entry {
        string etag;
        string body;
    };

    unordered_map<string, Entry> entries;

public:
    void put(const string& resource, const string& etag, const string& body) {
        entries[resource] = Entry{etag, body};
    }

    optional<Entry> get(const string& resource) const {
        auto iterator = entries.find(resource);

        if (iterator == entries.end()) {
            return nullopt;
        }

        return iterator->second;
    }
};


// ============================================================================
// SECTION 9: AUTHENTICATION
// ============================================================================

struct AuthContext {
    bool authenticated;
    string subject;
    vector<string> roles;
};


class AuthenticationService {
public:
    AuthContext authenticate(const HttpRequest& request) const {
        const string authorization = request.header("Authorization");

        if (authorization == "Bearer demo-admin-token") {
            return {
                true,
                "alice",
                {"customer", "admin"}
            };
        }

        if (authorization == "Bearer demo-customer-token") {
            return {
                true,
                "bob",
                {"customer"}
            };
        }

        return {
            false,
            "",
            {}
        };
    }
};


// ============================================================================
// SECTION 10: AUTHORIZATION
// ============================================================================

bool hasRole(const AuthContext& context, const string& requiredRole) {
    return find(
        context.roles.begin(),
        context.roles.end(),
        requiredRole
    ) != context.roles.end();
}


// ============================================================================
// SECTION 11: SECURE ERROR RESPONSE
// ============================================================================

HttpResponse errorResponse(
    int statusCode,
    const string& publicMessage,
    const string& requestId
) {
    ostringstream body;

    body << "{"
         << "\"error\":{"
         << "\"status\":" << statusCode << ","
         << "\"message\":\"" << publicMessage << "\","
         << "\"request_id\":\"" << requestId << "\""
         << "}"
         << "}";

    return {
        statusCode,
        {
            {"Content-Type", "application/json"},
            {"Cache-Control", "no-store"},
            {"X-Request-ID", requestId}
        },
        body.str()
    };
}


// ============================================================================
// SECTION 12: API SERVICE
// ============================================================================

class AccountApi {
private:
    AccountRepository repository;
    AuthenticationService authentication;
    TokenBucket rateLimiter;
    IdempotencyStore idempotencyStore;
    RepresentationCache cache;

    HttpResponse accountToResponse(
        const Account& account,
        const string& requestId
    ) {
        ostringstream body;

        body << "{"
             << "\"id\":" << account.id << ","
             << "\"owner\":\"" << account.owner << "\","
             << "\"balance\":" << fixed << setprecision(2) << account.balance << ","
             << "\"active\":" << (account.active ? "true" : "false")
             << "}";

        const string representation = body.str();

        return {
            200,
            {
                {"Content-Type", "application/json"},
                {"Cache-Control", "private, max-age=30"},
                {"ETag", "\"account-" + to_string(account.id) + "\""},
                {"X-Request-ID", requestId}
            },
            representation
        };
    }

public:
    AccountApi()
        : rateLimiter(3.0, 1.0) {}

    HttpResponse handle(const HttpRequest& request) {
        const string requestId = createRequestId();

        ValidationResult validation = validateRequest(request);

        if (!validation.valid) {
            return errorResponse(
                400,
                "The request failed validation.",
                requestId
            );
        }

        if (!rateLimiter.allow()) {
            return errorResponse(
                429,
                "Rate limit exceeded.",
                requestId
            );
        }

        AuthContext auth = authentication.authenticate(request);

        if (!auth.authenticated) {
            return errorResponse(
                401,
                "Authentication required.",
                requestId
            );
        }

        // GET /accounts/{id}
        if (request.method == HttpMethod::GET &&
            request.target.rfind("/accounts/", 0) == 0) {

            const string idText =
                request.target.substr(string("/accounts/").size());

            int accountId = 0;

            try {
                size_t consumed = 0;
                accountId = stoi(idText, &consumed);

                if (consumed != idText.size()) {
                    throw invalid_argument("Invalid account identifier.");
                }
            } catch (const exception&) {
                return errorResponse(
                    400,
                    "Invalid account identifier.",
                    requestId
                );
            }

            optional<Account> account = repository.findById(accountId);

            if (!account.has_value()) {
                return errorResponse(
                    404,
                    "Account not found.",
                    requestId
                );
            }

            // Authorization: a customer may only inspect the demonstration
            // account associated with that customer, while administrators
            // have broader access.
            if (!hasRole(auth, "admin") && auth.subject != account->owner) {
                return errorResponse(
                    403,
                    "Access denied.",
                    requestId
                );
            }

            HttpResponse response =
                accountToResponse(account.value(), requestId);

            const string suppliedEtag = request.header("If-None-Match");

            if (!suppliedEtag.empty() &&
                suppliedEtag == response.headers["ETag"]) {

                return {
                    304,
                    {
                        {"ETag", response.headers["ETag"]},
                        {"X-Request-ID", requestId}
                    },
                    ""
                };
            }

            cache.put(
                request.target,
                response.headers["ETag"],
                response.body
            );

            return response;
        }

        // POST /transfers
        if (request.method == HttpMethod::POST &&
            request.target == "/transfers") {

            if (!hasRole(auth, "customer") &&
                !hasRole(auth, "admin")) {

                return errorResponse(
                    403,
                    "Transfer permission denied.",
                    requestId
                );
            }

            const string idempotencyKey =
                request.header("Idempotency-Key");

            if (idempotencyKey.empty()) {
                return errorResponse(
                    400,
                    "Idempotency-Key is required for this operation.",
                    requestId
                );
            }

            optional<HttpResponse> previous =
                idempotencyStore.find(idempotencyKey);

            if (previous.has_value()) {
                HttpResponse replay = previous.value();
                replay.headers["X-Idempotent-Replay"] = "true";
                return replay;
            }

            // In a real financial system, the body would be parsed with a
            // strict JSON parser, schema validation would be performed,
            // authorization would be checked against account ownership,
            // and the transfer would execute transactionally in a database.
            if (request.body.empty()) {
                return errorResponse(
                    422,
                    "Transfer payload is empty.",
                    requestId
                );
            }

            HttpResponse response{
                201,
                {
                    {"Content-Type", "application/json"},
                    {"Cache-Control", "no-store"},
                    {"X-Request-ID", requestId}
                },
                "{\"status\":\"accepted\",\"transfer_id\":\"TRX-10001\"}"
            };

            idempotencyStore.save(idempotencyKey, response);

            return response;
        }

        // Unsupported endpoint/method.
        return errorResponse(
            404,
            "Resource not found.",
            requestId
        );
    }
};


// ============================================================================
// SECTION 13: SECURITY CONFIGURATION MODEL
// ============================================================================

struct TlsPolicy {
    string minimumVersion;
    bool verifyPeer;
    bool verifyHostname;
    vector<string> allowedApplicationProtocols;
};


void printTlsPolicy(const TlsPolicy& policy) {
    printSection("TLS SECURITY POLICY");

    cout << "Minimum TLS version: "
         << policy.minimumVersion << "\n";

    cout << "Peer verification: "
         << (policy.verifyPeer ? "enabled" : "disabled") << "\n";

    cout << "Hostname verification: "
         << (policy.verifyHostname ? "enabled" : "disabled") << "\n";

    cout << "ALPN protocols: ";

    for (const auto& protocol : policy.allowedApplicationProtocols) {
        cout << protocol << " ";
    }

    cout << "\n";
}


// ============================================================================
// SECTION 14: OBSERVABILITY
// ============================================================================

struct RequestMetrics {
    string requestId;
    string method;
    string path;
    int statusCode;
    double durationMs;
    size_t responseBytes;
};


void printMetrics(const RequestMetrics& metrics) {
    printSection("OBSERVABILITY RECORD");

    cout << "request_id      : " << metrics.requestId << "\n";
    cout << "method          : " << metrics.method << "\n";
    cout << "path            : " << metrics.path << "\n";
    cout << "status          : " << metrics.statusCode << "\n";
    cout << "duration_ms     : " << metrics.durationMs << "\n";
    cout << "response_bytes  : " << metrics.responseBytes << "\n";
}


// ============================================================================
// SECTION 15: REQUEST FACTORY
// ============================================================================

HttpRequest createGetAccountRequest(
    int accountId,
    const string& authorization,
    const string& etag = ""
) {
    map<string, string> headers{
        {"Host", "api.bank.example"},
        {"Accept", "application/json"},
        {"Authorization", authorization}
    };

    if (!etag.empty()) {
        headers["If-None-Match"] = etag;
    }

    return {
        HttpMethod::GET,
        "/accounts/" + to_string(accountId),
        headers,
        ""
    };
}


HttpRequest createTransferRequest(
    const string& authorization,
    const string& idempotencyKey,
    const string& body
) {
    return {
        HttpMethod::POST,
        "/transfers",
        {
            {"Host", "api.bank.example"},
            {"Accept", "application/json"},
            {"Content-Type", "application/json"},
            {"Content-Length", to_string(body.size())},
            {"Authorization", authorization},
            {"Idempotency-Key", idempotencyKey}
        },
        body
    };
}


// ============================================================================
// SECTION 16: CASE-STUDY EXECUTION
// ============================================================================

void executeRequest(
    AccountApi& api,
    const HttpRequest& request
) {
    const auto start = chrono::steady_clock::now();

    HttpResponse response = api.handle(request);

    const auto end = chrono::steady_clock::now();

    const double durationMs =
        chrono::duration<double, milli>(end - start).count();

    cout << "\nRequest: "
         << methodToString(request.method)
         << " "
         << request.target
         << "\n";

    cout << response.serialize() << "\n";

    RequestMetrics metrics{
        response.headers.count("X-Request-ID")
            ? response.headers.at("X-Request-ID")
            : "unknown",
        methodToString(request.method),
        request.target,
        response.statusCode,
        durationMs,
        response.body.size()
    };

    printMetrics(metrics);
}


// ============================================================================
// SECTION 17: ARCHITECTURAL DISCUSSION
// ============================================================================

void printArchitecture() {
    printSection("CASE-STUDY ARCHITECTURE");

    cout << "Client\n";
    cout << "  |\n";
    cout << "  | HTTPS / TLS\n";
    cout << "  v\n";
    cout << "TLS termination / API gateway\n";
    cout << "  |\n";
    cout << "  +--> HTTP request parsing\n";
    cout << "  +--> validation\n";
    cout << "  +--> authentication\n";
    cout << "  +--> authorization\n";
    cout << "  +--> rate limiting\n";
    cout << "  +--> routing\n";
    cout << "  +--> application service\n";
    cout << "  +--> repository / database\n";
    cout << "  +--> structured response\n";
    cout << "  +--> observability\n";
}


// ============================================================================
// SECTION 18: SECURITY CONSIDERATIONS
// ============================================================================

void printSecurityConsiderations() {
    printSection("SECURITY CONSIDERATIONS");

    vector<string> points = {
        "Use HTTPS for sensitive communication.",
        "Validate certificate chains and hostnames.",
        "Do not disable TLS certificate verification in production.",
        "Separate authentication from authorization.",
        "Apply least privilege to authenticated identities.",
        "Validate and constrain all externally supplied data.",
        "Do not expose secrets in logs or error messages.",
        "Use secure cookie attributes where cookies are used.",
        "Use idempotency controls for retry-sensitive financial operations.",
        "Apply rate limits and abuse controls.",
        "Use maintained TLS and HTTP implementations rather than custom cryptography.",
        "Keep HTTP parser behavior consistent across proxies and origin servers."
    };

    for (size_t i = 0; i < points.size(); ++i) {
        cout << i + 1 << ". " << points[i] << "\n";
    }
}


// ============================================================================
// MAIN
// ============================================================================

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    printSection("HTTP AND HTTPS C++ INDUSTRY CASE STUDY");

    cout << "HTTP methods are application-level semantics.\n";
    cout << "HTTPS protects HTTP traffic using TLS.\n";
    cout << "TLS authentication and application authorization solve different problems.\n";

    printArchitecture();

    TlsPolicy policy{
        "TLS 1.2 or newer",
        true,
        true,
        {"h2", "http/1.1"}
    };

    printTlsPolicy(policy);

    AccountApi api;

    // Administrator can inspect Alice's account.
    executeRequest(
        api,
        createGetAccountRequest(
            1001,
            "Bearer demo-admin-token"
        )
    );

    // Customer Bob attempts to access Alice's account.
    // The application should reject the operation with 403.
    executeRequest(
        api,
        createGetAccountRequest(
            1001,
            "Bearer demo-customer-token"
        )
    );

    // Missing credentials should produce 401.
    executeRequest(
        api,
        createGetAccountRequest(
            1001,
            ""
        )
    );

    // A conditional GET demonstrates ETag-based cache validation.
    executeRequest(
        api,
        createGetAccountRequest(
            1001,
            "Bearer demo-admin-token",
            "\"account-1001\""
        )
    );

    // Financial-style POST with an idempotency key.
    const string transferBody =
        "{\"from\":1001,\"to\":1002,\"amount\":1500.00}";

    executeRequest(
        api,
        createTransferRequest(
            "Bearer demo-admin-token",
            "transfer-key-001",
            transferBody
        )
    );

    // The same request can safely be replayed without creating a second
    // demonstration transaction.
    executeRequest(
        api,
        createTransferRequest(
            "Bearer demo-admin-token",
            "transfer-key-001",
            transferBody
        )
    );

    printSecurityConsiderations();

    printSection("HTTP STATUS CODE INTERPRETATION");

    const vector<int> statuses{
        200, 201, 304, 400, 401, 403, 404, 429, 500, 502, 503, 504
    };

    for (int status : statuses) {
        cout << status
             << " -> "
             << statusReason(status)
             << "\n";
    }

    printSection("PERFORMANCE CONSIDERATIONS");

    cout << "Routing lookup: O(R) in this simple vector-style model.\n";
    cout << "Production routers commonly use indexed structures for faster lookup.\n";
    cout << "Hash-table repository lookup: average O(1).\n";
    cout << "Rate-limit decision: O(1).\n";
    cout << "Idempotency lookup: average O(1).\n";
    cout << "ETag lookup: average O(1).\n";
    cout << "Real HTTP/TLS performance also depends on connection reuse, latency,\n";
    cout << "payload size, compression, protocol version, and cryptographic work.\n";

    printSection("PRODUCTION BOUNDARIES");

    cout << "This program models HTTP application behavior but intentionally does\n";
    cout << "not implement TLS cryptography or a complete HTTP wire parser.\n";
    cout << "Production services should use mature, maintained networking and TLS\n";
    cout << "libraries with secure defaults, certificate validation, timeouts,\n";
    cout << "resource limits, logging controls, and regular security updates.\n";

    return 0;
}
