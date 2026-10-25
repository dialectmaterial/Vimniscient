# vimniscient.com

The static site in `public/`, served by Cloudflare Workers through the
[`cf`](https://developers.cloudflare.com/cf/) CLI (Node 22.18+, signed in
with `cf auth login`).

```bash
npm install
npx cf dev       # serve it locally
npx cf deploy    # publish to vimniscient.com
```

`cloudflare.config.ts` names the Worker and its domains; `wrangler.config.ts`
points the build at `public/`.
