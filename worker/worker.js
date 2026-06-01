export default {
  async fetch(request, env) {
    const cors = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, PUT, OPTIONS',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: cors });
    }

    const auth = (request.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '').trim();
    if (!env.ARCHON_SECRET || auth !== env.ARCHON_SECRET) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), {
        status: 401,
        headers: { ...cors, 'Content-Type': 'application/json' },
      });
    }

    const url = new URL(request.url);

    if (url.pathname === '/overrides') {
      if (request.method === 'GET') {
        const data = await env.ARCHON_KV.get('overrides');
        return new Response(data || '{"gi":{},"hsr":{},"zzz":{}}', {
          headers: { ...cors, 'Content-Type': 'application/json' },
        });
      }

      if (request.method === 'PUT') {
        const body = await request.text();
        try { JSON.parse(body); } catch {
          return new Response(JSON.stringify({ error: 'Invalid JSON' }), {
            status: 400,
            headers: { ...cors, 'Content-Type': 'application/json' },
          });
        }
        await env.ARCHON_KV.put('overrides', body);
        return new Response(JSON.stringify({ ok: true }), {
          headers: { ...cors, 'Content-Type': 'application/json' },
        });
      }
    }

    return new Response(JSON.stringify({ error: 'Not found' }), {
      status: 404,
      headers: { ...cors, 'Content-Type': 'application/json' },
    });
  },
};
