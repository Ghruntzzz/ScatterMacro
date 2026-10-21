import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from python_macro.pathing import PathRecording,decode_path,replay_path
from python_macro.unit_actions import UnitIndexer
from ui.unit_manager import UnitManager,EMPTY_INDEX
from ui import dashboard
from test_unit_actions import FastStop


def path(mode='Keyboard',events=None):
    return json.dumps(dict(version=1,mode=mode,duration=1,
                           events=events if events is not None else [[0,'key','W',1],[1,'key','W',0]]))


class PathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_wasd_only_recording_and_focus_pause(self):
        now=[0]
        recorder=PathRecording('Keyboard',lambda:now[0])
        recorder.sample(True,['W','E'],dx=50)
        now[0]=1
        recorder.sample(True,['W','D'])
        now[0]=1.01
        recorder.sample(False,['A'])
        now[0]=30
        recorder.sample(False,['S'])
        now[0]=31
        recorder.sample(True,['S'])
        now[0]=32
        recorder.sample(True,[])
        data=decode_path(recorder.finish())
        self.assertEqual(data['duration'],2)
        self.assertTrue(all(e[1]=='key' and e[2] in 'WDS' for e in data['events']))
        self.assertEqual(data['events'][0],[0,'key','W',1])
        self.assertIn([1,'key','W',0],data['events'])

    def test_mouse_mode_ignores_keyboard_and_records_relative_drag(self):
        now=[0]
        recorder=PathRecording('Mouse',lambda:now[0])
        recorder.sample(True,['W'],True,12,-4)
        now[0]=.5
        recorder.sample(True,[],False)
        data=decode_path(recorder.finish())
        self.assertEqual(data['events'],[[0,'look',1],[0,'mouse',12,-4],[.5,'look',0]])

    def test_invalid_keys_times_and_modes_rejected(self):
        for raw in ('{}',path(events=[[0,'key','E',1]]),path(events=[[2,'key','W',1]]),
                    path(events=[[.8,'key','W',1],[.4,'key','W',0]]),path(mode='Mouse'),
                    path(events=[[0,'mouse',10,20]])):
            with self.assertRaises(ValueError):
                decode_path(raw)

    def test_replay_preserves_timing_and_order(self):
        now=[0]
        stop=FastStop()
        stop.wait=lambda seconds:now.__setitem__(0,now[0]+seconds) or False
        client=SimpleNamespace(focus_pause_time=0,check_focus=Mock(),_key=Mock(),_send_mouse=Mock())
        replay_path(path('Both',[[0,'key','W',1],[.5,'mouse',3,-2],[1,'key','W',0]]),
                    client,stop,clock=lambda:now[0])
        self.assertAlmostEqual(now[0],1)
        self.assertEqual([c.args for c in client._key.call_args_list],[('W',),('W',)])
        client._send_mouse.assert_called_once_with(1,dx=3,dy=-2)

    def test_stop_and_game_end_release_all_held_input(self):
        for game_end in (False,True):
            now=[0]
            stop=FastStop()
            def wait(seconds):
                now[0]+=seconds
                if not game_end:
                    stop.set()
                return stop.is_set()
            stop.wait=wait
            client=SimpleNamespace(focus_pause_time=0,check_focus=Mock(),_key=Mock(),_send_mouse=Mock())
            def heartbeat():
                if game_end and now[0]>.0:
                    raise RuntimeError('round ended')
            with self.assertRaises(RuntimeError if game_end else InterruptedError):
                replay_path(path('Both',[[0,'key','W',1],[0,'look',1],[1,'mouse',1,1]]),
                            client,stop,heartbeat,lambda:now[0])
            client._key.assert_called_with('W',release=True)
            client._send_mouse.assert_called_with(0x10)

    def test_path_index_replays_in_numerical_order_without_unit_placement(self):
        entries=[dict(EMPTY_INDEX,path=path()),dict(EMPTY_INDEX,unit='1',x='10',y='20')]
        worker=UnitIndexer(entries,Mock(),Mock(),Mock(),FastStop(),Mock())
        worker.close=Mock()
        worker.place=Mock()
        self.assertFalse(worker.all_done())
        self.assertEqual(worker.next_ready(None),0)
        with patch('python_macro.pathing.replay_path') as replay:
            worker.run(0)
        replay.assert_called_once()
        worker.place.assert_not_called()
        self.assertEqual(worker.next_ready(None),1)

    def test_manager_path_disables_fields_and_reset_restores(self):
        entries=[dict(EMPTY_INDEX,unit='6',x='400',y='300')]
        widget=UnitManager(entries,Mock(),lambda:False,Mock(),record=Mock())
        widget.save_path(0,path())
        self.assertEqual(entries[0]['unit'],'0')
        self.assertEqual(entries[0]['x'],'')
        self.assertTrue(all(not field.isEnabled() for field in widget.fields.values()))
        self.assertIn('PATH',widget.cards[0].text())
        widget.recording_changed(True)
        self.assertEqual(widget.record_button.text(),'Stop Recording')
        widget.recording_changed(False)
        widget.clear_index()
        self.assertTrue(all(field.isEnabled() for field in widget.fields.values()))
        widget.close()

    def test_recording_f3_stops_without_sending_input(self):
        from ui.path_recorder import PathRecorder
        from PySide6.QtWidgets import QWidget
        window=QWidget()
        user=Mock()
        user.GetForegroundWindow.return_value=99
        user.GetAsyncKeyState.return_value=0
        client=SimpleNamespace(user=user,hwnd=99,focus_roblox=Mock(return_value=True))
        recorder=PathRecorder(client,'Keyboard',window)
        finished=Mock()
        recorder.finished.connect(finished)
        recorder.start()
        self.assertTrue(recorder.active)
        user.GetAsyncKeyState.side_effect=lambda key:0x8000 if key==0x72 else 0
        recorder.sample()
        self.assertFalse(recorder.active)
        finished.assert_called_once_with('')
        user.SendInput.assert_not_called()
        window.close()

    def test_raw_mouse_registration_and_cleanup_without_global_input(self):
        import ctypes
        from ui.path_recorder import PathRecorder,Header,Mouse
        from PySide6.QtWidgets import QWidget
        window=QWidget()
        user=Mock()
        user.GetForegroundWindow.return_value=99
        user.GetAsyncKeyState.return_value=0
        user.RegisterRawInputDevices.return_value=True
        client=SimpleNamespace(user=user,hwnd=99,focus_roblox=Mock(return_value=True))
        recorder=PathRecorder(client,'Mouse',window)
        recorder.start()
        header=Header(0,ctypes.sizeof(Header)+ctypes.sizeof(Mouse),None,0)
        mouse=Mouse(0,0,0,7,-3,0)
        packet=bytes(header)+bytes(mouse)
        def read(handle,command,buffer,size,header_size):
            ctypes.cast(size,ctypes.POINTER(ctypes.c_uint)).contents.value=len(packet)
            if buffer is None:
                return 0
            ctypes.memmove(buffer,packet,len(packet))
            return len(packet)
        user.GetRawInputData.side_effect=read
        recorder.raw_mouse(10)
        self.assertEqual(recorder.recording.events[-1][1:],['mouse',7,-3])
        recorder.finish()
        self.assertFalse(recorder.registered)
        self.assertEqual(user.RegisterRawInputDevices.call_count,2)
        user.SendInput.assert_not_called()
        window.close()

    def test_path_round_trips_through_runtime_config(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(dashboard,'CONFIG_PATH',Path(directory)/'settings.ini'):
            window=dashboard.RuntimeWindow()
            window._save_runtime_index(0,dict(EMPTY_INDEX,path=path()))
            self.assertEqual(dashboard.load_unit_indexes(window.values)[0]['path'],path())
            window.close()
