"""A tiny key-value store over Econet — the worked-example application.

`KvServer` is a `Service` plug-in (the ``oaknut.econet.service`` axis, registered
as ``kvstore``) backed by a dict; `KvClient` is the matching client. Together
they exercise the whole stack end-to-end and serve as the template an Econet
application author copies. See ``docs/dev/econet-design.md`` §13.
"""

from __future__ import annotations

__version__ = "12.5.3"

__all__: list[str] = []
