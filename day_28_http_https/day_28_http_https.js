/*
 * HTTP AND HTTPS STUDY FILE
 *
 * This file demonstrates HTTP and HTTPS concepts using standard JavaScript
 * facilities available in modern Node.js. It progresses from HTTP message
 * structure and methods to headers, status codes, URL parsing, cookies,
 * caching, TLS inspection, HTTPS requests, routing, validation, rate
 * limiting, retries, and security-oriented design.
 *
 * Run with:
 *   node http_https_study.js
 */

"use strict";

const http = require("node:http");
const https = require("node:https");
const tls = require("node:tls");
const crypto = require("node:crypto");
const { URL } = require("node:url");


function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}


// ============================================================================
// 1. HTTP TERMINOLOGY
// ============================================================================

function demonstrateTerminology() {
    section("1. HTTP TERMINOLOGY");

    const terms = {
        HTTP: "Hypertext Transfer Protocol.",
        HTTPS: "HTTP transported through TLS.",
        client: "The system initiating an HTTP request.",
        server: "The system receiving and processing the request.",
        request: "Client-to-server HTTP message.",
        response: "Server-to-client HTTP message.",
        header: "Metadata associated with an HTTP message.",
        body: "Optional application payload.",
        TLS: "Transport Layer Security.",
        certificate: "Digitally signed identity credential containing a public key."
    };

    for (const [name, definition] of Object.entries(terms)) {
        console.log(`${name.padEnd(14)}: ${definition}`);
    }
}


// ============================================================================
// 2. HTTP REQUEST MODEL
// ============================================================================

class HttpRequest {
    constructor(method, target, headers = {}, body = "") {
        this.method = method.toUpperCase();
        this.target = target;
        this.headers = headers;
        this.body = body;
    }

    serialize() {
        const headerText = Object.entries(this.headers)
            .map(([name, value]) => `${name}: ${value}`)
            .join("\r\n");

        return `${this.method} ${this.target} HTTP/1.1\r\n${headerText}\r\n\r\n${this.body}`;
    }
}


function demonstrateRequest() {
    section("2. HTTP REQUEST STRUCTURE");

    const request = new HttpRequest(
        "GET",
        "/api/users?page=1&limit=10",
        {
            Host: "api.example.com",
            Accept: "application/json",
            "User-Agent": "HTTPStudyClient/1.0",
            Connection: "keep-alive"
        }
    );

    console.log(request.serialize());
}


// ============================================================================
// 3. METHODS
// ============================================================================

function demonstrateMethods() {
    section("3. HTTP METHODS");

    const methods = {
        GET: ["safe", "idempotent", "Retrieve a representation."],
        HEAD: ["safe", "idempotent", "Retrieve response headers without a body."],
        POST: ["not safe", "not generally idempotent", "Submit or create data."],
        PUT: ["not safe", "idempotent", "Create or replace a known resource."],
        PATCH: ["not safe", "not inherently idempotent", "Partially modify a resource."],
        DELETE: ["not safe", "idempotent", "Request deletion of a resource."],
        OPTIONS: ["safe", "idempotent", "Discover supported communication options."],
        CONNECT: ["not safe", "not generally idempotent", "Establish a tunnel through a proxy."],
        TRACE: ["safe", "idempotent", "Diagnostic loop-back method."]
    };

    for (const [method, properties] of Object.entries(methods)) {
        console.log(
            `${method.padEnd(8)} | ${properties[0].padEnd(12)} | ` +
            `${properties[1].padEnd(22)} | ${properties[2]}`
        );
    }
}


// ============================================================================
// 4. STATUS CODES
// ============================================================================

function classifyStatus(status) {
    if (status >= 100 && status < 200) return "1xx Informational";
    if (status >= 200 && status < 300) return "2xx Successful";
    if (status >= 300 && status < 400) return "3xx Redirection";
    if (status >= 400 && status < 500) return "4xx Client Error";
    if (status >= 500 && status < 600) return "5xx Server Error";
    return "Invalid";
}


function demonstrateStatusCodes() {
    section("4. HTTP STATUS CODES");

    const statuses = {
        200: "OK",
        201: "Created",
        202: "Accepted",
        204: "No Content",
        301: "Moved Permanently",
        302: "Found",
        304: "Not Modified",
        307: "Temporary Redirect",
        308: "Permanent Redirect",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        422: "Unprocessable Content",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout"
    };

    for (const [status, phrase] of Object.entries(statuses)) {
        console.log(`${status}: ${phrase} (${classifyStatus(Number(status))})`);
    }
}


// ============================================================================
// 5. HEADERS
// ============================================================================

function normalizeHeaders(headers) {
    const normalized = {};

    for (const [name, value] of Object.entries(headers)) {
        normalized[name.toLowerCase()] = String(value);
    }

    return normalized;
}


function demonstrateHeaders() {
    section("5. HTTP HEADERS");

    const headers = {
        Host: "example.com",
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: "Bearer REDACTED",
        "Cache-Control": "no-cache",
        "User-Agent": "HTTPStudyClient/1.0"
    };

    console.log("Original headers:", headers);
    console.log("Normalized headers:", normalizeHeaders(headers));
    console.log("Header names are case-insensitive.");
}


// ============================================================================
// 6. URL PROCESSING
// ============================================================================

function demonstrateUrl() {
    section("6. URL PROCESSING");

    const url = new URL(
        "https://api.example.com:8443/v1/users/42?active=true&sort=name#profile"
    );

    console.log("protocol:", url.protocol);
    console.log("hostname:", url.hostname);
    console.log("port:", url.port);
    console.log("pathname:", url.pathname);
    console.log("search:", url.search);
    console.log("hash:", url.hash);

    console.log("active:", url.searchParams.get("active"));
    console.log("sort:", url.searchParams.get("sort"));

    url.searchParams.set("page", "2");
    console.log("Updated URL:", url.toString());
}


// ============================================================================
// 7. JSON REQUEST
// ============================================================================

function createJsonRequest(method, urlString, data) {
    const body = JSON.stringify(data);

    return {
        method,
        url: urlString,
        headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(body)
        },
        body
    };
}


function demonstrateJsonRequest() {
    section("7. JSON HTTP REQUEST");

    const request = createJsonRequest(
        "POST",
        "https://api.example.com/users",
        {
            name: "Atul",
            skills: ["Python", "JavaScript", "C++"],
            active: true
        }
    );

    console.log(request);
}


// ============================================================================
// 8. COOKIES
// ============================================================================

function parseCookieHeader(cookieHeader) {
    const result = {};

    for (const segment of cookieHeader.split(";")) {
        const index = segment.indexOf("=");

        if (index === -1) {
            continue;
        }

        const key = segment.slice(0, index).trim();
        const value = segment.slice(index + 1).trim();

        result[key] = value;
    }

    return result;
}


function demonstrateCookies() {
    section("8. COOKIES");

    const cookie = "session_id=abc123; theme=dark; language=en";
    console.log(parseCookieHeader(cookie));

    console.log("Secure cookies should be transmitted through HTTPS.");
    console.log("HttpOnly cookies cannot normally be read by browser JavaScript.");
    console.log("SameSite controls cross-site cookie transmission.");
}


// ============================================================================
// 9. CACHING
// ============================================================================

function demonstrateCaching() {
    section("9. HTTP CACHING");

    const response = {
        status: 200,
        headers: {
            "Cache-Control": "max-age=60",
            ETag: "\"user-42-v8\""
        },
        body: JSON.stringify({
            id: 42,
            name: "Alice"
        })
    };

    console.log("Original response:", response);

    const conditionalRequest = {
        "If-None-Match": response.headers.ETag
    };

    console.log("Conditional request:", conditionalRequest);
    console.log("If unchanged, server can return 304 Not Modified.");
}


// ============================================================================
// 10. BASIC AUTHENTICATION ENCODING
// ============================================================================

function basicAuthorization(username, password) {
    return "Basic " +
        Buffer.from(`${username}:${password}`, "utf8").toString("base64");
}


function demonstrateAuthentication() {
    section("10. AUTHENTICATION");

    const authorization = basicAuthorization("alice", "example-password");

    console.log("Authorization header:", authorization);
    console.log("Base64 is encoding, not encryption.");
    console.log("Basic authentication therefore requires protected transport.");
}


// ============================================================================
// 11. ROUTER
// ============================================================================

class Router {
    constructor() {
        this.routes = [];
    }

    add(method, pattern, handler) {
        this.routes.push({
            method: method.toUpperCase(),
            pattern,
            handler
        });
    }

    matchPattern(pattern, path) {
        const patternParts = pattern.split("/").filter(Boolean);
        const pathParts = path.split("/").filter(Boolean);

        if (patternParts.length !== pathParts.length) {
            return false;
        }

        return patternParts.every((part, index) => {
            if (part.startsWith(":")) {
                return true;
            }

            return part === pathParts[index];
        });
    }

    resolve(method, path) {
        const upperMethod = method.toUpperCase();

        return this.routes.find(
            route =>
                route.method === upperMethod &&
                this.matchPattern(route.pattern, path)
        );
    }
}


function demonstrateRouting() {
    section("11. APPLICATION ROUTING");

    const router = new Router();

    router.add("GET", "/users/:id", "getUser");
    router.add("POST", "/users", "createUser");
    router.add("DELETE", "/users/:id", "deleteUser");

    const requests = [
        ["GET", "/users/42"],
        ["POST", "/users"],
        ["DELETE", "/users/42"],
        ["GET", "/products/5"]
    ];

    for (const [method, path] of requests) {
        const route = router.resolve(method, path);
        console.log(`${method} ${path} -> ${route ? route.handler : "404 Not Found"}`);
    }
}


// ============================================================================
// 12. REQUEST VALIDATION
// ============================================================================

function validateRequest(request) {
    const errors = [];
    const validMethods = new Set([
        "GET", "HEAD", "POST", "PUT", "PATCH",
        "DELETE", "OPTIONS", "CONNECT", "TRACE"
    ]);

    if (!validMethods.has(request.method.toUpperCase())) {
        errors.push("Unsupported HTTP method.");
    }

    if (!request.target.startsWith("/")) {
        errors.push("Origin-form request target should start with '/'.");
    }

    const normalized = normalizeHeaders(request.headers);

    if (!normalized.host) {
        errors.push("Host header is required for HTTP/1.1 requests.");
    }

    if (normalized["content-length"] !== undefined) {
        const declared = Number(normalized["content-length"]);
        const actual = Buffer.byteLength(request.body || "");

        if (!Number.isInteger(declared) || declared !== actual) {
            errors.push("Content-Length does not match the body.");
        }
    }

    return errors;
}


function demonstrateValidation() {
    section("12. REQUEST VALIDATION");

    const validRequest = new HttpRequest(
        "POST",
        "/users",
        {
            Host: "api.example.com",
            "Content-Length": "5"
        },
        "hello"
    );

    console.log("Valid:", validateRequest(validRequest));

    const invalidRequest = new HttpRequest(
        "POST",
        "/users",
        {
            Host: "api.example.com",
            "Content-Length": "50"
        },
        "hello"
    );

    console.log("Invalid:", validateRequest(invalidRequest));
}


// ============================================================================
// 13. TOKEN BUCKET RATE LIMITER
// ============================================================================

class TokenBucket {
    constructor(capacity, refillRatePerSecond) {
        if (capacity <= 0 || refillRatePerSecond <= 0) {
            throw new Error("Capacity and refill rate must be positive.");
        }

        this.capacity = capacity;
        this.refillRate = refillRatePerSecond;
        this.tokens = capacity;
        this.lastRefill = process.hrtime.bigint();
    }

    allow(cost = 1) {
        const now = process.hrtime.bigint();
        const elapsedSeconds =
            Number(now - this.lastRefill) / 1_000_000_000;

        this.lastRefill = now;

        this.tokens = Math.min(
            this.capacity,
            this.tokens + elapsedSeconds * this.refillRate
        );

        if (this.tokens >= cost) {
            this.tokens -= cost;
            return true;
        }

        return false;
    }
}


function demonstrateRateLimiting() {
    section("13. RATE LIMITING");

    const limiter = new TokenBucket(3, 1);

    for (let index = 1; index <= 5; index++) {
        console.log(`Request ${index}: allowed=${limiter.allow()}`);
    }
}


// ============================================================================
// 14. SECURITY HEADERS
// ============================================================================

function demonstrateSecurityHeaders() {
    section("14. SECURITY HEADERS");

    const headers = {
        "Strict-Transport-Security":
            "max-age=31536000; includeSubDomains",
        "Content-Security-Policy":
            "default-src 'self'; object-src 'none'",
        "X-Content-Type-Options":
            "nosniff",
        "Referrer-Policy":
            "strict-origin-when-cross-origin"
    };

    console.log(headers);
    console.log("These controls complement, rather than replace, application security.");
}


// ============================================================================
// 15. HASHING AND ETAG
// ============================================================================

function createWeakRepresentationTag(body) {
    const digest = crypto
        .createHash("sha256")
        .update(body)
        .digest("hex");

    return `"${digest}"`;
}


function demonstrateEtags() {
    section("15. REPRESENTATION VALIDATION");

    const body = JSON.stringify({
        id: 42,
        name: "Keyboard"
    });

    console.log("Representation:", body);
    console.log("ETag:", createWeakRepresentationTag(body));
    console.log("A real ETag can be strong or weak depending on representation semantics.");
}


// ============================================================================
// 16. HTTPS REQUEST
// ============================================================================

function httpsGet(hostname, path = "/") {
    return new Promise((resolve, reject) => {
        const request = https.request(
            {
                hostname,
                path,
                method: "GET",
                headers: {
                    Accept: "text/html,application/json;q=0.9,*/*;q=0.1",
                    "User-Agent": "HTTPStudyClient/1.0"
                },
                timeout: 5000,
                rejectUnauthorized: true
            },
            response => {
                const chunks = [];

                response.on("data", chunk => chunks.push(chunk));

                response.on("end", () => {
                    resolve({
                        statusCode: response.statusCode,
                        headers: response.headers,
                        body: Buffer.concat(chunks)
                    });
                });
            }
        );

        request.on("timeout", () => {
            request.destroy(new Error("HTTPS request timed out."));
        });

        request.on("error", reject);
        request.end();
    });
}


async function demonstrateHttpsRequest() {
    section("16. HTTPS REQUEST");

    try {
        const response = await httpsGet("example.com", "/");

        console.log("Status:", response.statusCode);
        console.log("Content-Type:", response.headers["content-type"]);
        console.log("Body bytes:", response.body.length);
        console.log(
            "First 200 bytes:",
            response.body.toString("utf8", 0, 200)
        );
    } catch (error) {
        console.log("HTTPS request failed:", error.message);
    }
}


// ============================================================================
// 17. TLS CERTIFICATE INSPECTION
// ============================================================================

function inspectCertificate(hostname = "example.com") {
    section(`17. TLS CERTIFICATE INSPECTION: ${hostname}`);

    return new Promise(resolve => {
        const socket = tls.connect(
            {
                host: hostname,
                port: 443,
                servername: hostname,
                rejectUnauthorized: true,
                timeout: 5000
            },
            () => {
                const certificate = socket.getPeerCertificate(true);

                console.log("Authorized:", socket.authorized);
                console.log("Authorization error:", socket.authorizationError);
                console.log("TLS protocol:", socket.getProtocol());
                console.log("Cipher:", socket.getCipher());
                console.log("ALPN:", socket.alpnProtocol);
                console.log("Certificate subject:", certificate.subject);
                console.log("Certificate issuer:", certificate.issuer);
                console.log("Valid from:", certificate.valid_from);
                console.log("Valid to:", certificate.valid_to);
                console.log("Subject alternative names:", certificate.subjectaltname);

                socket.end();
                resolve();
            }
        );

        socket.on("timeout", () => {
            socket.destroy();
            console.log("TLS inspection timed out.");
            resolve();
        });

        socket.on("error", error => {
            console.log("TLS inspection failed:", error.message);
            resolve();
        });
    });
}


// ============================================================================
// 18. LOCAL HTTP SERVER
// ============================================================================

function createDemoServer() {
    return http.createServer((request, response) => {
        const parsedUrl = new URL(
            request.url,
            `http://${request.headers.host || "localhost"}`
        );

        if (request.method === "GET" && parsedUrl.pathname === "/health") {
            const body = JSON.stringify({
                status: "ok",
                timestamp: new Date().toISOString()
            });

            response.writeHead(200, {
                "Content-Type": "application/json",
                "Content-Length": Buffer.byteLength(body),
                "Cache-Control": "no-store"
            });

            response.end(body);
            return;
        }

        if (request.method === "POST" && parsedUrl.pathname === "/echo") {
            const chunks = [];

            request.on("data", chunk => chunks.push(chunk));

            request.on("end", () => {
                const body = Buffer.concat(chunks);

                response.writeHead(200, {
                    "Content-Type":
                        request.headers["content-type"] || "application/octet-stream",
                    "Content-Length": body.length
                });

                response.end(body);
            });

            return;
        }

        response.writeHead(404, {
            "Content-Type": "application/json"
        });

        response.end(JSON.stringify({
            error: "Not Found"
        }));
    });
}


async function demonstrateLocalServer() {
    section("18. LOCAL HTTP SERVER");

    const server = createDemoServer();

    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));

    const address = server.address();
    console.log("Server listening on:", address);

    await new Promise((resolve, reject) => {
        const request = http.request(
            {
                hostname: "127.0.0.1",
                port: address.port,
                path: "/health",
                method: "GET"
            },
            response => {
                const chunks = [];

                response.on("data", chunk => chunks.push(chunk));

                response.on("end", () => {
                    console.log("Status:", response.statusCode);
                    console.log(
                        "Response:",
                        Buffer.concat(chunks).toString("utf8")
                    );
                    resolve();
                });
            }
        );

        request.on("error", reject);
        request.end();
    });

    server.close();
}


// ============================================================================
// 19. RETRY DECISION
// ============================================================================

function shouldRetry(statusCode, method) {
    const retryableStatuses = new Set([408, 429, 500, 502, 503, 504]);
    const retryableMethods = new Set([
        "GET",
        "HEAD",
        "OPTIONS",
        "PUT",
        "DELETE"
    ]);

    return retryableStatuses.has(statusCode) &&
        retryableMethods.has(method.toUpperCase());
}


function demonstrateRetryPolicy() {
    section("19. RETRY POLICY");

    const cases = [
        [503, "GET"],
        [500, "POST"],
        [429, "GET"],
        [404, "GET"],
        [504, "DELETE"]
    ];

    for (const [status, method] of cases) {
        console.log(
            `${method} + ${status}: retry=${shouldRetry(status, method)}`
        );
    }

    console.log("Retry policy must account for idempotency and server guidance.");
}


// ============================================================================
// 20. TIMEOUTS
// ============================================================================

function demonstrateTimeoutDesign() {
    section("20. TIMEOUT DESIGN");

    const timeouts = {
        dns: "Limit name-resolution waiting time.",
        connection: "Limit TCP connection establishment.",
        tls: "Limit TLS handshake waiting time.",
        request: "Limit waiting for an HTTP response.",
        idle: "Limit periods without useful activity."
    };

    for (const [type, explanation] of Object.entries(timeouts)) {
        console.log(`${type.padEnd(12)}: ${explanation}`);
    }
}


// ============================================================================
// 21. HTTP/2 AND HTTP/3 CONCEPTS
// ============================================================================

function demonstrateModernHttpVersions() {
    section("21. HTTP VERSIONS");

    console.log("HTTP/1.1: text-based message syntax and persistent connections.");
    console.log("HTTP/2: binary framing, multiplexed streams, HPACK compression.");
    console.log("HTTP/3: HTTP semantics over QUIC, with QPACK header compression.");
    console.log("HTTP/2 and HTTP/3 retain HTTP request/response semantics while changing transport/framing mechanisms.");
}


// ============================================================================
// 22. HTTPS SECURITY PROPERTIES
// ============================================================================

function demonstrateHttpsProperties() {
    section("22. HTTPS SECURITY PROPERTIES");

    const properties = [
        ["Confidentiality", "Encrypts application data against ordinary network observation."],
        ["Integrity", "Authenticated encryption detects unauthorized modification."],
        ["Server authentication", "Certificate validation binds the connection to a trusted identity."],
        ["Forward secrecy", "Modern key exchanges can limit exposure of past sessions if long-term keys are later compromised."]
    ];

    for (const [name, explanation] of properties) {
        console.log(`${name.padEnd(22)}: ${explanation}`);
    }
}


// ============================================================================
// 23. END-TO-END FLOW
// ============================================================================

function demonstrateEndToEndFlow() {
    section("23. END-TO-END HTTPS FLOW");

    const steps = [
        "Resolve the server hostname.",
        "Establish network connectivity.",
        "Start the TLS handshake.",
        "Negotiate cryptographic parameters.",
        "Validate the certificate and hostname.",
        "Establish protected session keys.",
        "Send HTTP request inside the protected channel.",
        "Authenticate and authorize at the application layer.",
        "Validate input.",
        "Perform business logic.",
        "Return HTTP status, headers, and body.",
        "Record safe observability information."
    ];

    steps.forEach((step, index) => {
        console.log(`${index + 1}. ${step}`);
    });
}


// ============================================================================
// 24. SECURITY MISTAKES
// ============================================================================

function demonstrateSecurityMistakes() {
    section("24. COMMON SECURITY MISTAKES");

    const mistakes = [
        "Disabling rejectUnauthorized for production HTTPS clients.",
        "Sending passwords or tokens through plain HTTP.",
        "Treating Base64 as encryption.",
        "Logging Authorization headers.",
        "Logging session cookies.",
        "Trusting client-provided authorization claims without verification.",
        "Retrying non-idempotent operations without an idempotency strategy.",
        "Accepting ambiguous request framing.",
        "Failing to validate input.",
        "Returning sensitive diagnostic information in error responses."
    ];

    mistakes.forEach((item, index) => {
        console.log(`${index + 1}. ${item}`);
    });
}


// ============================================================================
// MAIN
// ============================================================================

async function main() {
    demonstrateTerminology();
    demonstrateRequest();
    demonstrateMethods();
    demonstrateStatusCodes();
    demonstrateHeaders();
    demonstrateUrl();
    demonstrateJsonRequest();
    demonstrateCookies();
    demonstrateCaching();
    demonstrateAuthentication();
    demonstrateRouting();
    demonstrateValidation();
    demonstrateRateLimiting();
    demonstrateSecurityHeaders();
    demonstrateEtags();
    demonstrateTimeoutDesign();
    demonstrateModernHttpVersions();
    demonstrateHttpsProperties();
    demonstrateEndToEndFlow();
    demonstrateSecurityMistakes();
    demonstrateRetryPolicy();

    await demonstrateLocalServer();
    await inspectCertificate("example.com");
    await demonstrateHttpsRequest();
}

main().catch(error => {
    console.error("Program terminated with an unexpected error:", error);
    process.exitCode = 1;
});
