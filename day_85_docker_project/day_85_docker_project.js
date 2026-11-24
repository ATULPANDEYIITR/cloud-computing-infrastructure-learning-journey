'use strict';

/*
 * Node.js frontend service.
 * Responsibilities:
 * - Serve a browser-based task interface.
 * - Proxy API requests to the backend.
 * - Apply request limits and timeouts.
 * - Track service health.
 *
 * Runtime: Node.js 22+
 */

const http = require('node:http');
const { URL } = require('node:url');

const PORT = Number(process.env.PORT || 3000);
const API_URL = process.env.API_URL || 'http://localhost:8000';
const REQUEST_TIMEOUT = 5000;
const MAX_BODY_SIZE = 16384;

if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) {
    throw new Error('Invalid frontend port.');
}

const metrics = {
    requests: 0,
    failures: 0,
    startedAt: new Date().toISOString()
};

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Containerized Task Manager</title>
<style>
body{font-family:Arial,sans-serif;max-width:850px;margin:50px auto;
padding:20px;background:#f4f6f9;color:#202735}
main{background:white;padding:25px;border-radius:10px}
input,textarea,button{padding:12px;margin:7px 0;width:100%;
box-sizing:border-box;border:1px solid #ccc;border-radius:5px}
button{background:#174ea6;color:white;cursor:pointer}
.task{padding:12px;border-bottom:1px solid #ddd}
.status{color:#247347;font-weight:bold}
#message{margin:10px 0}
</style>
</head>
<body>
<main>
<h1>Containerized Task Manager</h1>
<p>Frontend → Backend API → PostgreSQL</p>
<form id="taskForm">
<input id="title" maxlength="200" required placeholder="Task title">
<textarea id="description" maxlength="5000"
placeholder="Description"></textarea>
<button type="submit">Create Task</button>
</form>
<p id="message" role="status"></p>
<h2>Tasks</h2>
<div id="tasks">Loading...</div>
</main>
<script>
const message = document.getElementById('message');
const taskContainer = document.getElementById('tasks');

async function request(path, options = {}) {
    const response = await fetch(path, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        }
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || 'Request failed');
    }

    return data;
}

async function loadTasks() {
    try {
        const result = await request('/api/tasks');
        taskContainer.replaceChildren();

        if (!result.tasks.length) {
            taskContainer.textContent = 'No tasks available.';
            return;
        }

        for (const task of result.tasks) {
            const item = document.createElement('div');
            item.className = 'task';

            const title = document.createElement('strong');
            title.textContent = task.title;

            const description = document.createElement('p');
            description.textContent = task.description;

            const status = document.createElement('span');
            status.className = 'status';
            status.textContent = task.status;

            item.append(title, description, status);
            taskContainer.appendChild(item);
        }
    } catch (error) {
        taskContainer.textContent = 'Unable to retrieve tasks.';
        message.textContent = error.message;
    }
}

document.getElementById('taskForm').addEventListener('submit',
    async event => {
        event.preventDefault();

        const title = document.getElementById('title').value.trim();
        const description =
            document.getElementById('description').value.trim();

        if (!title || title.length > 200) {
            message.textContent = 'Enter a valid task title.';
            return;
        }

        try {
            await request('/api/tasks', {
                method: 'POST',
                body: JSON.stringify({ title, description })
            });

            event.target.reset();
            message.textContent = 'Task created successfully.';
            await loadTasks();
        } catch (error) {
            message.textContent = error.message;
        }
    });

loadTasks();
</script>
</body>
</html>`;

async function proxyRequest(path, method, body) {
    const target = new URL(path, API_URL);

    if (target.origin !== new URL(API_URL).origin) {
        throw new Error('Invalid proxy destination.');
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

    try {
        const response = await fetch(target, {
            method,
            body,
            signal: controller.signal,
            headers: body ? { 'Content-Type': 'application/json' } : {}
        });

        const responseBody = await response.text();

        return {
            status: response.status,
            body: responseBody
        };
    } finally {
        clearTimeout(timeout);
    }
}

function sendJSON(response, status, data) {
    response.writeHead(status, {
        'Content-Type': 'application/json',
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store'
    });

    response.end(JSON.stringify(data));
}

async function readBody(request) {
    const chunks = [];
    let size = 0;

    for await (const chunk of request) {
        size += chunk.length;

        if (size > MAX_BODY_SIZE) {
            throw new Error('Request body too large.');
        }

        chunks.push(chunk);
    }

    return Buffer.concat(chunks).toString('utf8');
}

const routes = new Map([
    ['GET /', async (request, response) => {
        response.writeHead(200, {
            'Content-Type': 'text/html; charset=utf-8',
            'Content-Security-Policy':
                "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'",
            'X-Content-Type-Options': 'nosniff'
        });
        response.end(html);
    }],

    ['GET /health', async (request, response) => {
        sendJSON(response, 200, {
            service: 'frontend',
            status: 'healthy',
            uptime: process.uptime()
        });
    }],

    ['GET /ready', async (request, response) => {
        try {
            const result = await proxyRequest('/health', 'GET');
            sendJSON(response, 200, {
                frontend: 'ready',
                backend: result.status === 200 ? 'ready' : 'unavailable'
            });
        } catch {
            sendJSON(response, 503, { status: 'not_ready' });
        }
    }]
]);

const server = http.createServer(async (request, response) => {
    metrics.requests++;

    const method = request.method;
    const pathname = new URL(request.url, `http://${request.headers.host || 'localhost'}`).pathname;

    try {
        if (pathname.startsWith('/api/')) {
            if (!['GET', 'POST', 'PATCH'].includes(method)) {
                sendJSON(response, 405, { error: 'Method not allowed' });
                return;
            }

            let body;

            if (method !== 'GET') {
                body = await readBody(request);

                if (!body.trim()) {
                    sendJSON(response, 400, { error: 'Request body required' });
                    return;
                }

                JSON.parse(body);
            }

            const result = await proxyRequest(pathname, method, body);

            response.writeHead(result.status, {
                'Content-Type': 'application/json',
                'X-Content-Type-Options': 'nosniff',
                'Cache-Control': 'no-store'
            });

            response.end(result.body);
            return;
        }

        const handler = routes.get(`${method} ${pathname}`);

        if (!handler) {
            sendJSON(response, 404, { error: 'Route not found' });
            return;
        }

        await handler(request, response);

    } catch (error) {
        metrics.failures++;

        const status = error instanceof SyntaxError ? 400 : 502;

        if (!response.headersSent) {
            sendJSON(response, status, {
                error: status === 400
                    ? 'Invalid JSON request'
                    : 'Upstream service unavailable'
            });
        } else {
            response.destroy();
        }

        console.error({
            event: 'request_failure',
            message: error.message,
            method,
            pathname
        });
    }
});

server.listen(PORT, '0.0.0.0', () => {
    console.log(`Frontend listening on port ${PORT}`);
    console.log(`Backend destination: ${API_URL}`);
});

function shutdown() {
    console.log('Frontend shutting down.');

    server.close(error => {
        if (error) {
            console.error(error);
            process.exitCode = 1;
        }
    });

    setTimeout(() => process.exit(1), 10000).unref();
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
process.on('unhandledRejection', error => {
    console.error('Unhandled rejection:', error);
});

module.exports = { proxyRequest, metrics };
