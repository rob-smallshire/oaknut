# oaknut-econet-kvstore

A tiny key-value store over Econet — the **worked example** of an
`oaknut-econet` application, with both a server and a client.

- `KvServer` is a `Service` (an `oaknut.econet.service` plug-in, registered as
  `kvstore`) backed by a plain `dict`: GET / PUT / DELETE on a demo port.
- `KvClient` is the matching client: `await client.put(key, value)`,
  `await client.get(key)`, `await client.delete(key)`.

It exists to validate the whole stack end-to-end — client → transmit →
`Station` port-dispatch → `KvServer` → reply → client — and to serve as the
template an application author copies. The test suite runs a full round-trip
entirely in memory over two linked `TestTransport`s, so it needs no hardware.

The demo protocol (deliberately minimal): requests on port `&B0` framed as
`[reply_port][op][key_len][key][value…]`; replies framed as `[status][value…]`.
See `docs/dev/econet-design.md` §13 for the service-host model this builds on.
