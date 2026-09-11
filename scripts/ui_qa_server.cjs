// Local HTTPS QA ingress only. Keeps the production backend's allowed Origin
// and Secure refresh cookie intact; never logs request headers or bodies.
const fs = require('node:fs');
const path = require('node:path');
const https = require('node:https');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const temporary = path.join(__dirname, '../.ui-qa');
fs.mkdirSync(temporary, { recursive: true });
const key = path.join(temporary, 'localhost.key');
const cert = path.join(temporary, 'localhost.crt');
execFileSync('C:/Program Files/Git/usr/bin/openssl.exe', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key, '-out', cert, '-days', '1', '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'], { stdio: 'ignore' });
const streams = new Set();
https.createServer({ key: fs.readFileSync(key), cert: fs.readFileSync(cert) }, (req, res) => {
  // Test-only fault injection: interrupt streaming connections at local ingress.
  if (req.method === 'POST' && req.url === '/__uiqa/disconnect-streams') {
    for (const stream of streams) stream.destroy();
    res.writeHead(200); res.end('QA_STREAMS_DISCONNECTED'); return;
  }
  if (req.url.endsWith('/stream')) { streams.add(res); res.on('close', () => streams.delete(res)); }
  const upstream = http.request({ hostname: '127.0.0.1', port: req.url.startsWith('/api/v1') ? 18001 : 3100, path: req.url, method: req.method, headers: { ...req.headers, 'x-forwarded-proto': 'https' } }, incoming => {
    res.writeHead(incoming.statusCode, incoming.headers); incoming.pipe(res);
  });
  upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end('Local QA upstream unavailable'); });
  res.on('close', () => upstream.destroy()); req.pipe(upstream);
}).listen(13000, '127.0.0.1', () => console.log('LOCAL_UI_QA_HTTPS_READY'));
