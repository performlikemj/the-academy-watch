// The Academy Watch — share-link proxy
// Routes to attach (Workers & Pages → this worker → Settings → Domains & Routes → Add route, zone theacademywatch.com):
//   theacademywatch.com/p/*
//   theacademywatch.com/sitemap.xml
//   www.theacademywatch.com/p/*
//   www.theacademywatch.com/sitemap.xml
// Everything else on the site never touches this worker.

const ORIGIN = 'api.theacademywatch.com';

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const isShare = url.pathname === '/sitemap.xml' || url.pathname === '/p' || url.pathname.startsWith('/p/');
    if (!isShare) {
      // Safety net if the route ever matches more than intended: pass through untouched.
      return fetch(request);
    }
    url.hostname = ORIGIN;
    const upstream = new Request(url.toString(), {
      method: request.method,
      headers: request.headers,
      redirect: 'manual',
    });
    const response = await fetch(upstream);
    // Return the backend's answer as-is (og tags, card.png, sitemap XML, or the neutral 404).
    return new Response(response.body, {
      status: response.status,
      headers: response.headers,
    });
  },
};
