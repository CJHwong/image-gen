# Open the studio from another device

The studio binds `127.0.0.1`, so only this machine can open it. To open it from a phone or
another computer on your tailnet, put Tailscale serve in front of it.

1. Start the studio on its usual address, and name the page's HTTPS origin:

   ```sh
   uv run studio --allow-origin https://my-mac.example.ts.net:8765
   ```

2. Let Tailscale serve that port over HTTPS:

   ```sh
   tailscale serve --bg --https=8765 http://127.0.0.1:8765
   ```

3. Open **https://my-mac.example.ts.net:8765** on the other device.

Use the machine name that `tailscale status` shows. The startup line names the origins that
may post, so you can compare it with the address bar.

Do not use `tailscale funnel` for the studio. Funnel puts the page on the public internet,
and the studio has no login.

## Why the flag is necessary

The server refuses a POST when the page's Origin does not name the server. This stops other
sites, and DNS rebinding, from starting runs. Behind the proxy, the page's origin is
`https://my-mac.example.ts.net:8765`, and the server bound `127.0.0.1`. So the server refuses
every POST until you name that origin. A page on another site cannot send that origin.

The flag takes `scheme://host[:port]` only. The studio refuses `null`, `*`, a path, or a
value with no scheme, and does not start. `null` would let a sandboxed frame on any site post.

## Why plain HTTP on the tailnet is not enough

`--host 0.0.0.0` and `http://my-mac.example.ts.net:8765` also reach the server. A browser does
not treat that address as a secure context, because it is neither HTTPS nor `localhost`.
The page needs a secure context: without one, `crypto.randomUUID` does not exist, and the
page stops before it draws its controls.
