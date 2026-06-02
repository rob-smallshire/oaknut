"""Contract for the Service.from_config default."""

from oaknut.econet.station import Service


class _ConfigService(Service):
    def __init__(self, name="cfg", *, greeting="hi", reply_to=None):
        super().__init__(name=name)
        self.greeting = greeting
        self.reply_to = reply_to

    @property
    def ports(self):
        return frozenset({0xC0})

    async def handle(self, request, station):
        pass


def test_from_config_default_passes_flat_kwargs():
    service = _ConfigService.from_config(name="cfg", config={"greeting": "yo"})
    assert service.name == "cfg"
    assert service.greeting == "yo"


def test_from_config_normalises_hyphenated_keys():
    service = _ConfigService.from_config(name="cfg", config={"reply-to": "0.1"})
    assert service.reply_to == "0.1"
