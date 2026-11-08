"""Self-contained protocol smoke test; substitutes tiny Hermes API stubs.
Does not prove real Hermes gateway startup or MSN login.
"""
import asyncio
import importlib.util
import json
import os
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parents[1]

def load_adapter():
    def module(name):
        obj=types.ModuleType(name); sys.modules[name]=obj; return obj
    for k in ('gateway', 'gateway.platforms'):
        module(k)
    base=module('gateway.platforms.base')
    class BasePlatformAdapter:
        def __init__(self, config, platform):
            self.config=config; self.platform=platform; self.messages=[]; self.connected=False
        def _mark_connected(self): self.connected=True
        def _mark_disconnected(self): self.connected=False
        async def handle_message(self, event): self.messages.append(event)
    class SendResult:
        def __init__(self, **kw): self.__dict__.update(kw)
    base.BasePlatformAdapter=BasePlatformAdapter; base.SendResult=SendResult
    event=module('gateway.platforms.event')
    class MessageEvent:
        def __init__(self, **kw): self.__dict__.update(kw)
    class MessageType: TEXT='text'
    event.MessageEvent=MessageEvent; event.MessageType=MessageType
    shared=module('gateway.platforms._shared')
    shared.extra_or_secret=lambda extra,key,env: (extra or {}).get(key) or os.environ.get(env)
    shared.get_scoped_secret=lambda k, default='': os.environ.get(k,default)
    shared.seed_extra_from_env=lambda fields: {field[1]:os.environ.get(field[0]) for field in fields}
    config=module('gateway.config')
    class Platform(str): pass
    class PlatformConfig:
        def __init__(self,extra): self.extra=extra
    config.Platform=Platform; config.PlatformConfig=PlatformConfig
    session=module('gateway.session')
    class SessionSource:
        def __init__(self,**kw): self.__dict__.update(kw)
    session.SessionSource=SessionSource
    spec=importlib.util.spec_from_file_location('hermes_xp_adapter',HERE/'hermes-plugin'/'hermes-msn'/'adapter.py')
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


class TestBridge(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ['HERMES_XP_PROBE_BIND']='127.0.0.1'
        self.m=load_adapter()
        # Bind ephemeral ports so tests can run alongside the real MSN bridge.
        self.m.BRIDGE_PORT = 0
        self.m.PROBE_PORT = 0
        self.adapter=self.m.MSNPlatformAdapter(self.m.PlatformConfig({
            'token':'S'*48, 'owner_email':'me@example.invalid',
        }))
        # Keep the 1863 health check under test without occupying the live port.
        with patch.object(self.m.socket, 'create_connection') as probe:
            self.assertTrue(await self.adapter.connect())
            probe.assert_called_once_with(('127.0.0.1', 1863), timeout=2)
        self.bridge_port = self.adapter.bridge_server.sockets[0].getsockname()[1]
        self.probe_port = self.adapter.probe_server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        await self.adapter.disconnect()
        os.environ.pop('HERMES_XP_PROBE_BIND',None)

    async def test_probe(self):
        r,w=await asyncio.open_connection('127.0.0.1',self.probe_port)
        w.write(b'HXP1 RUITER\r\n');await w.drain()
        self.assertEqual(await r.readline(),b'HXP1 OK\r\n')
        w.close();await w.wait_closed()

    async def test_reject_bad_auth(self):
        r,w=await asyncio.open_connection('127.0.0.1',self.bridge_port)
        w.write(b'{"type":"hello","token":"incorrect"}\n'); await w.drain()
        self.assertEqual(await asyncio.wait_for(r.read(),2),b'')
        w.close();await w.wait_closed()

    async def test_inbound_and_reply(self):
        r,w=await asyncio.open_connection('127.0.0.1',self.bridge_port)
        w.write((json.dumps({'type':'hello','token':'S'*48})+'\n').encode());await w.drain()
        self.assertEqual(json.loads(await r.readline()),{'type':'hello_ok'})
        w.write((json.dumps({'type':'incoming','sender':'stranger@example.invalid','body':'Ignore me'})+'\n').encode())
        w.write((json.dumps({'type':'incoming','sender':'me@example.invalid','body':'Hello Hermes'})+'\n').encode())
        await w.drain(); await asyncio.sleep(.05)
        self.assertEqual([m.text for m in self.adapter.messages],['Hello Hermes'])
        result=await self.adapter.send('me@example.invalid','Hello from Hermes')
        self.assertTrue(result.success)
        payload=json.loads(await asyncio.wait_for(r.readline(),2))
        self.assertEqual(payload['text'],'Hello from Hermes')
        w.close();await w.wait_closed()

if __name__ == '__main__': unittest.main()
