"""Self-contained protocol smoke test; substitutes tiny Hermes API stubs.
Does not prove real Hermes gateway startup or MSN login.
"""
import asyncio
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
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
        self._prior_queue = os.environ.get('HERMES_MSN_OFFLINE_QUEUE')
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['HERMES_MSN_OFFLINE_QUEUE'] = str(pathlib.Path(self.tmp.name) / 'offline.json')
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
        if self._prior_queue is None:
            os.environ.pop('HERMES_MSN_OFFLINE_QUEUE', None)
        else:
            os.environ['HERMES_MSN_OFFLINE_QUEUE'] = self._prior_queue
        self.tmp.cleanup()

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

    async def test_file_notice_hides_contents_and_send_is_basename_only(self):
        digest = '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
        r,w=await asyncio.open_connection('127.0.0.1',self.bridge_port)
        w.write((json.dumps({'type':'hello','token':'S'*48})+'\n').encode());await w.drain()
        self.assertEqual(json.loads(await r.readline()),{'type':'hello_ok'})
        for packet in (
            {'type':'incoming_file','sender':'me@example.invalid','name':'note.txt',
             'size':5,'sha256':digest,'contents':'SENTINEL_DO_NOT_LEAK_9f3a'},
            {'type':'incoming_file','sender':'stranger@example.invalid','name':'note.txt',
             'size':5,'sha256':digest},
            {'type':'incoming_file','sender':'me@example.invalid','name':'../note.txt',
             'size':5,'sha256':digest},
            {'type':'incoming_file','sender':'me@example.invalid','name':'note.txt',
             'size':5,'sha256':digest},
        ):
            w.write((json.dumps(packet)+'\n').encode())
        await w.drain(); await asyncio.sleep(.05)
        self.assertEqual([m.text for m in self.adapter.messages], [
            f'[file received] note.txt (5 bytes, sha256 {digest})'])
        self.assertNotIn('SENTINEL_DO_NOT_LEAK_9f3a', self.adapter.messages[0].text)
        rejected = await self.adapter.send(
            'me@example.invalid', '/etc/passwd', metadata={'file':'../note.txt'})
        self.assertFalse(rejected.success)
        accepted = await self.adapter.send(
            'me@example.invalid', '/etc/passwd', metadata={'file':'note.txt'})
        self.assertTrue(accepted.success)
        payload=json.loads(await asyncio.wait_for(r.readline(),2))
        self.assertEqual(payload, {'type':'send_file','to':'me@example.invalid','name':'note.txt'})
        self.assertNotIn('passwd', json.dumps(payload))
        w.close();await w.wait_closed()

    async def test_standalone_file_send_is_loopback_basename_only(self):
        seen = []
        class Reply:
            status = 202
            def read(self, _limit):
                return b'{"success": true, "queued": true}'
        class Connection:
            def __init__(self, host, port, timeout):
                self.host, self.port, self.timeout = host, port, timeout
            def request(self, method, path, body, headers):
                self.method, self.path, self.body, self.headers = method, path, body, headers
                seen.append(self)
            def getresponse(self):
                return Reply()
            def close(self):
                pass
        config = self.m.PlatformConfig({'token':'S'*48,'owner_email':'me@example.invalid'})
        with patch.object(self.m.http.client, 'HTTPConnection', side_effect=Connection):
            unsafe = await self.m.standalone_send(config, 'me@example.invalid', '', media_files=['/etc/passwd'])
            self.assertIn('error', unsafe)
            self.assertEqual(seen, [])
            accepted = await self.m.standalone_send(config, 'me@example.invalid', '', media_files=['note.txt'])
        self.assertTrue(accepted.get('success'))
        self.assertEqual(seen[0].host, '127.0.0.1')
        self.assertEqual(seen[0].path, '/file/send')
        self.assertEqual(json.loads(seen[0].body), {'to':'me@example.invalid','name':'note.txt'})
        self.assertEqual(seen[0].headers['X-Hermes-Token'], 'S'*48)

    async def test_out_of_process_sender_rejects_unauthorized_recipient(self):
        result = await self.m.standalone_send(
            self.m.PlatformConfig({'token':'S'*48,'owner_email':'me@example.invalid'}),
            'stranger@example.invalid', 'test')
        self.assertIn('error', result)

    async def test_standalone_text_sender_preserves_queued_status_and_id(self):
        seen = []
        class Reply:
            status = 202
            def read(self, _limit):
                return (b'{"success":true,"queued":true,"offline":true,'
                        b'"status":"queued","delivered":false,'
                        b'"message_id":"stable-id"}')
        class Connection:
            def __init__(self, host, port, timeout):
                self.host, self.port, self.timeout = host, port, timeout
            def request(self, method, path, body, headers):
                self.method, self.path, self.body, self.headers = method, path, body, headers
                seen.append(self)
            def getresponse(self):
                return Reply()
            def close(self):
                pass
        config = self.m.PlatformConfig({'token':'S'*48,'owner_email':'me@example.invalid'})
        with patch.object(self.m.http.client, 'HTTPConnection', side_effect=Connection):
            result = await self.m.standalone_send(config, 'me@example.invalid', 'hello')
        self.assertEqual(result, {
            "success": True, "message_id": "stable-id", "queued": True,
            "offline": True, "status": "queued", "delivered": False,
        })
        request = seen[0]
        packet = json.loads(request.body)
        self.assertEqual(request.path, "/send")
        self.assertEqual(packet["to"], "me@example.invalid")
        self.assertEqual(packet["text"], "hello")
        self.assertTrue(packet["id"])

    async def test_registration_exposes_standalone_sender(self):
        captured={}
        class Registry:
            def register_platform(self, **kwargs): captured.update(kwargs)
        self.m.register(Registry())
        self.assertIs(captured['standalone_sender_fn'], self.m.standalone_send)

    async def test_registration_exposes_talk_only_cli(self):
        observed={}
        class Registry:
            def register_platform(self, **kwargs): pass
            def register_cli_command(self, **kwargs): observed.update(kwargs)
        self.m.register(Registry())
        self.assertEqual(observed["name"], "xpvoice")
        self.assertTrue(callable(observed["setup_fn"]))
        self.assertTrue(callable(observed["handler_fn"]))

    async def test_registration_exposes_authenticated_native_call_tool(self):
        observed = {}
        class Registry:
            def register_platform(self, **_): pass
            def register_tool(self, **kwargs): observed[kwargs['name']] = kwargs
        self.m.register(Registry())
        self.assertEqual(set(observed), {"msn_call", "xp_status", "xp_screen",
                                         "xp_control", "xp_service"})
        self.assertEqual(observed["msn_call"]["toolset"], "hermes-msn")
        self.assertEqual(
            observed["msn_call"]["schema"]["parameters"]["properties"]["action"]["enum"],
            ["start", "end", "status"])
        for name, config in observed.items():
            self.assertEqual(config["schema"]["name"], name)
            self.assertTrue(callable(config["handler"]))
            self.assertFalse(config["schema"]["parameters"]["additionalProperties"])
        self.assertIn("confirm_live", observed["xp_control"]["schema"]["parameters"]["properties"])
        self.assertIn("analyze", observed["xp_screen"]["schema"]["parameters"]["properties"])

    async def test_xp_tools_are_isolated_from_hermes_core_tools_package(self):
        # Hermes itself owns the top-level tools package. A plugin must
        # never assume it can import tools.xp_agent_tools from that package.
        fake_core_tools = types.ModuleType("tools")
        fake_core_tools.__path__ = [self.tmp.name]
        with patch.dict(sys.modules, {"tools": fake_core_tools}):
            result = json.loads(self.m._handle_xp_tool("xp_status", {"probe": False}))
        self.assertTrue(result["success"], result)
        self.assertIn("services", result)
        self.assertNotIn("token", json.dumps(result).lower())

    async def test_native_call_tool_uses_loopback_only_and_owner_scoped_secret(self):
        class Reply:
            status = 202
            def read(self, _limit):
                return b'{"success": true, "active": true}'

        class Connection:
            def __init__(self, host, port, timeout):
                self.host, self.port, self.timeout = host, port, timeout
                self.path = None
            def request(self, method, path, body, headers):
                self.method, self.path, self.body, self.headers = method, path, body, headers
            def getresponse(self): return Reply()
            def close(self): pass

        seen = []
        def make_connection(*args, **kwargs):
            c = Connection(*args, **kwargs)
            seen.append(c)
            return c
        with patch.dict(os.environ, {
            "HERMES_MSN_BRIDGE_TOKEN": "t" * 48,
            "HERMES_MSN_OWNER_EMAIL": "me@example.invalid",
        }), patch.object(self.m.http.client, "HTTPConnection", side_effect=make_connection):
            result = json.loads(self.m._handle_msn_call({"action": "start"}))
        self.assertTrue(result["success"])
        self.assertEqual(len(seen), 1)
        self.assertEqual((seen[0].host, seen[0].port), ("127.0.0.1", 18769))
        self.assertEqual((seen[0].method, seen[0].path), ("POST", "/call/start"))
        self.assertEqual(seen[0].headers["X-Hermes-Token"], "t" * 48)
        self.assertFalse(json.loads(self.m._handle_msn_call(
            {"action": "run", "command": "net user"}))["success"])

if __name__ == '__main__': unittest.main()
